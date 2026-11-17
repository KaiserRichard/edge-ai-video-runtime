"""Seeded illustrative telemetry, never evidence from the hardware campaign."""
import asyncio
from collections import deque
import math
import random

from .schema import event


class QueueComparison:
    """Same arrivals, equal fixed service, bounded FIFO(8) and latest slot(1)."""
    def __init__(self, service_ms=50):
        self.service = service_ms / 1000
        self.next_arrival = 0.0
        self.queues = {"fifo": deque(), "latest": deque()}
        self.jobs = {"fifo": None, "latest": None}
        self.results = {"fifo": 0.0, "latest": 0.0}

    def advance(self, now):
        # Process arrival and completion events in clock order; a result age is
        # since that result's input frame, not since inference completion.
        while True:
            completion = min((job[1] for job in self.jobs.values() if job), default=math.inf)
            tick = min(self.next_arrival, completion)
            if tick > now + 1e-10:
                break
            for policy, job in self.jobs.items():
                if job and job[1] <= tick + 1e-10:
                    self.results[policy] = job[0]
                    self.jobs[policy] = None
            if self.next_arrival <= tick + 1e-10:
                for policy, queue in self.queues.items():
                    if policy == "latest":
                        queue.clear()
                    if len(queue) < 8:
                        queue.append(tick)
                self.next_arrival += 1 / 30
            for policy, queue in self.queues.items():
                if self.jobs[policy] is None and queue:
                    self.jobs[policy] = (queue.popleft(), tick + self.service)
        return {"fifo_age_ms": (now - self.results["fifo"]) * 1000,
                "latest_age_ms": (now - self.results["latest"]) * 1000,
                "fifo_queue": len(self.queues["fifo"]), "latest_queue": len(self.queues["latest"]),
                "service_ms": self.service * 1000}


class Synthetic:
    phases = ("Clean Ethernet", "Random loss 5%", "Burst loss 5%", "Jitter / D=20 ms", "Jitter / D=100 ms", "ABR loss step 15%", "Recovery / queue comparison")

    def __init__(self, seed=11):
        self.rng = random.Random(seed)
        self.seq = 65500
        self.frame = 0
        self.kernel_drops = 0
        self.comparison = QueueComparison()
        self.rr_received = self.rr_expected = 0

    def tick(self, t):
        phase = int(t // 12) % len(self.phases)
        phase_t = t % 12
        p = (0, .05, .05, 0, 0, .15, 0)[phase]
        jitter = 20 if phase in (3, 4) else 0
        delay = 20 if phase == 3 else 100 if phase == 4 else 50
        messages = []

        def emit(kind, data, source="receiver", profile="cn"):
            messages.append(event(kind, data, t, source, profile, "synthetic"))

        damaged = False
        # Three 30 fps input frames per 100 ms telemetry tick, ten packets each.
        for local in range(3):
            frame_id = self.frame
            ts = (frame_id * 3000) % 2**32
            burst = phase == 2 and self.rng.random() < .125
            frame_lost = False
            for packet in range(10):
                lost = (burst and packet < 4) if phase == 2 else self.rng.random() < p
                self.rr_expected += 1
                if lost:
                    self.kernel_drops += 1
                    frame_lost = True
                else:
                    self.rr_received += 1
                    emit("packet", {"seq": self.seq % 65536, "rtp_ts": ts, "frame_id": frame_id,
                                    "bytes": 300, "jitter_ms": .14 + jitter * (.3 + .1 * math.sin(t)),
                                    "frame_jitter_ms": .03 + jitter * (.55 + .1 * math.cos(t))})
                self.seq += 1
            offset = self.rng.gauss(20, jitter) - delay
            status = "lost" if frame_lost else "late" if offset > 0 else "ok"
            damaged |= status != "ok"
            emit("frame", {"frame_id": frame_id, "rtp_ts": ts, "status": status,
                           "arrival_offset_ms": offset, "buffer_frames": max(0, round(delay / 33.3))})
            self.frame += 1
        queue = self.comparison.advance(t)
        emit("queue", queue)
        infer = 12 + self.rng.random() * 4
        total = 4 + delay + 1 + infer + 2
        emit("ai", {"frame_id": self.frame - 1, "rtp_ts": (self.frame - 1) * 3000 % 2**32,
                    "policy": "latest", "queue_ms": 1, "inference_ms": infer,
                    "class_id": 281, "confidence": .87, "label": "tabby cat · synthetic label"})
        emit("result", {"frame_id": self.frame - 1, "rtp_ts": (self.frame - 1) * 3000 % 2**32,
                        "latency_ms": total, "capture_send_ms": 4, "network_playout_ms": delay + 2,
                        "queue_ms": 1, "inference_ms": infer}, "pi")
        netem = f"{self.phases[phase]} · loss {p * 100:g}% · jitter {jitter} ms · D {delay} ms"
        quality = max(25, 75 - int(phase_t // 2) * 10) if phase == 5 else min(75, 25 + int(phase_t // 2) * 10) if phase == 6 else 75
        decision = "down" if phase == 5 else "up" if phase == 6 else "hold"
        emit("sender", {"bitrate_mbps": .72 * quality / 75, "quality": quality, "fps": 30,
                        "step": (75 - quality) // 10, "decision": decision, "netem": netem,
                        "netem_jitter_ms": jitter}, "pi")
        if self.frame % 30 == 3:
            fraction = min(255, round((self.rr_expected - self.rr_received) / max(1, self.rr_expected) * 256))
            for kind, source, direction in (("SR", "pi", "tx"), ("RR", "receiver", "tx"), ("APP", "receiver", "tx")):
                emit("rtcp", {"kind": kind, "direction": direction, "fraction_lost": fraction,
                              "jitter_ms": .14 + jitter * .4, "rtt_ms": 2.5 + jitter}, source)
            self.rr_received = self.rr_expected = 0
        hw = {"temperature_c": 52 + 4 * math.sin(t / 20), "throttled": 0, "cpu_pct": 38,
              "cpu_cores": [32 + 10 * math.sin(t), 75, 30, 20], "rssi_dbm": -53,
              "tx_mbps": 144, "kernel_drops": self.kernel_drops, "netem": netem, "netem_jitter_ms": jitter}
        emit("hardware", hw, "pi")
        emit("hardware", hw, "pi", "os")
        cycle = t % 30
        state = "FRESH" if cycle < 16 else "HOLD" if cycle < 18 else "FAILSAFE"
        fault = "bridge stopped (simulated)" if 16 <= cycle < 16.1 else "manual rearm (simulated)" if cycle < .1 else ""
        condition = ("idle-P0", "stress-P0", "idle-P1", "stress-P1")[int(cycle // 7.5)]
        emit("os", {"state": state, "fifo_age_ms": queue["fifo_age_ms"], "latest_age_ms": queue["latest_age_ms"],
                    "inference_ms": infer + (80 if condition.startswith("stress") else 0),
                    "condition": condition, "fault": fault,
                    "link_active": cycle < 16}, "bridge", "os")
        return messages, self.phases[phase], damaged


async def generate(hub, seed=11):
    source = Synthetic(seed)
    start = asyncio.get_running_loop().time()
    tick = 0
    supervisor = {}
    while True:
        t = tick / 40
        if tick % 4 == 0:
            messages, phase, _ = source.tick(t)
            hub.status = f"synthetic · {phase}"
            supervisor = next(m["data"] for m in messages if m["type"] == "os")
        else:
            # 40 Hz age observations avoid aliasing the fixed 50 ms service
            # into a flat line at exactly 10 Hz. Packet/hardware telemetry stays
            # at 10 Hz; the websocket still batches at 10 Hz.
            queue = source.comparison.advance(t)
            os_data = {k: v for k, v in supervisor.items() if k not in ("inference_ms", "condition", "fault")}
            os_data.update(fifo_age_ms=queue["fifo_age_ms"], latest_age_ms=queue["latest_age_ms"])
            messages = [event("queue", queue, t, session="synthetic"),
                        event("os", os_data, t, "bridge", "os", "synthetic")]
        for message in messages:
            hub.publish(message)
        tick += 1
        await asyncio.sleep(max(0, start + tick / 40 - asyncio.get_running_loop().time()))
