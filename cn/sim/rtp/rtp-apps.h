#ifndef RTP_APPS_H
#define RTP_APPS_H

#include "ns3/application.h"
#include "ns3/error-model.h"
#include "ns3/event-id.h"
#include "ns3/ipv4-address.h"
#include "ns3/random-variable-stream.h"
#include "ns3/socket.h"

#include <functional>
#include <fstream>
#include <map>
#include <string>
#include <vector>

namespace ns3
{

constexpr uint32_t RTP_CLOCK_RATE = 90000;
constexpr uint32_t RTP_SSRC = 0x52545031;
constexpr uint32_t RTP_PAYLOAD_BYTES = 1200;

struct SentFrame
{
    uint32_t id;
    uint32_t timestamp;
    uint32_t packets;
    uint64_t captureNs;
};

class GilbertElliottErrorModel : public ErrorModel
{
  public:
    static TypeId GetTypeId();
    void Configure(double averageLoss, double meanBurst);

  private:
    bool DoCorrupt(Ptr<Packet> packet) override;
    void DoReset() override;
    double m_averageLoss{0};
    double m_meanBurst{4};
    bool m_bad{false};
    Ptr<UniformRandomVariable> m_rng;
};

class RtpVideoSender : public Application
{
  public:
    static TypeId GetTypeId();
    void Configure(Ipv4Address peer, double fps, uint32_t frameBytes, double frameJitter,
                   std::string csvPath, bool abr, Time duration);
    const std::vector<SentFrame>& GetFrames() const;
    void SetAbrLogger(std::function<void(const uint8_t*)> logger);

  private:
    void StartApplication() override;
    void StopApplication() override;
    void SendFrame();
    void ReadRtcp(Ptr<Socket> socket);
    Ptr<Socket> m_socket;
    Ptr<Socket> m_rtcpSocket;
    Ptr<UniformRandomVariable> m_sizeRng;
    Ipv4Address m_peer;
    double m_fps{30};
    uint32_t m_frameBytes{12000};
    double m_frameJitter{0};
    uint32_t m_seq{0};
    uint32_t m_quality{75};
    uint32_t m_cleanRrs{0};
    uint32_t m_lastJitter{0};
    bool m_haveJitter{false};
    std::function<void(const uint8_t*)> m_abrLogger;
    bool m_abr{false};
    Time m_duration;
    Time m_firstCapture;
    std::string m_csvPath;
    std::ofstream m_csv;
    EventId m_event;
    std::vector<SentFrame> m_frames;
};

class RtpVideoReceiver : public Application
{
  public:
    static TypeId GetTypeId();
    void Configure(double delayMs, double jitterMs, double playoutMs, std::string outDir,
                   Ipv4Address sender, Ptr<ErrorModel> loss, std::string anchor,
                   std::string jitterDist);
    uint64_t GetDelayClipCount() const;
    void WriteFrames(const std::vector<SentFrame>& sent);
    void LogAbr(const uint8_t* report);

  private:
    struct Frame
    {
        uint32_t timestamp{0};
        uint32_t totalBytes{0};
        uint32_t markerEnd{0};
        uint64_t completeNs{0};
        int64_t deadlineNs{0};
        bool haveFirst{false};
        bool haveMarker{false};
        std::map<uint32_t, uint32_t> fragments;
    };

    void StartApplication() override;
    void StopApplication() override;
    void HandleRead(Ptr<Socket> socket);
    void ReceivePacket(Ptr<Packet> packet);
    void SendRr();
    void WriteRr();
    Ptr<Socket> m_socket;
    Ptr<Socket> m_rtcpSocket;
    Ptr<ErrorModel> m_loss;
    Ptr<RandomVariableStream> m_delayRng;
    std::string m_playoutAnchor;
    uint64_t m_delayClipCount{0};
    bool m_haveAnchor{false};
    int64_t m_anchorTimestamp{0};
    int64_t m_timestampReference{0};
    int64_t m_anchorNs{0};
    double m_delayMs{0};
    double m_jitterMs{0};
    double m_playoutMs{50};
    Ipv4Address m_sender;
    std::string m_outDir;
    std::ofstream m_rx;
    std::ofstream m_rtcp;
    std::map<uint32_t, Frame> m_frames;
    uint32_t m_highSeq{0};
    uint32_t m_received{0};
    uint32_t m_expectedPrior{0};
    uint32_t m_receivedPrior{0};
    bool m_initialized{false};
    double m_jitter{0};
    int64_t m_transit{0};
    bool m_haveTransit{false};
    EventId m_rrEvent;
};

} // namespace ns3
#endif
