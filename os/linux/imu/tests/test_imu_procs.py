"""Process-level tests for hea_imu / hea_oled with the fake I2C backend.

All data is SYNTHETIC (fake register file); timing numbers from a host run are
not Pi evidence and are only checked for internal consistency.
"""
import csv
import json
import os
import signal
import struct
import subprocess
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, '..', 'build')
IMU = os.path.join(BUILD, 'hea_imu')
OLED = os.path.join(BUILD, 'hea_oled')


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=60, **kw)


class ImuProcessTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.shm = 'hea_imu_pt_%d' % os.getpid()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fake_run_csv_summary(self):
        out_csv = os.path.join(self.dir, 'imu.csv')
        summary = os.path.join(self.dir, 'imu_summary.json')
        p = run([IMU, '--backend', 'fake', '--count', '100', '--rate-hz', '200', '--shm', self.shm,
                 '--csv', out_csv, '--summary', summary])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('IMU sensor map, accel 0x18 (id 0x1E), gyro 0x68 (id 0x0F)', p.stderr)
        with open(out_csv, newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 100)
        self.assertEqual([int(r['index']) for r in rows], list(range(100)))
        for r in rows:
            self.assertEqual(int(r['flags']) & 3, 3)           # acc_new and gyro_new
            self.assertLess(abs(float(r['roll_deg'])), 21.0)   # synthetic +-20 deg motion
            self.assertGreaterEqual(int(r['t_wake_ns']), int(r['t_release_ns']))
            self.assertEqual(int(r['lateness_ns']), int(r['t_wake_ns']) - int(r['t_release_ns']))
        az = [float(r['az_g']) for r in rows]
        self.assertTrue(all(0.9 < v <= 1.0001 for v in az))
        with open(summary) as f:
            s = json.load(f)
        self.assertEqual(s['map'], 'imu')
        self.assertEqual(s['samples'], 100)
        self.assertEqual(s['status'], 'OK')
        self.assertEqual(s['timing']['releases'], 100)
        self.assertEqual(s['timing']['period_ns'], 5000000)
        self.assertEqual(s['timing']['release_lateness']['count'], 100)
        self.assertEqual(s['timing']['period_jitter']['count'], 99)
        self.assertEqual(s['config'], {'acc_range_g': 6, 'acc_odr_hz': 400.0, 'gyro_range_dps': 500,
                                       'gyro_bw_code': 3})
        self.assertIn('requested', s['scheduling'])
        self.assertGreater(s['attitude']['bias_samples'], 300)
        self.assertEqual(s['attitude']['bias_dps'], [0, 0, 0])
        for row in rows:
            self.assertAlmostEqual(sum(float(row[k])**2 for k in ('qw','qx','qy','qz')), 1, places=5)
        self.assertFalse(os.path.exists('/dev/shm/' + self.shm))   # owner unlinked the ring

    def test_invensense_map_and_probe_only(self):
        p = run([IMU, '--backend', 'fake', '--map', 'invensense', '--probe-only'])
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn('invensense map', p.stderr)

    def test_clear_errors(self):
        p = run([IMU, '--backend', 'fake', '--fake-missing-gyro', '--map', 'imu', '--probe-only'])
        self.assertEqual(p.returncode, 3)
        self.assertIn('only the accelerometer die answered', p.stderr)
        p = run([IMU, '--bus', os.path.join(self.dir, 'no-i2c'), '--probe-only'])
        self.assertEqual(p.returncode, 1)
        self.assertIn('cannot open', p.stderr)
        p = run([IMU, '--backend', 'fake', '--acc-range-g', '5'])
        self.assertEqual(p.returncode, 2)
        self.assertIn('--acc-range-g must be', p.stderr)
        p = run([IMU, '--rate-hz', '5'])
        self.assertEqual(p.returncode, 2)
        p = run([OLED, '--backend', 'fake', '--addr', '0x3D', '--once', '--bus', '/dev/null'])
        self.assertEqual(p.returncode, 0, p.stderr)  # fake device follows --addr

    def test_oled_reads_run_dir_and_ring(self):
        run_dir = os.path.join(self.dir, 'run')
        os.mkdir(run_dir)
        with open(os.path.join(run_dir, 'mcu_status.csv'), 'w') as f:
            f.write('seq,version,t_rx_pi_ns,mcu_us,state,missed_heartbeats\n1,3,5,1,2,0\n')
        with open(os.path.join(run_dir, 'source.csv'), 'w') as f:
            f.write('frame_id,t_input_ns,status\n')
            for i in range(31):
                f.write('%d,%d,sent\n' % (i, 10**9 + i * 50_000_000))
        with open(os.path.join(run_dir, 'bridge.csv'), 'w') as f:
            f.write('seq,frame_id,t_input_ns,t_done_ns,t_send_ns\n0,0,100,30000100,30000200\n')
        imu = subprocess.Popen([IMU, '--backend', 'fake', '--duration', '3', '--rate-hz', '200',
                                '--bias-seconds', '0',
                                '--shm', self.shm, '--csv', os.path.join(self.dir, 'imu.csv')],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.time() + 5
            while not os.path.exists('/dev/shm/' + self.shm) and time.time() < deadline:
                time.sleep(0.02)
            time.sleep(0.2)
            frame = os.path.join(self.dir, 'frame.pbm')
            oled_csv = os.path.join(self.dir, 'oled.csv')
            p = run([OLED, '--backend', 'fake', '--run-dir', run_dir, '--imu-shm', self.shm, '--count', '3',
                     '--rate-hz', '5', '--max-age-s', '0', '--frame-out', frame, '--csv', oled_csv])
            self.assertEqual(p.returncode, 0, p.stderr)
        finally:
            _, imu_err = imu.communicate(timeout=10)
        self.assertEqual(imu.returncode, 0, imu_err)
        with open(oled_csv, newline='') as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[-1]['state'], 'HOLD')
        self.assertAlmostEqual(float(rows[-1]['cam_fps']), 20.0, places=3)
        self.assertAlmostEqual(float(rows[-1]['infer_ms']), 30.0, places=3)
        self.assertGreaterEqual(float(rows[-1]['imu_age_ms']), 0.0)    # tilt came from the ring
        self.assertEqual(int(rows[0]['pages']), 8)                       # first frame: full redraw
        self.assertLessEqual(int(rows[-1]['pages']), 8)
        with open(frame) as f:
            lines = f.read().split()
        self.assertEqual(lines[:3], ['P1', '128', '64'])
        bits = ''.join(lines[3:])
        self.assertEqual(len(bits), 128 * 64)
        self.assertGreater(bits.count('1'), 200)

    def test_attitude_rezero_drift_and_display(self):
        out_csv = os.path.join(self.dir, 'imu.csv')
        summary = os.path.join(self.dir, 'imu.json')
        imu = subprocess.Popen([IMU, '--backend', 'fake', '--fake-still', '--bias-seconds', '0.1',
                                '--duration', '3', '--shm', self.shm, '--csv', out_csv, '--summary', summary],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            shm_path = '/dev/shm/' + self.shm
            deadline = time.time()+5
            while time.time() < deadline:
                if os.path.exists(shm_path):
                    with open(shm_path,'rb') as f:
                        header = f.read(64)
                    if len(header) == 64 and struct.unpack_from('Q',header,32)[0] > 0:
                        break
                time.sleep(0.01)
            else:
                self.fail('producer never published attitude')
            self.assertEqual(struct.unpack_from('I',header,4)[0], 2)
            self.assertEqual(struct.unpack_from('I',header,12)[0], 128)
            imu.send_signal(signal.SIGUSR1)
            oled_csv = os.path.join(self.dir, 'oled.csv')
            p = run([OLED, '--backend', 'fake', '--imu-shm', self.shm, '--mode', 'attitude',
                     '--fps', '20', '--count', '20', '--csv', oled_csv,
                     '--frame-out', os.path.join(self.dir,'att.pbm')])
            self.assertEqual(p.returncode, 0, p.stderr)
            display = json.loads(p.stderr.splitlines()[-1])
            self.assertGreater(display['achieved_fps'], 10)  # host, not a Pi deadline claim
            self.assertEqual(display['io_errors'], 0)
            with open(oled_csv,newline='') as f:
                frames = list(csv.DictReader(f))
            self.assertTrue(all(float(r['imu_age_ms']) >= 0 for r in frames))
            self.assertTrue(all(r['mode'] == 'attitude' for r in frames))
            self.assertLess(int(frames[-1]['bytes']), int(frames[0]['bytes']))
        finally:
            _, stderr = imu.communicate(timeout=10)
        self.assertEqual(imu.returncode,0,stderr)
        with open(summary) as f:
            s = json.load(f)
        self.assertEqual(s['attitude']['rezero_count'],1)
        self.assertEqual(s['attitude']['drift_deg_per_min'],0)
        self.assertGreater(s['attitude']['drift_stationary_seconds'],1)
        for opts in (['--fps','26'],['--mode','bogus'],['--chunk','33']):
            self.assertEqual(run([OLED,*opts]).returncode,2)


if __name__ == '__main__':
    unittest.main()
