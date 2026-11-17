#include "rtp-apps.h"

#include "ns3/double.h"
#include "ns3/inet-socket-address.h"
#include "ns3/log.h"
#include "ns3/simulator.h"
#include "ns3/udp-socket-factory.h"

#include <algorithm>
#include <cmath>
#include <iomanip>

namespace ns3
{
NS_LOG_COMPONENT_DEFINE("RtpVideoApps");
NS_OBJECT_ENSURE_REGISTERED(GilbertElliottErrorModel);
NS_OBJECT_ENSURE_REGISTERED(RtpVideoSender);
NS_OBJECT_ENSURE_REGISTERED(RtpVideoReceiver);

namespace
{
uint32_t Read32(const uint8_t* bytes)
{
    return (uint32_t(bytes[0]) << 24) | (uint32_t(bytes[1]) << 16) |
           (uint32_t(bytes[2]) << 8) | bytes[3];
}

void Write32(uint8_t* bytes, uint32_t value)
{
    bytes[0] = uint8_t(value >> 24);
    bytes[1] = uint8_t(value >> 16);
    bytes[2] = uint8_t(value >> 8);
    bytes[3] = uint8_t(value);
}
} // namespace

TypeId GilbertElliottErrorModel::GetTypeId()
{
    static TypeId tid = TypeId("ns3::GilbertElliottErrorModel")
                            .SetParent<ErrorModel>()
                            .SetGroupName("Network")
                            .AddConstructor<GilbertElliottErrorModel>();
    return tid;
}

void GilbertElliottErrorModel::Configure(double loss, double burst)
{
    m_averageLoss = loss;
    m_meanBurst = burst;
    m_rng = CreateObject<UniformRandomVariable>();
    m_rng->SetStream(10);
    DoReset();
}

bool GilbertElliottErrorModel::DoCorrupt(Ptr<Packet>)
{
    if (m_averageLoss == 0 || m_averageLoss == 1)
    {
        return m_averageLoss == 1;
    }
    // Stationary loss = a/(a+b), bad-run mean = 1/b; emissions precede transitions.
    const bool lost = m_bad;
    const double badToGood = 1.0 / m_meanBurst;
    const double goodToBad = m_averageLoss * badToGood / (1.0 - m_averageLoss);
    const double draw = m_rng->GetValue();
    if (m_bad)
    {
        m_bad = !(draw < badToGood);
    }
    else
    {
        m_bad = draw < goodToBad;
    }
    return lost;
}

void GilbertElliottErrorModel::DoReset()
{
    m_bad = m_rng && m_rng->GetValue() < m_averageLoss;
}

TypeId RtpVideoSender::GetTypeId()
{
    static TypeId tid = TypeId("ns3::RtpVideoSender")
                            .SetParent<Application>()
                            .SetGroupName("Applications")
                            .AddConstructor<RtpVideoSender>();
    return tid;
}

void RtpVideoSender::Configure(Ipv4Address peer, double fps, uint32_t bytes, double jitter,
                               std::string path, bool abr, Time duration)
{
    m_peer = peer;
    m_fps = fps;
    m_frameBytes = bytes;
    m_frameJitter = jitter;
    m_csvPath = path;
    m_abr = abr;
    m_quality = 75;
    m_duration = duration;
    m_sizeRng = CreateObject<UniformRandomVariable>();
    m_sizeRng->SetStream(20);
}

const std::vector<SentFrame>& RtpVideoSender::GetFrames() const
{
    return m_frames;
}

void RtpVideoSender::SetAbrLogger(std::function<void(const uint8_t*)> logger)
{
    m_abrLogger = logger;
}

void RtpVideoSender::StartApplication()
{
    m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    NS_ABORT_MSG_IF(m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), 5004)) < 0,
                    "Cannot bind sender RTP");
    m_socket->Connect(InetSocketAddress(m_peer, 5004));
    m_rtcpSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    NS_ABORT_MSG_IF(m_rtcpSocket->Bind(InetSocketAddress(Ipv4Address::GetAny(), 5005)) < 0,
                    "Cannot bind sender RTCP");
    m_rtcpSocket->SetRecvCallback(MakeCallback(&RtpVideoSender::ReadRtcp, this));
    m_csv.open(m_csvPath);
    NS_ABORT_MSG_IF(!m_csv, "Cannot open sender.csv");
    m_csv << "frame_id,rtp_ts,seq_first,seq_last,n_pkts,bytes,quality,"
             "t_capture_mono_ns,t_send_first_mono_ns,t_send_last_mono_ns\n";
    // Resolve ARP before media starts. This non-RTP datagram is never impaired.
    m_socket->Send(Create<Packet>(1));
    m_firstCapture = Simulator::Now() + MilliSeconds(100);
    m_event = Simulator::Schedule(MilliSeconds(100), &RtpVideoSender::SendFrame, this);
}

void RtpVideoSender::StopApplication()
{
    Simulator::Cancel(m_event);
    m_socket->Close();
    m_rtcpSocket->Close();
    m_csv.close();
}

void RtpVideoSender::ReadRtcp(Ptr<Socket> socket)
{
    while (Ptr<Packet> packet = socket->Recv())
    {
        uint8_t bytes[32]{};
        if (packet->GetSize() < sizeof(bytes))
        {
            continue;
        }
        packet->CopyData(bytes, sizeof(bytes));
        if (bytes[1] != 201 || !m_abr)
        {
            continue;
        }
        // RR fraction is quantized in units of 1/256; compare strict thresholds.
        const double fraction = bytes[12] / 256.0;
        const uint32_t jitter = Read32(bytes + 20);
        const bool rising = m_haveJitter && jitter >= 1.5 * m_lastJitter &&
                            int64_t(jitter) - m_lastJitter >= 90;
        m_lastJitter = jitter;
        m_haveJitter = true;
        if (fraction > 0.05)
        {
            m_quality = std::max(20u, uint32_t(m_quality * 0.7));
            m_cleanRrs = 0;
        }
        else if (fraction < 0.01 && !rising)
        {
            if (++m_cleanRrs == 3)
            {
                m_quality = std::min(95u, m_quality + 5);
                m_cleanRrs = 0;
            }
        }
        else
        {
            m_cleanRrs = 0;
        }
        if (m_abrLogger)
        {
            m_abrLogger(bytes);
        }
    }
}

void RtpVideoSender::SendFrame()
{
    const uint32_t frame = m_frames.size();
    // ASSUMED linear JPEG-size model; fixed mode retains its original size.
    const double base = m_abr ? m_frameBytes * (m_quality / 90.0) : m_frameBytes;
    uint32_t size = std::max(1u, uint32_t(base));
    if (m_frameJitter > 0)
    {
        const double scale = 1.0 + m_sizeRng->GetValue(-m_frameJitter, m_frameJitter);
        size = std::max(1u, uint32_t(base * scale));
    }
    const uint64_t now = Simulator::Now().GetNanoSeconds();
    const uint32_t timestamp = uint32_t((now * 90) / 1000000);
    const uint16_t firstSeq = m_seq;
    uint32_t offset = 0;
    uint32_t packets = 0;
    uint32_t wireBytes = 0;
    do
    {
        const bool first = offset == 0;
        const uint32_t room = RTP_PAYLOAD_BYTES - 8 - (first ? 4 : 0);
        const uint32_t chunk = std::min(room, size - offset);
        const bool last = offset + chunk == size;
        std::vector<uint8_t> bytes(12 + 8 + (first ? 4 : 0) + chunk);
        bytes[0] = 0x80;
        bytes[1] = uint8_t((last ? 0x80 : 0) | 96);
        bytes[2] = uint8_t(m_seq >> 8);
        bytes[3] = uint8_t(m_seq);
        Write32(bytes.data() + 4, timestamp);
        Write32(bytes.data() + 8, RTP_SSRC);
        Write32(bytes.data() + 12, frame);
        bytes[16] = uint8_t(offset >> 16);
        bytes[17] = uint8_t(offset >> 8);
        bytes[18] = uint8_t(offset);
        bytes[19] = first ? 1 : 0;
        if (first)
        {
            Write32(bytes.data() + 20, size);
        }
        Ptr<Packet> packet = Create<Packet>(bytes.data(), bytes.size());
        NS_ABORT_MSG_IF(m_socket->Send(packet) < 0, "RTP send failed");
        wireBytes += bytes.size();
        offset += chunk;
        ++packets;
        ++m_seq;
    } while (offset < size);

    m_frames.push_back({frame, timestamp, packets, now});
    m_csv << frame << ',' << timestamp << ',' << firstSeq << ',' << uint16_t(m_seq - 1)
          << ',' << packets << ',' << wireBytes << ',' << m_quality << ',' << now << ','
          << now << ',' << Simulator::Now().GetNanoSeconds() << '\n';
    // Absolute capture schedule avoids accumulating rounded frame-period errors.
    const Time next = m_firstCapture + Seconds(m_frames.size() / m_fps);
    if (next < m_firstCapture + m_duration)
    {
        m_event = Simulator::Schedule(next - Simulator::Now(), &RtpVideoSender::SendFrame, this);
    }
}

TypeId RtpVideoReceiver::GetTypeId()
{
    static TypeId tid = TypeId("ns3::RtpVideoReceiver")
                            .SetParent<Application>()
                            .SetGroupName("Applications")
                            .AddConstructor<RtpVideoReceiver>();
    return tid;
}

void RtpVideoReceiver::Configure(double delay, double jitter, double playout, std::string dir,
                                 Ipv4Address sender, Ptr<ErrorModel> loss,
                                 std::string anchor, std::string jitterDist)
{
    m_delayMs = delay;
    m_jitterMs = jitter;
    m_playoutMs = playout;
    m_outDir = dir;
    m_sender = sender;
    m_loss = loss;
    m_playoutAnchor = anchor;
    if (jitterDist == "normal")
    {
        m_delayRng = CreateObject<NormalRandomVariable>();
        m_delayRng->SetAttribute("Variance", DoubleValue(jitter * jitter));
    }
    else
    {
        m_delayRng = CreateObject<UniformRandomVariable>();
        m_delayRng->SetAttribute("Min", DoubleValue(-jitter));
        m_delayRng->SetAttribute("Max", DoubleValue(jitter));
    }
    m_delayRng->SetStream(30);
}

uint64_t RtpVideoReceiver::GetDelayClipCount() const
{
    return m_delayClipCount;
}

void RtpVideoReceiver::StartApplication()
{
    m_rx.open(m_outDir + "/receiver.csv");
    m_rtcp.open(m_outDir + "/rtcp.csv");
    NS_ABORT_MSG_IF(!m_rx || !m_rtcp, "Cannot open receiver CSV files");
    m_rx << "seq,rtp_ts,frame_id,marker,bytes,t_arrival_rx_ns,transit_ts_units,jitter_ts_units\n";
    m_rx << std::setprecision(12);
    m_rtcp << "t_mono_ns,dir,type,ssrc,fraction_lost,cum_lost,ext_high_seq,"
              "jitter,lsr,dlsr,rtt_ms\n";
    m_socket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    NS_ABORT_MSG_IF(m_socket->Bind(InetSocketAddress(Ipv4Address::GetAny(), 5004)) < 0,
                    "Cannot bind receiver RTP");
    m_socket->SetRecvCallback(MakeCallback(&RtpVideoReceiver::HandleRead, this));
    m_rtcpSocket = Socket::CreateSocket(GetNode(), UdpSocketFactory::GetTypeId());
    NS_ABORT_MSG_IF(m_rtcpSocket->Bind(InetSocketAddress(Ipv4Address::GetAny(), 5005)) < 0,
                    "Cannot bind receiver RTCP");
    m_rtcpSocket->Connect(InetSocketAddress(m_sender, 5005));
    m_rrEvent = Simulator::Schedule(Seconds(1), &RtpVideoReceiver::SendRr, this);
}

void RtpVideoReceiver::StopApplication()
{
    Simulator::Cancel(m_rrEvent);
    WriteRr();
    m_socket->Close();
    m_rtcpSocket->Close();
    m_rx.close();
    m_rtcp.close();
}

void RtpVideoReceiver::HandleRead(Ptr<Socket> socket)
{
    while (Ptr<Packet> packet = socket->Recv())
    {
        // Impair each RTP datagram once, after UDP; never ARP, RTCP or warm-up.
        if (packet->GetSize() < 20 || (m_loss && m_loss->IsCorrupt(packet)))
        {
            continue;
        }
        const double jitter = m_jitterMs > 0 ? m_delayRng->GetValue() : 0;
        const double delay = m_delayMs + jitter;
        m_delayClipCount += delay < 0;
        Simulator::Schedule(Seconds(std::max(0.0, delay) / 1000),
                            &RtpVideoReceiver::ReceivePacket, this, packet);
    }
}

void RtpVideoReceiver::ReceivePacket(Ptr<Packet> packet)
{
    std::vector<uint8_t> bytes(packet->GetSize());
    packet->CopyData(bytes.data(), bytes.size());
    const uint16_t seq = uint16_t((bytes[2] << 8) | bytes[3]);
    const uint32_t timestamp = Read32(bytes.data() + 4);
    const uint32_t frame = Read32(bytes.data() + 12);
    const bool marker = (bytes[1] & 128) != 0;
    const uint32_t offset = (uint32_t(bytes[16]) << 16) | (uint32_t(bytes[17]) << 8) |
                            bytes[18];
    const bool first = (bytes[19] & 1) != 0;
    if (bytes[0] != 0x80 || (bytes[1] & 127) != 96 || (first && bytes.size() < 24))
    {
        return;
    }

    // One trusted source starts at sequence zero. Unwrap around its highest sequence.
    const int32_t delta = int16_t(uint16_t(seq - uint16_t(m_highSeq)));
    if (!m_initialized)
    {
        m_highSeq = seq;
        m_initialized = true;
    }
    else if (delta > 0)
    {
        m_highSeq += delta;
    }
    ++m_received;
    const uint64_t arrival = Simulator::Now().GetNanoSeconds();
    const uint32_t arrivalTicks = uint32_t((arrival * 90) / 1000000);
    const int64_t transit = int32_t(arrivalTicks - timestamp);
    if (m_haveTransit)
    {
        // RFC 3550 section 6.4.1 / Appendix A.8, in 90 kHz timestamp units.
        m_jitter += (std::abs(transit - m_transit) - m_jitter) / 16.0;
    }
    m_transit = transit;
    m_haveTransit = true;
    m_rx << seq << ',' << timestamp << ',' << frame << ',' << marker << ',' << bytes.size()
         << ',' << arrival << ',' << transit << ',' << m_jitter << '\n';

    if (!m_haveAnchor)
    {
        m_anchorTimestamp = timestamp;
        m_timestampReference = timestamp;
        m_anchorNs = arrival;
        m_haveAnchor = true;
    }
    // Nearest extended timestamp, matching RTP2 unwrap32 even with reordering.
    const int64_t extended = m_timestampReference +
        int32_t(timestamp - uint32_t(m_timestampReference));
    m_timestampReference = std::max(m_timestampReference, extended);
    Frame& state = m_frames[frame];
    // Integer floor division also for packets older than the first arrival's timestamp.
    const int64_t ticks = extended - m_anchorTimestamp;
    const int64_t remainderNs = (ticks % RTP_CLOCK_RATE) * 1000000000;
    const int64_t deltaNs = (ticks / RTP_CLOCK_RATE) * 1000000000 +
        remainderNs / RTP_CLOCK_RATE -
        (remainderNs < 0 && remainderNs % RTP_CLOCK_RATE != 0);
    state.deadlineNs = m_anchorNs + deltaNs + int64_t(m_playoutMs * 1e6);
    state.timestamp = timestamp;
    const uint32_t body = bytes.size() - 20 - (first ? 4 : 0);
    state.fragments.emplace(offset, body);
    if (first)
    {
        state.haveFirst = true;
        state.totalBytes = Read32(bytes.data() + 20);
    }
    if (marker)
    {
        state.haveMarker = true;
        state.markerEnd = offset + body;
    }
    if (!state.haveFirst || !state.haveMarker || state.completeNs != 0)
    {
        return;
    }
    // Require contiguous JPEG coverage, including the first and marker fragments.
    uint32_t end = 0;
    for (const auto& [start, length] : state.fragments)
    {
        if (start != end)
        {
            return;
        }
        end += length;
    }
    if (end == state.totalBytes && end == state.markerEnd)
    {
        state.completeNs = arrival;
    }
}

void RtpVideoReceiver::LogAbr(const uint8_t* report)
{
    // Shared schema: feedback fields retain RR meaning, including zero LSR/DLSR.
    const uint32_t lost = (uint32_t(report[13]) << 16) |
                          (uint32_t(report[14]) << 8) | report[15];
    m_rtcp << Simulator::Now().GetNanoSeconds() << ",local,ABR," << RTP_SSRC << ','
           << uint32_t(report[12]) << ',' << lost << ',' << Read32(report + 16) << ','
           << Read32(report + 20) << ",0,0,\n";
}

void RtpVideoReceiver::WriteFrames(const std::vector<SentFrame>& sent)
{
    std::ofstream csv(m_outDir + "/frames_rx.csv");
    NS_ABORT_MSG_IF(!csv, "Cannot open frames_rx.csv");
    csv << "frame_id,rtp_ts,n_expected,n_received,complete,"
           "t_complete_rx_ns,t_playout_rx_ns,status\n";
    // Offline simulation accounting only: the sender manifest never feeds RR or loss.
    for (const SentFrame& frame : sent)
    {
        const auto found = m_frames.find(frame.id);
        const Frame* state = found == m_frames.end() ? nullptr : &found->second;
        const bool complete = state && state->completeNs != 0;
        const int64_t deadline = m_playoutAnchor == "capture"
            ? int64_t(frame.captureNs) + int64_t(m_playoutMs * 1e6)
            : (state ? state->deadlineNs : 0);
        const std::string status = !complete ? "lost" :
                                  (int64_t(state->completeNs) <= deadline ? "ok" : "late");
        csv << frame.id << ',' << frame.timestamp << ',' << frame.packets << ','
            << (state ? state->fragments.size() : 0) << ',' << complete << ',';
        if (complete)
        {
            csv << state->completeNs;
        }
        csv << ',';
        if (state || m_playoutAnchor == "capture")
        {
            csv << deadline;
        }
        csv << ',' << status << '\n';
    }
}

void RtpVideoReceiver::SendRr()
{
    WriteRr();
    m_rrEvent = Simulator::Schedule(Seconds(1), &RtpVideoReceiver::SendRr, this);
}

void RtpVideoReceiver::WriteRr()
{
    if (!m_initialized)
    {
        return;
    }
    // RFC 3550 section 6.4.1: expected = extended_highest - base_seq + 1.
    const uint32_t expected = m_highSeq + 1;
    const uint32_t lost = expected > m_received ? expected - m_received : 0;
    const uint32_t intervalExpected = expected - m_expectedPrior;
    const uint32_t intervalReceived = m_received - m_receivedPrior;
    uint8_t fraction = 0;
    if (intervalExpected > intervalReceived)
    {
        fraction = uint8_t(std::min(255u, ((intervalExpected - intervalReceived) * 256) /
                                         intervalExpected));
    }
    m_expectedPrior = expected;
    m_receivedPrior = m_received;
    uint8_t data[32] = {0x81, 201, 0, 7};
    Write32(data + 4, 0x52545032);
    Write32(data + 8, RTP_SSRC);
    data[12] = fraction;
    const uint32_t lost24 = std::min(lost, 0x7fffffu);
    data[13] = uint8_t(lost24 >> 16);
    data[14] = uint8_t(lost24 >> 8);
    data[15] = uint8_t(lost24);
    Write32(data + 16, m_highSeq);
    Write32(data + 20, uint32_t(m_jitter));
    m_rtcpSocket->Send(Create<Packet>(data, sizeof(data)));
    m_rtcp << Simulator::Now().GetNanoSeconds() << ",tx,RR," << RTP_SSRC << ','
           << uint32_t(fraction) << ',' << lost24 << ',' << m_highSeq << ','
           << uint32_t(m_jitter) << ",0,0,\n";
}

} // namespace ns3
