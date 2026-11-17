#include "rtp-apps.h"

#include "ns3/command-line.h"
#include "ns3/csma-helper.h"
#include "ns3/internet-stack-helper.h"
#include "ns3/ipv4-address-helper.h"
#include "ns3/mobility-helper.h"
#include "ns3/rng-seed-manager.h"
#include "ns3/string.h"
#include "ns3/wifi-helper.h"
#include "ns3/yans-wifi-helper.h"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <iostream>
#include <sstream>

using namespace ns3;

int main(int argc, char** argv)
{
    std::string link = "csma";
    std::string outDir = "results/sim_rtp/manual";
    double fps = 30;
    double lossP = 0;
    std::string lossSteps;
    double geBurst = 0;
    double delayMs = 0;
    double jitterMs = 0;
    double playoutMs = 50;
    std::string playoutAnchor = "first";
    std::string jitterDist = "uniform";
    double distance = 5;
    double simTime = 10;
    double frameJitter = 0;
    uint32_t frameBytes = 12000;
    uint32_t seed = 1;
    uint32_t run = 1;
    bool abr = false;
    CommandLine cmd(__FILE__);
    cmd.AddValue("link", "csma or wifi", link);
    cmd.AddValue("fps", "Frames per second", fps);
    cmd.AddValue("frameBytes", "JPEG bytes per frame", frameBytes);
    cmd.AddValue("frameJitter", "Uniform relative frame-size variation (default 0)", frameJitter);
    cmd.AddValue("lossP", "RTP datagram loss probability", lossP);
    cmd.AddValue("lossSteps", "Seconds since first capture:probability, comma separated",
                 lossSteps);
    cmd.AddValue("geBurst", "Mean Gilbert-Elliott bad run (0 disables)", geBurst);
    cmd.AddValue("delayMs", "Receiver-side extra delay", delayMs);
    cmd.AddValue("jitterMs", "Symmetric uniform half-width or normal standard deviation", jitterMs);
    cmd.AddValue("playoutMs", "Playout buffer depth in milliseconds", playoutMs);
    cmd.AddValue("playoutAnchor", "first or capture", playoutAnchor);
    cmd.AddValue("jitterDist", "uniform or normal", jitterDist);
    cmd.AddValue("abr", "Enable RR AIMD quality and frame-size control", abr);
    cmd.AddValue("simTime", "Media generation duration, excluding setup and drain", simTime);
    cmd.AddValue("seed", "RNG seed", seed);
    cmd.AddValue("run", "RngRun", run);
    cmd.AddValue("distance", "Wi-Fi STA distance in metres", distance);
    cmd.AddValue("outDir", "Output directory", outDir);
    cmd.Parse(argc, argv);

    const bool finite = std::isfinite(fps) && std::isfinite(lossP) && std::isfinite(geBurst) &&
                        std::isfinite(delayMs) && std::isfinite(jitterMs) &&
                        std::isfinite(playoutMs) && std::isfinite(distance) &&
                        std::isfinite(simTime) && std::isfinite(frameJitter);
    const bool invalidGe = geBurst != 0 &&
                           (geBurst < 1 || (lossP < 1 && lossP / (1 - lossP) > geBurst));
    if ((link != "csma" && link != "wifi") || !finite || fps <= 0 || fps > 1e6 ||
        frameBytes == 0 || frameJitter < 0 || frameJitter >= 1 ||
        frameBytes * (1 + frameJitter) > 0x1000000 || simTime <= 0 || lossP < 0 ||
        lossP > 1 || delayMs < 0 || jitterMs < 0 || playoutMs < 0 || distance < 0 ||
        seed == 0 || invalidGe ||
        (playoutAnchor != "first" && playoutAnchor != "capture") ||
        (jitterDist != "uniform" && jitterDist != "normal"))
    {
        std::cerr << "Invalid simulation parameter (including infeasible GE transitions)\n";
        return 2;
    }

    std::vector<std::pair<double, double>> steps;
    if (!lossSteps.empty())
    {
        std::istringstream input(lossSteps);
        std::string item;
        bool valid = geBurst == 0 && lossSteps.back() != ',';
        while (std::getline(input, item, ','))
        {
            std::istringstream entry(item);
            double time = 0;
            double probability = 0;
            char colon = 0;
            if (!(entry >> time >> colon >> probability) || colon != ':' ||
                !(entry >> std::ws).eof() || !std::isfinite(time) ||
                !std::isfinite(probability) || time < 0 || probability < 0 ||
                probability > 1 || (steps.empty() ? time != 0 : time <= steps.back().first))
            {
                valid = false;
                break;
            }
            steps.emplace_back(time, probability);
        }
        if (!valid || steps.empty())
        {
            std::cerr << "Invalid simulation parameter: lossSteps (requires Bernoulli, "
                         "increasing times starting at 0 and probabilities in [0,1])\n";
            return 2;
        }
    }

    RngSeedManager::SetSeed(seed);
    RngSeedManager::SetRun(run);
    std::filesystem::create_directories(outDir);
    NodeContainer nodes;
    nodes.Create(2);
    NetDeviceContainer devices;
    if (link == "csma")
    {
        CsmaHelper csma;
        csma.SetChannelAttribute("DataRate", StringValue("100Mbps"));
        csma.SetChannelAttribute("Delay", TimeValue(MicroSeconds(1)));
        devices = csma.Install(nodes);
    }
    else
    {
        MobilityHelper mobility;
        Ptr<ListPositionAllocator> positions = CreateObject<ListPositionAllocator>();
        positions->Add(Vector(0, 0, 0));
        positions->Add(Vector(distance, 0, 0));
        mobility.SetPositionAllocator(positions);
        mobility.SetMobilityModel("ns3::ConstantPositionMobilityModel");
        mobility.Install(nodes);
        WifiHelper wifi;
        wifi.SetStandard(WIFI_STANDARD_80211ac);
        wifi.SetRemoteStationManager("ns3::IdealWifiManager");
        YansWifiChannelHelper channel = YansWifiChannelHelper::Default();
        YansWifiPhyHelper phy;
        phy.SetChannel(channel.Create());
        phy.Set("ChannelSettings", StringValue("{0, 80, BAND_5GHZ, 0}"));
        WifiMacHelper mac;
        mac.SetType("ns3::AdhocWifiMac");
        devices = wifi.Install(phy, mac, nodes);
    }
    InternetStackHelper internet;
    internet.Install(nodes);
    Ipv4AddressHelper address;
    address.SetBase("10.1.0.0", "255.255.255.0");
    Ipv4InterfaceContainer interfaces = address.Assign(devices);

    Ptr<ErrorModel> model;
    if (geBurst > 0)
    {
        auto ge = CreateObject<GilbertElliottErrorModel>();
        ge->Configure(lossP, geBurst);
        model = ge;
    }
    else
    {
        auto rate = CreateObject<RateErrorModel>();
        rate->SetUnit(RateErrorModel::ERROR_UNIT_PACKET);
        rate->SetRate(steps.empty() ? lossP : steps.front().second);
        rate->AssignStreams(10);
        model = rate;
        for (const auto& [time, probability] : steps)
        {
            Simulator::Schedule(Seconds(0.2 + time), &RateErrorModel::SetRate,
                                rate, probability);
        }
    }

    // Start at 0.1 s, resolve ARP for 0.1 s, then generate simTime seconds of media.
    const double mediaEnd = 0.2 + simTime;
    const double tailMs = (jitterDist == "normal" ? 12 : 1) * jitterMs;
    const double drain = std::max(1.0, (delayMs + tailMs + playoutMs) / 1000 + 0.1);
    const Time stop = Seconds(mediaEnd + drain);
    auto receiver = CreateObject<RtpVideoReceiver>();
    receiver->Configure(delayMs, jitterMs, playoutMs, outDir, interfaces.GetAddress(0),
                        model, playoutAnchor, jitterDist);
    nodes.Get(1)->AddApplication(receiver);
    receiver->SetStartTime(Seconds(0));
    receiver->SetStopTime(stop);
    auto sender = CreateObject<RtpVideoSender>();
    sender->Configure(interfaces.GetAddress(1), fps, frameBytes, frameJitter,
                      outDir + "/sender.csv", abr, Seconds(simTime));
    sender->SetAbrLogger([receiver](const uint8_t* report) { receiver->LogAbr(report); });
    nodes.Get(0)->AddApplication(sender);
    sender->SetStartTime(Seconds(0.1));
    sender->SetStopTime(stop);

    // Shared CSV names remain unchanged; metadata identifies their one simulator clock.
    std::ofstream args(outDir + "/args.json");
    args << "{\"link\":\"" << link << "\",\"fps\":" << fps
         << ",\"frameBytes\":" << frameBytes << ",\"frameJitter\":" << frameJitter
         << ",\"lossSteps\":\"" << lossSteps << "\",\"lossP\":" << lossP
         << ",\"geBurst\":" << geBurst
         << ",\"delayMs\":" << delayMs << ",\"jitterMs\":" << jitterMs
         << ",\"jitterDist\":\"" << jitterDist << "\""
         << ",\"playoutAnchor\":\"" << playoutAnchor << "\""
         << ",\"playoutMs\":" << playoutMs << ",\"distance\":" << distance
         << ",\"simTime\":" << simTime << ",\"seed\":" << seed << ",\"run\":" << run
         << ",\"abr\":" << (abr ? "true" : "false") << "}\n";
    NS_ABORT_MSG_IF(!args, "Cannot write run arguments");
    args.close();
    Simulator::Stop(stop + NanoSeconds(1));
    Simulator::Run();
    receiver->WriteFrames(sender->GetFrames());
    std::ofstream meta(outDir + "/meta.json");
    meta << "{\"evidence\":\"SIM\",\"ns3_version\":\"3.44\",\"clock\":\"sim\","
            "\"csv_clock_aliases\":{\"mono\":\"sim\",\"rx\":\"sim\"},"
            "\"loss_layer\":\"RTP datagram after UDP\","
            "\"frame_accounting\":\"offline sender manifest join\","
            "\"media_start_ns\":200000000,\"seed\":" << seed << ",\"run\":" << run
         << ",\"delay_clip_count\":" << receiver->GetDelayClipCount() << "}\n";
    NS_ABORT_MSG_IF(!meta, "Cannot write run metadata");
    meta.close();
    Simulator::Destroy();
    return 0;
}
