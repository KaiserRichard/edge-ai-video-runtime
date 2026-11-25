"""JPEG sources. Capture times are local monotonic ns, never sensor-clock values.

CAM1 ABI source: OS repo linux/camera/{README.md,ring.h,ring.cpp}; design note
CAM1_CAMERA_SOURCE.md. No OS files are copied or modified. shm: uses the CAM1
native reader (HEA_CAM_READER_LIB or --shm-library) for acquire loads/fences;
Python mmap is used only to discover candidate IDs, never to trust pixel copies.
The ABI has no timestamps: its capture time here is verified-copy acquisition.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import io
import mmap
import os
from pathlib import Path
import re
import select
import struct
import sys
import time

MAX_JPEG = 0x1000000


@dataclass(frozen=True)
class CapturedFrame:
    frame_id: int
    jpeg: bytes
    t_capture_mono_ns: int
    quality: int | None = None


def _jpeg(image, quality):
    out = io.BytesIO()
    image.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def _quality(q):
    if not 1 <= q <= 95:
        raise ValueError("JPEG quality must be in 1..95")


class SyntheticSource:
    def __init__(self, width=320, height=240, quality=75):
        from PIL import Image, ImageDraw, ImageFont
        _quality(quality)
        if not 1 <= width <= 4096 or not 1 <= height <= 4096:
            raise ValueError("dimensions must be in 1..4096")
        self.width, self.height, self.quality = width, height, quality
        # Initialize lazy Pillow modules/fonts before the sender starts its clock.
        Image.preinit()
        self.image_module, self.draw_module = Image, ImageDraw
        self.font = ImageFont.load_default()
        self.frame_id = 0

    def read(self, timeout=0.0):
        captured = time.monotonic_ns()
        image = self.image_module.new("RGB", (self.width, self.height))
        draw = self.draw_module.Draw(image)
        colors = ("white", "yellow", "cyan", "green", "magenta", "red", "blue", "black")
        for i, color in enumerate(colors):
            draw.rectangle((i * self.width // 8, 0, (i + 1) * self.width // 8,
                            self.height - 1), fill=color)
        x = (self.frame_id * 7) % self.width
        draw.line((x, 0, x, self.height - 1), fill="black", width=3)
        draw.rectangle((0, 0, min(self.width - 1, 160), 24), fill="black")
        draw.text((5, 5), f"FRAME {self.frame_id:08d}", fill="white", font=self.font)
        result = CapturedFrame(self.frame_id, _jpeg(image, self.quality), captured, self.quality)
        self.frame_id += 1
        return result

    def close(self):
        pass


class JpegDirectorySource:
    """Replay sorted *.jpg/*.jpeg cyclically; preserve the original JPEG bytes."""
    def __init__(self, directory):
        self.files = sorted(p for p in Path(directory).iterdir()
                            if p.is_file() and p.suffix.lower() in (".jpg", ".jpeg"))
        if not self.files:
            raise ValueError("JPEG directory contains no .jpg/.jpeg files")
        self.frame_id = 0

    def read(self, timeout=0.0):
        captured = time.monotonic_ns()
        data = self.files[self.frame_id % len(self.files)].read_bytes()
        if not data.startswith(b"\xff\xd8") or not data.endswith(b"\xff\xd9") or len(data) > MAX_JPEG:
            raise ValueError("invalid or oversized JPEG file")
        result = CapturedFrame(self.frame_id, data, captured)
        self.frame_id += 1
        return result

    def close(self):
        pass


class MjpegPipeSource:
    """Incremental SOI/EOI framing of rpicam-vid --codec mjpeg -o -.

    read(timeout) returns None while waiting and raises EOFError at clean EOF;
    truncated frames raise ValueError. The input stream belongs to the caller.
    """
    def __init__(self, stream=None):
        self.stream = sys.stdin.buffer if stream is None else stream
        self.buffer = bytearray()
        self.frame_id = 0
        self.eof = False

    def read(self, timeout=0.0):
        deadline = time.monotonic() + timeout
        reads = 0
        while True:
            start = self.buffer.find(b"\xff\xd8")
            if start < 0:
                self.buffer[:] = self.buffer[-1:] if self.buffer.endswith(b"\xff") else b""
            else:
                del self.buffer[:start]
                end = self.buffer.find(b"\xff\xd9", 2)
                if end >= 0:
                    if end + 2 > MAX_JPEG:
                        raise ValueError("MJPEG frame exceeds payload format limit")
                    data = bytes(self.buffer[:end + 2])
                    del self.buffer[:end + 2]
                    result = CapturedFrame(self.frame_id, data, time.monotonic_ns())
                    self.frame_id += 1
                    return result
            if len(self.buffer) > MAX_JPEG:
                raise ValueError("MJPEG frame exceeds payload format limit")
            if self.eof:
                if start >= 0:
                    raise ValueError("truncated MJPEG frame at EOF")
                raise EOFError
            try:
                fd = self.stream.fileno()
            except (AttributeError, io.UnsupportedOperation):
                chunk = self.stream.read(65536)
            else:
                if reads and time.monotonic() >= deadline:
                    return None
                remaining = max(0.0, deadline - time.monotonic())
                if not select.select([fd], [], [], remaining)[0]:
                    return None
                chunk = os.read(fd, 65536)
                reads += 1
            if not chunk:
                self.eof = True
            else:
                self.buffer.extend(chunk)

    def close(self):
        pass


def _ring_layout(data, size):
    """Validate the documented little-endian CAM1 v1 header."""
    if len(data) < 64:
        raise ValueError("truncated CAM1 header")
    magic, version, width, height, slots, pixels, stride, ready = struct.unpack_from("<8I", data)
    if magic != 0x43414548 or version != 1 or ready != 1:
        raise ValueError("CAM1 ring not ready or unsupported ABI")
    if not (1 <= width <= 4096 and 1 <= height <= 4096 and 1 <= slots <= 64):
        raise ValueError("invalid CAM1 dimensions/slot count")
    if (pixels != width * height * 3 or stride != ((16 + pixels + 63) & ~63)
            or size != 64 + slots * stride or size > 256 * 1024 * 1024):
        raise ValueError("invalid CAM1 ring layout")
    return width, height, slots, pixels, stride


class ShmSource:
    """Read the newest unseen CAM1 frame; skip busy, torn and overwritten slots.

    Requires the OS project's libhea_camera.so/.dylib only when selected. Its
    native bounded copy enforces the seqlock on ARM as well as x86. No spin lock,
    unlink, resource tracker, or dependency on a running camera for other sources.
    """
    def __init__(self, name, quality=75, library=None):
        _quality(quality)
        name = name.removeprefix("/")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", name):
            raise ValueError("invalid CAM1 shared-memory name")
        library = library or os.environ.get("HEA_CAM_READER_LIB")
        if not library:
            raise RuntimeError("shm: requires --shm-library or HEA_CAM_READER_LIB pointing to CAM1 libhea_camera")
        self.lib = ctypes.CDLL(str(library))
        self.lib.hea_camera_open.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint32),
                                            ctypes.POINTER(ctypes.c_uint32)]
        self.lib.hea_camera_open.restype = ctypes.c_void_p
        self.lib.hea_camera_read.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                            ctypes.POINTER(ctypes.c_uint8), ctypes.c_size_t]
        self.lib.hea_camera_read.restype = ctypes.c_int
        self.lib.hea_camera_close.argtypes = [ctypes.c_void_p]
        self.lib.hea_camera_close.restype = None
        self.lib.hea_camera_error.restype = ctypes.c_char_p
        path = Path("/tmp" if sys.platform == "darwin" else "/dev/shm") / (
            "hea-cam-" + name if sys.platform == "darwin" else name)
        self.mapping = None
        self.handle = None
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
            try:
                size = os.fstat(fd).st_size
                header = os.read(fd, 64)
                self.width, self.height, self.slots, self.pixels, self.stride = _ring_layout(header, size)
                self.mapping = mmap.mmap(fd, size, access=mmap.ACCESS_READ)
            finally:
                os.close(fd)
            w, h = ctypes.c_uint32(), ctypes.c_uint32()
            self.handle = self.lib.hea_camera_open(name.encode(), ctypes.byref(w), ctypes.byref(h))
            if not self.handle:
                raise RuntimeError(self.lib.hea_camera_error().decode())
            if (w.value, h.value) != (self.width, self.height):
                raise ValueError("CAM1 ring changed while opening")
            self.rgb = (ctypes.c_uint8 * self.pixels)()
        except BaseException:
            self.close()
            raise
        self.quality = quality
        self.last_frame = -1
        self.torn = self.overwritten = 0

    def read(self, timeout=0.0):
        from PIL import Image
        deadline = time.monotonic() + timeout
        while True:
            candidates = []
            for index in range(self.slots):
                seq, frame_id = struct.unpack_from("<QI", self.mapping, 64 + index * self.stride)
                if seq and not seq & 1 and frame_id > self.last_frame:
                    candidates.append(frame_id)
            if candidates:
                frame_id = max(candidates)
                status = self.lib.hea_camera_read(self.handle, frame_id, self.rgb, self.pixels)
                if status == 0:
                    captured = time.monotonic_ns()
                    self.last_frame = frame_id
                    image = Image.frombytes("RGB", (self.width, self.height), bytes(self.rgb))
                    return CapturedFrame(frame_id, _jpeg(image, self.quality), captured, self.quality)
                if status == 1:
                    self.overwritten += 1
                elif status == 2:
                    self.torn += 1
                else:
                    raise RuntimeError(self.lib.hea_camera_error().decode())
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            time.sleep(min(remaining, 0.002))

    def close(self):
        if self.handle:
            self.lib.hea_camera_close(self.handle)
            self.handle = None
        if self.mapping is not None:
            self.mapping.close()
            self.mapping = None


def open_source(spec="synthetic", *, quality=75, width=320, height=240,
                jpeg_dir=None, stream=None, shm_library=None):
    if spec == "synthetic":
        return SyntheticSource(width, height, quality)
    if spec == "jpegdir" or spec.startswith("jpegdir:"):
        directory = spec.partition(":")[2] or jpeg_dir
        if directory is None:
            raise ValueError("jpegdir requires --jpeg-dir or jpegdir:PATH")
        return JpegDirectorySource(directory)
    if spec == "mjpeg-pipe":
        return MjpegPipeSource(stream)
    if spec.startswith("shm:"):
        return ShmSource(spec[4:], quality, shm_library)
    raise ValueError(f"unknown source: {spec}")
