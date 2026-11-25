#!/usr/bin/env python3
"""Portable host evidence. No third-party dependencies and no hardware access.

Run after make all:
  python3 tests/attitude_evidence.py
PBMs come directly from the production C renderer. PNGs only scale those bits
and add a title using the existing font, on opaque white for print readability.
The fake A/B timings describe the host scheduler, never the shared Pi I2C bus.
"""
import csv
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT.parents[1] / 'docs' / 'img'
BUILD = ROOT / 'build'


def png(path, pixels, width, height):
    def chunk(tag, data):
        return struct.pack('!I', len(data)) + tag + data + struct.pack('!I', zlib.crc32(tag + data))
    raw = b''.join(b'\0' + bytes(pixels[y*width:(y+1)*width]) for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 0, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


def previews():
    OUT.mkdir(parents=True, exist_ok=True)
    table = (ROOT / 'oled.c').read_text().split('static const uint8_t font[59][5] = {')[1].split('};')[0]
    font = bytes(int(h, 16) for h in re.findall(r'0x([0-9A-Fa-f]{2})', table))
    manifest = []
    for name, angles in [('level', (0, 0, 0)), ('roll30', (30, 0, 0)), ('pitch45', (0, 45, 0)),
                         ('yaw90', (0, 0, 90)), ('mixed', (30, -25, 60)), ('inverted', (180, 0, 0))]:
        stem = OUT / ('attitude_' + name)
        subprocess.run([str(BUILD/'attitude_preview'), *map(str, angles), str(stem.with_suffix('.pbm'))], check=True)
        tokens = stem.with_suffix('.pbm').read_text().split()
        assert tokens[:3] == ['P1', '128', '64']
        bits = ''.join(tokens[3:])
        width, height = 512, 312
        pixels = bytearray([255])*(width*height)
        title = f'{name.upper()} R{angles[0]:+04} P{angles[1]:+04} Y{angles[2]:+04} DEG'
        for col, char in enumerate(title):
            glyph = font[(ord(char)-32)*5:(ord(char)-32)*5+5]
            for x, value in enumerate(glyph):
                for y in range(7):
                    if (value >> y) & 1:
                        for dy in range(2):
                            for dx in range(2):
                                pixels[(10+2*y+dy)*width+8+col*12+2*x+dx] = 0
        coords = []
        for i, value in enumerate(bits):
            if value == '1':
                x, y = i % 128, i // 128
                coords.append((x, y))
                for dy in range(4):
                    for dx in range(4):
                        pixels[(40+4*y+dy)*width+4*x+dx] = 0
        png(stem.with_suffix('.png'), pixels, width, height)
        manifest.append(dict(name=name, rpy_deg=angles, on_pixels=len(coords),
                             bbox_xyxy=[min(x for x,y in coords), min(y for x,y in coords),
                                        max(x for x,y in coords), max(y for x,y in coords)]))
    (OUT/'attitude_previews.json').write_text(json.dumps(manifest, indent=2)+'\n')


def timing_pair():
    out = ROOT.parents[1] / 'docs' / 'attitude_host'
    out.mkdir(exist_ok=True)
    results = {'evidence': 'COMPUTED synthetic host fake buses; no physical shared-bus contention',
               'host': os.uname().sysname + ' ' + os.uname().release, 'runs': []}
    for enabled in (False, True):
        name = 'on' if enabled else 'off'
        shm = f'attitude_evidence_{os.getpid()}_{name}'
        with (out/f'imu_{name}.stderr.log').open('w') as err:
            command = [str(BUILD/'hea_imu'), '--backend', 'fake', '--duration', '4',
                       '--shm', shm, '--bias-seconds', '0.1', '--csv', str(out/f'imu_{name}.csv'),
                       '--summary', str(out/f'imu_{name}.json')]
            imu = subprocess.Popen(command, stderr=err)
            try:
                if enabled:
                    deadline = time.monotonic()+5
                    while time.monotonic() < deadline:
                        try:
                            data = Path('/dev/shm', shm).read_bytes()[:64]
                            if struct.unpack_from('Q',data,32)[0] > 0:
                                break
                        except FileNotFoundError:
                            pass
                        time.sleep(0.01)
                    else:
                        raise RuntimeError('IMU ring not published within 5 seconds')
                    with (out/'oled.stderr.log').open('w') as oled_err:
                        subprocess.run([str(BUILD/'hea_oled'), '--backend', 'fake', '--mode', 'attitude',
                                        '--fps', '20', '--duration', '3', '--imu-shm', shm,
                                        '--csv', str(out/'oled.csv')], stderr=oled_err, check=True, timeout=10)
                if imu.wait(timeout=10):
                    raise RuntimeError('IMU failed; see stderr log')
            finally:
                if imu.poll() is None:
                    imu.terminate()
                    imu.wait(timeout=5)
        summary = json.loads((out/f'imu_{name}.json').read_text())
        results['runs'].append(dict(display=enabled, samples=summary['samples'],
                                    release_lateness=summary['timing']['release_lateness'],
                                    missed_releases=summary['timing']['missed_releases']))
    with (out/'oled.csv').open(newline='') as f:
        frames = list(csv.DictReader(f))
    results['display'] = dict(frames=len(frames), achieved_fps=float(frames[-1]['achieved_fps']),
                              bytes=sum(int(r['bytes']) for r in frames))
    (out/'comparison.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    previews()
    timing_pair()
