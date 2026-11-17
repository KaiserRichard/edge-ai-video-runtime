"""Queued edge inference for decoded RTP video frames.

The model is the MobileNetV2 ONNX file used by ``hw/os_inference.py``. Its
default location is ``offline-bundle/mobilenetv2-12.onnx``; pass ``model``
explicitly when it lives elsewhere. Inference and queue timestamps use the
edge receiver's monotonic clock.
"""

from __future__ import annotations

from collections import deque
import csv
from dataclasses import dataclass
import io
import math
from pathlib import Path
import threading
import time


AI_FIELDS = (
    "frame_id", "rtp_ts", "policy", "t_enqueue_rx_ns", "t_start_rx_ns",
    "t_done_rx_ns", "class_id", "confidence", "status",
)


@dataclass
class _Job:
    frame_id: int
    rtp_ts: int
    jpeg_bytes: bytes
    t_complete_rx_ns: int
    t_enqueue_rx_ns: int
    t_start_rx_ns: int = 0


class _SyntheticModel:
    def __init__(self, service_ms: float):
        self.service_ms = service_ms

    def infer(self, jpeg_bytes: bytes) -> tuple[int, float]:
        time.sleep(self.service_ms / 1000)
        return 0, 1.0


class _OnnxModel:
    def __init__(self, model_path: str | Path, threads: int):
        try:
            import numpy as np
            import onnxruntime as ort
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("real inference requires numpy, Pillow, and onnxruntime") from exc
        path = Path(model_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"MobileNetV2 ONNX model not found: {path}")
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self.session = ort.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"]
        )
        inputs = self.session.get_inputs()
        if len(inputs) != 1 or inputs[0].type != "tensor(float)":
            raise ValueError("MobileNetV2 must have one float32 input")
        shape = inputs[0].shape
        if len(shape) != 4 or any(
            isinstance(actual, int) and actual != expected
            for actual, expected in zip(shape, (1, 3, 224, 224))
        ):
            raise ValueError("MobileNetV2 input must accept 1x3x224x224")
        self.np, self.Image = np, Image
        self.input_name = inputs[0].name
        self.output_name = self.session.get_outputs()[0].name

    def infer(self, jpeg_bytes: bytes) -> tuple[int, float]:
        np = self.np
        with self.Image.open(io.BytesIO(jpeg_bytes)) as source:
            image = source.convert("RGB").resize((224, 224), self.Image.Resampling.BILINEAR)
            rgb = np.asarray(image, dtype=np.float32) / np.float32(255)
        rgb -= np.array([0.485, 0.456, 0.406], dtype=np.float32)
        rgb /= np.array([0.229, 0.224, 0.225], dtype=np.float32)
        tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1)[None, ...])
        scores = np.asarray(
            self.session.run([self.output_name], {self.input_name: tensor})[0],
            dtype=np.float64,
        ).reshape(-1)
        if scores.size != 1000 or not np.isfinite(scores).all():
            raise ValueError("expected 1000 finite MobileNetV2 ImageNet logits")
        class_id = int(np.argmax(scores))
        weights = np.exp(scores - scores.max())
        confidence = float(weights[class_id] / weights.sum())
        return class_id, confidence


class EdgeAI:
    """Single-worker inference stage with bounded FIFO or latest-value queue.

    ``model`` is an ONNX path, or ``"synthetic"`` for deterministic test
    inference. ``latest`` replaces an already-waiting frame; FIFO drops a new
    frame when its bounded queue is full. ``skipped`` counts both cases.
    """

    def __init__(self, policy, model, threads, send_result, *,
                 service_ms=0, queue_size=8, ai_csv="ai.csv", telemetry=None):
        self.telemetry = telemetry
        if policy not in ("fifo", "latest"):
            raise ValueError("policy must be 'fifo' or 'latest'")
        if not isinstance(threads, int) or threads < 1:
            raise ValueError("threads must be a positive integer")
        if not isinstance(queue_size, int) or queue_size < 1:
            raise ValueError("queue_size must be a positive integer")
        if not math.isfinite(service_ms) or service_ms < 0:
            raise ValueError("service_ms must be finite and nonnegative")
        if not callable(send_result):
            raise TypeError("send_result must be callable")
        self.policy = policy
        self.send_result = send_result
        self.model = (_SyntheticModel(service_ms) if model == "synthetic"
                      else _OnnxModel(model, threads))
        self.queue_size = queue_size
        self.skipped = 0
        self.completed = 0
        self.failed = 0
        self.max_waiting = 0
        self._queue: deque[_Job] = deque()
        self._condition = threading.Condition()
        self._csv_lock = threading.Lock()
        self._closing = False
        self._csv_handle = Path(ai_csv).open("w", newline="", encoding="utf-8")
        self._csv = csv.DictWriter(self._csv_handle, fieldnames=AI_FIELDS)
        self._csv.writeheader()
        self._csv_handle.flush()
        self._worker = threading.Thread(target=self._run, name="rtp-edge-ai", daemon=True)
        self._worker.start()

    @property
    def waiting(self):
        with self._condition:
            return len(self._queue)

    def _write(self, job, *, start="", done="", class_id="", confidence="", status):
        with self._csv_lock:
            self._csv.writerow({
                "frame_id": job.frame_id, "rtp_ts": job.rtp_ts, "policy": self.policy,
                "t_enqueue_rx_ns": job.t_enqueue_rx_ns, "t_start_rx_ns": start,
                "t_done_rx_ns": done, "class_id": class_id, "confidence": confidence,
                "status": status,
            })
            self._csv_handle.flush()
            if status == "ok" and self.telemetry is not None:
                self.telemetry.emit("ai", dict(frame_id=job.frame_id, rtp_ts=job.rtp_ts,
                    policy=self.policy, queue_ms=(start - job.t_enqueue_rx_ns) / 1e6,
                    inference_ms=(done - start) / 1e6, class_id=class_id, confidence=confidence))

    def submit(self, frame_id, rtp_ts, jpeg_bytes, t_complete_rx_ns):
        """Enqueue a complete JPEG frame without waiting for inference."""
        if not isinstance(jpeg_bytes, bytes):
            raise TypeError("jpeg_bytes must be bytes")
        now = time.monotonic_ns()
        job = _Job(frame_id, rtp_ts, jpeg_bytes, t_complete_rx_ns, now)
        with self._condition:
            if self._closing:
                raise RuntimeError("EdgeAI is closed")
            if self.policy == "latest" and self._queue:
                skipped = self._queue.pop()
                self._write(skipped, status="skipped")
                self.skipped += 1
            elif len(self._queue) >= self.queue_size:
                self._write(job, status="skipped")
                self.skipped += 1
                return False
            self._queue.append(job)
            self.max_waiting = max(self.max_waiting, len(self._queue))
            self._condition.notify()
        return True

    def _run(self):
        while True:
            with self._condition:
                self._condition.wait_for(lambda: self._queue or self._closing)
                if not self._queue:
                    return
                job = self._queue.popleft()
            job.t_start_rx_ns = time.monotonic_ns()
            try:
                class_id, confidence = self.model.infer(job.jpeg_bytes)
                t_done = time.monotonic_ns()
                # AIRS carries confidence in one byte; retain the float in ai.csv.
                confidence_byte = max(0, min(255, round(confidence * 255)))
                self.send_result(job.rtp_ts, job.frame_id, class_id,
                                 confidence_byte, (t_done // 1000) & 0xFFFFFFFF)
            except Exception:
                t_done = time.monotonic_ns()
                with self._condition:
                    self.failed += 1
                self._write(job, start=job.t_start_rx_ns, done=t_done, status="error")
            else:
                with self._condition:
                    self.completed += 1
                self._write(job, start=job.t_start_rx_ns, done=t_done,
                            class_id=class_id, confidence=confidence, status="ok")

    def close(self):
        """Drain queued work and close the CSV after the worker exits."""
        with self._condition:
            if not self._closing:
                self._closing = True
                self._condition.notify_all()
        self._worker.join()
        self._csv_handle.close()


def _run_synthetic_demo(policy: str, service_ms: float, frame_period_ms: float,
                        frames: int, queue_size: int, output: str) -> None:
    results = []
    edge = EdgeAI(policy, "synthetic", 1,
                  lambda rtp_ts, frame_id, class_id, confidence, done_us:
                  results.append((frame_id, class_id, confidence, done_us)),
                  service_ms=service_ms, queue_size=queue_size, ai_csv=output)
    try:
        for frame_id in range(frames):
            edge.submit(frame_id, frame_id * 3000, b"synthetic", time.monotonic_ns())
            time.sleep(frame_period_ms / 1000)
    finally:
        edge.close()
    print(f"policy={policy} submitted={frames} completed={edge.completed} "
          f"skipped={edge.skipped} max_waiting={edge.max_waiting} results={len(results)}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("synthetic",), default="synthetic")
    parser.add_argument("--policy", choices=("fifo", "latest"), default="latest")
    parser.add_argument("--service-ms", type=float, default=100)
    parser.add_argument("--frame-period-ms", type=float, default=33.333)
    parser.add_argument("--frames", type=int, default=30)
    parser.add_argument("--queue-size", type=int, default=8)
    parser.add_argument("--ai-csv", default="ai.csv")
    args = parser.parse_args()
    _run_synthetic_demo(args.policy, args.service_ms, args.frame_period_ms,
                        args.frames, args.queue_size, args.ai_csv)
