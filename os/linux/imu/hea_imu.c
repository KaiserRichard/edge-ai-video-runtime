/* hea_imu: optional periodic IMU sensor producer (off by default).
 * Probe + configure the sensor on an I2C bus, then sample at a fixed rate on
 * absolute CLOCK_MONOTONIC deadlines, publish each sample to a shared-memory
 * ring (imu_ring.h), log it to CSV, run a complementary tilt filter, and
 * account release lateness, period jitter and I2C read time. A separate Mahony
 * observer publishes quaternion attitude without changing complementary tilt. */
#include "hea_runtime.h"
#include "imu_bus.h"
#include "imu_filter.h"
#include "imu_ring.h"
#include "imu_sensor.h"
#include "imu_stats.h"
#include <errno.h>
#include <getopt.h>
#include <inttypes.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
#ifdef __linux__
#include <sched.h>
#endif

struct args {
    const char *bus, *backend, *shm, *csv, *summary, *map;
    unsigned rate_hz, slots, acc_addr, gyr_addr, acc_range_g, gyr_range_dps, gyr_bw;
    double acc_odr_hz, tau_s, kp, ki, bias_seconds;
    uint64_t count, duration_s;
    int probe_only, fake_missing_gyro, fake_still;
    struct hea_options sched;
};
static volatile sig_atomic_t rezero_requested;
static void rezero_handler(int sig) { (void)sig; rezero_requested = 1; }

static void usage(FILE *out)
{
    fputs("hea_imu [--bus /dev/i2c-1] [--backend linux|fake] [--map auto|imu|invensense]\n"
          "  [--acc-addr 0x18] [--gyro-addr 0x68] [--rate-hz 200] [--duration S | --count N]\n"
          "  [--shm hea_imu] [--slots 1024] [--csv imu.csv] [--summary imu_summary.json]\n"
          "  [--acc-range-g 3|6|12|24] [--acc-odr-hz 12.5..1600] [--gyro-range-dps 125..2000]\n"
          "  [--gyro-bw 0..7] [--tau-s 0.5] [--fifo-priority N] [--cpu N] [--mlock] [--probe-only]\n"
          "  [--mahony-kp 2] [--mahony-ki 0.05] [--bias-seconds 2] [--fake-still]\n"
          "Keep the IMU sensor STILL during startup calibration. SIGUSR1 re-zeros heading.\n"
          "See os/docs/IMU_EXTENSION.md. Off by default: no runner starts it.\n", out);
}
static int num(const char *s, unsigned long max, unsigned long *out)
{
    char *end = NULL;
    errno = 0;
    unsigned long v = strtoul(s, &end, 0);
    if (errno || !*s || *s == '-' || *end || v > max) { fprintf(stderr, "invalid numeric option: %s\n", s); return -1; }
    *out = v; return 0;
}
static int fnum(const char *s, double lo, double hi, double *out)
{
    char *end = NULL;
    errno = 0;
    double v = strtod(s, &end);
    if (errno || !*s || *end || !(v >= lo && v <= hi)) { fprintf(stderr, "invalid option value: %s\n", s); return -1; }
    *out = v; return 0;
}
static int parse(int argc, char **argv, struct args *a)
{
    static const struct option opts[] = {
        {"bus", required_argument, NULL, 'b'}, {"backend", required_argument, NULL, 'B'},
        {"map", required_argument, NULL, 'm'}, {"acc-addr", required_argument, NULL, 'a'},
        {"gyro-addr", required_argument, NULL, 'g'}, {"rate-hz", required_argument, NULL, 'r'},
        {"duration", required_argument, NULL, 'd'}, {"count", required_argument, NULL, 'n'},
        {"shm", required_argument, NULL, 's'}, {"slots", required_argument, NULL, 'S'},
        {"csv", required_argument, NULL, 'l'}, {"summary", required_argument, NULL, 'j'},
        {"acc-range-g", required_argument, NULL, 1}, {"acc-odr-hz", required_argument, NULL, 2},
        {"gyro-range-dps", required_argument, NULL, 3}, {"gyro-bw", required_argument, NULL, 4},
        {"tau-s", required_argument, NULL, 5}, {"fifo-priority", required_argument, NULL, 6},
        {"cpu", required_argument, NULL, 7}, {"mlock", no_argument, NULL, 8},
        {"probe-only", no_argument, NULL, 9}, {"fake-missing-gyro", no_argument, NULL, 10},
        {"mahony-kp", required_argument, NULL, 11}, {"mahony-ki", required_argument, NULL, 12},
        {"bias-seconds", required_argument, NULL, 13}, {"fake-still", no_argument, NULL, 14},
        {"help", no_argument, NULL, 'h'}, {NULL, 0, NULL, 0}
    };
    memset(a, 0, sizeof(*a));
    a->bus = "/dev/i2c-1"; a->backend = "linux"; a->shm = "hea_imu"; a->csv = "imu.csv"; a->map = "auto";
    a->rate_hz = 200; a->slots = 1024; a->acc_range_g = 6; a->acc_odr_hz = 400; a->gyr_range_dps = 500;
    a->gyr_bw = 3; a->tau_s = 0.5; a->sched.cpu = -1;
    a->kp = 2; a->ki = 0.05; a->bias_seconds = 2;
    unsigned long v;
    int ch;
    while ((ch = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (ch) {
        case 'b': a->bus = optarg; break;
        case 'B': a->backend = optarg; break;
        case 'm': a->map = optarg; break;
        case 'a': if (num(optarg, 0x7F, &v)) return -1; a->acc_addr = (unsigned)v; break;
        case 'g': if (num(optarg, 0x7F, &v)) return -1; a->gyr_addr = (unsigned)v; break;
        case 'r': if (num(optarg, 1000, &v) || v < 10) { fprintf(stderr, "--rate-hz must be 10..1000\n"); return -1; }
                  a->rate_hz = (unsigned)v; break;
        case 'd': if (num(optarg, 86400, &v)) return -1; a->duration_s = v; break;
        case 'n': if (num(optarg, UINT32_MAX, &v)) return -1; a->count = v; break;
        case 's': a->shm = optarg; break;
        case 'S': if (num(optarg, IMU_RING_MAX_SLOTS, &v) || !v) return -1; a->slots = (unsigned)v; break;
        case 'l': a->csv = optarg; break;
        case 'j': a->summary = optarg; break;
        case 1: if (num(optarg, 24, &v)) return -1; a->acc_range_g = (unsigned)v; break;
        case 2: if (fnum(optarg, 12.5, 1600, &a->acc_odr_hz)) return -1; break;
        case 3: if (num(optarg, 2000, &v)) return -1; a->gyr_range_dps = (unsigned)v; break;
        case 4: if (num(optarg, 7, &v)) return -1; a->gyr_bw = (unsigned)v; break;
        case 5: if (fnum(optarg, 0.01, 60, &a->tau_s)) return -1; break;
        case 6: if (num(optarg, 99, &v)) return -1; a->sched.priority = (int)v; break;
        case 7: if (num(optarg, 1023, &v)) return -1; a->sched.cpu = (int)v; break;
        case 8: a->sched.lock_memory = 1; break;
        case 9: a->probe_only = 1; break;
        case 10: a->fake_missing_gyro = 1; break;
        case 11: if (fnum(optarg, 0, 50, &a->kp)) return -1; break;
        case 12: if (fnum(optarg, 0, 10, &a->ki)) return -1; break;
        case 13: if (fnum(optarg, 0, 30, &a->bias_seconds)) return -1; break;
        case 14: a->fake_still = 1; break;
        case 'h': usage(stdout); return 1;
        default: usage(stderr); return -1;
        }
    }
    if (optind != argc) { usage(stderr); return -1; }
    if (strcmp(a->backend, "linux") && strcmp(a->backend, "fake")) { fprintf(stderr, "--backend must be linux or fake\n"); return -1; }
    if (strcmp(a->map, "auto") && strcmp(a->map, "imu") && strcmp(a->map, "invensense")) {
        fprintf(stderr, "--map must be auto, imu or invensense\n"); return -1;
    }
    return 0;
}
/* Human units -> register codes. */
static int to_config(const struct args *a, struct imu_config *c)
{
    imu_config_default(c);
    int found = 0;
    for (uint8_t r = 0; r <= 3; ++r) if ((unsigned)(3u << r) == a->acc_range_g) { c->acc_range = r; found = 1; }
    if (!found) { fprintf(stderr, "--acc-range-g must be 3, 6, 12 or 24\n"); return -1; }
    found = 0;
    for (uint8_t r = 0; r <= 4; ++r) if ((unsigned)(2000u >> r) == a->gyr_range_dps) { c->gyr_range = r; found = 1; }
    if (a->gyr_range_dps == 125) { c->gyr_range = 4; found = 1; }
    if (!found) { fprintf(stderr, "--gyro-range-dps must be 125, 250, 500, 1000 or 2000\n"); return -1; }
    found = 0;
    for (uint8_t o = 0x05; o <= 0x0C; ++o)
        if (fabs((double)imu_chip_acc_odr_hz(o) - a->acc_odr_hz) < 1e-3) { c->acc_odr = o; found = 1; }
    if (!found) { fprintf(stderr, "--acc-odr-hz must be 12.5, 25, 50, 100, 200, 400, 800 or 1600\n"); return -1; }
    c->gyr_bw = (uint8_t)a->gyr_bw;
    /* InvenSense fallback: nearest equivalents. */
    c->inv_afs = a->acc_range_g <= 3 ? 0 : a->acc_range_g <= 6 ? 1 : a->acc_range_g <= 12 ? 2 : 3;
    c->inv_fs = a->gyr_range_dps <= 250 ? 0 : a->gyr_range_dps <= 500 ? 1 : a->gyr_range_dps <= 1000 ? 2 : 3;
    return 0;
}

/* Synthetic motion for --backend fake: roll = 20 deg * sin(2 pi 0.2 t). */
struct fake_motion { struct imu_device *dev; uint64_t t0_us; int still; };
static void fake_generator(struct imu_fake *f)
{
    const struct fake_motion *m = f->model.user;
    double t = (double)(f->now_us - m->t0_us) / 1e6, w = 2.0 * 3.14159265358979 * 0.2;
    double roll = 20.0 * sin(w * t) * 3.14159265358979 / 180.0;
    double rate_dps = 20.0 * w * cos(w * t);
    if (m->still) { roll = 0; rate_dps = 0; }
    float alsb = m->dev->acc_lsb_per_g > 0 ? m->dev->acc_lsb_per_g : 5461.0f;
    float glsb = m->dev->gyr_lsb_per_dps > 0 ? m->dev->gyr_lsb_per_dps : 65.536f;
    f->model.acc[0] = 0;
    f->model.acc[1] = (int16_t)lrint(sin(roll) * (double)alsb);
    f->model.acc[2] = (int16_t)lrint(cos(roll) * (double)alsb);
    f->model.gyr[0] = (int16_t)lrint(rate_dps * (double)glsb);
    f->model.gyr[1] = f->model.gyr[2] = 0;
    ++f->model.generated;
}

static void sched_report(FILE *out, const struct hea_options *o)
{
#ifdef __linux__
    int policy = sched_getscheduler(0);
    struct sched_param p; memset(&p, 0, sizeof(p)); sched_getparam(0, &p);
    cpu_set_t set; CPU_ZERO(&set);
    fprintf(out, "\"requested\":{\"cpu\":%d,\"fifo_priority\":%d,\"mlock\":%d},\"actual\":{\"policy\":\"%s\",\"priority\":%d,\"cpus\":[",
            o->cpu, o->priority, o->lock_memory,
            policy == SCHED_FIFO ? "SCHED_FIFO" : policy == SCHED_RR ? "SCHED_RR" : policy == SCHED_OTHER ? "SCHED_OTHER" : "other",
            p.sched_priority);
    if (!sched_getaffinity(0, sizeof(set), &set)) {
        int first = 1;
        for (size_t c = 0; c < CPU_SETSIZE; ++c) if (CPU_ISSET(c, &set)) { fprintf(out, first ? "%zu" : ",%zu", c); first = 0; }
    }
    fputs("]}", out);
#else
    fprintf(out, "\"requested\":{\"cpu\":%d,\"fifo_priority\":%d,\"mlock\":%d},\"actual\":null",
            o->cpu, o->priority, o->lock_memory);
#endif
}

int main(int argc, char **argv)
{
    struct args a;
    int rc = parse(argc, argv, &a);
    if (rc) return rc > 0 ? 0 : 2;
    struct imu_config cfg;
    if (to_config(&a, &cfg)) return 2;
    hea_signals();
    struct sigaction sa;
    memset(&sa, 0, sizeof(sa)); sa.sa_handler = rezero_handler;
    sigemptyset(&sa.sa_mask);
    if (sigaction(SIGUSR1, &sa, NULL)) hea_fatal("SIGUSR1");

    struct imu_bus bus;
    static struct imu_fake fake;
    static struct imu_device dev;
    struct fake_motion motion = { &dev, 0, 1 };
    char err[256] = "", report[2048] = "";
    int fake_mode = !strcmp(a.backend, "fake");
    if (fake_mode) {
        imu_fake_init(&fake, &bus);
        if (!strcmp(a.map, "invensense")) imu_fake_model_invensense(&fake, 0x68, 0x68);
        else imu_fake_model_chip(&fake, IMU_ACC_ADDR_LO, IMU_GYR_ADDR_LO);
        if (a.fake_missing_gyro) imu_fake_find(&fake, IMU_GYR_ADDR_LO)->present = 0;
        fake.model.generator = fake_generator; fake.model.user = &motion;
    } else if (imu_bus_linux_open(&bus, a.bus, err, sizeof(err))) {
        fprintf(stderr, "hea_imu: %s\n", err); return 1;
    }
    enum imu_map_request req = !strcmp(a.map, "imu") ? IMU_REQ_CHIP :
                               !strcmp(a.map, "invensense") ? IMU_REQ_INVENSENSE : IMU_REQ_AUTO;
    if (imu_probe(&dev, &bus, req, (uint8_t)a.acc_addr, (uint8_t)a.gyr_addr, report, sizeof(report))) {
        fprintf(stderr, "hea_imu: probe of %s failed\n%s", fake_mode ? "fake bus" : a.bus, report);
        if (!fake_mode) imu_bus_linux_close(&bus);
        return 3;
    }
    fprintf(stderr, "hea_imu: probe\n%s", report);
    if (imu_configure(&dev, &cfg, err, sizeof(err))) {
        fprintf(stderr, "hea_imu: configure failed: %s\n", err);
        if (!fake_mode) imu_bus_linux_close(&bus);
        return 3;
    }
    fprintf(stderr, "hea_imu: %s map, accel 0x%02X (id 0x%02X), gyro 0x%02X (id 0x%02X), %.2f LSB/g, %.3f LSB/dps\n",
            dev.map == IMU_MAP_CHIP ? "IMU sensor" : imu_map_name(dev.map), dev.acc_addr, dev.chip_id_acc, dev.gyr_addr, dev.chip_id_gyr,
            (double)dev.acc_lsb_per_g, (double)dev.gyr_lsb_per_dps);
    if (a.probe_only) { if (!fake_mode) imu_bus_linux_close(&bus); return 0; }
    if (dev.map == IMU_MAP_CHIP && (double)imu_chip_acc_odr_hz(cfg.acc_odr) < (double)a.rate_hz)
        fprintf(stderr, "hea_imu: warning: accelerometer ODR below sample rate; acc_new will often be 0\n");

    struct imu_ring ring;
    if (imu_ring_create(&ring, a.shm, a.slots, a.rate_hz, (uint32_t)dev.map, err, sizeof(err))) {
        fprintf(stderr, "hea_imu: %s\n", err); if (!fake_mode) imu_bus_linux_close(&bus); return 1;
    }
    FILE *csv = fopen(a.csv, "w");
    if (!csv) { perror("hea_imu: open CSV"); imu_ring_close(&ring); return 1; }
    /* Fully buffered: one write(2) per ~64 KiB rather than per sample, so logging
     * does not add a syscall to every period. */
    static char csv_buf[1 << 16];
    if (setvbuf(csv, csv_buf, _IOFBF, sizeof(csv_buf))) hea_fatal("CSV buffer");
    fprintf(csv, "index,t_release_ns,t_wake_ns,t_sample_raw_ns,lateness_ns,period_ns,i2c_ns,missed_before,flags,"
                 "ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,roll_deg,pitch_deg,"
                 "qw,qx,qy,qz,att_roll_deg,att_pitch_deg,yaw_deg,rezero_count\n");
    a.sched.period_ms = 1; a.sched.heartbeat_ms = 1; a.sched.baud = 1;
    if (hea_schedule(&a.sched)) { fclose(csv); imu_ring_close(&ring); if (!fake_mode) imu_bus_linux_close(&bus); return 1; }

    static struct imu_timing timing;
    struct imu_filter filter;
    imu_filter_init(&filter, (float)a.tau_s);
    struct imu_mahony attitude;
    imu_mahony_init(&attitude, (float)a.kp, (float)a.ki);
    const uint64_t period = UINT64_C(1000000000) / a.rate_hz;
    struct imu_bias_cal cal; memset(&cal, 0, sizeof(cal));
    if (a.bias_seconds > 0) {
        fprintf(stderr, "hea_imu: keep IMU sensor STILL for %.2f s (gyro bias calibration)\n", a.bias_seconds);
        uint64_t cstart = hea_now(CLOCK_MONOTONIC);
        uint64_t cend = cstart + (uint64_t)(a.bias_seconds * 1e9);
        for (uint64_t deadline = cstart; !hea_stop && deadline < cend; deadline += period) {
            rc = hea_sleep_until(deadline);
            if (rc && !(rc == EINTR && hea_stop)) { errno = rc; hea_fatal("calibration sleep"); }
            if (hea_stop) break;
            struct imu_raw raw; struct imu_sample s;
            if (imu_read_raw(&dev, &raw)) { cal.moving = 1; break; }
            imu_scale(&dev, &raw, &s); imu_bias_add(&cal, &s);
            /* Do not manufacture catch-up samples after a delayed read. */
            uint64_t now = hea_now(CLOCK_MONOTONIC);
            if (now > deadline + period) deadline += ((now-deadline)/period)*period;
        }
        if (!hea_stop) {
            rc = hea_sleep_until(cend);
            if (rc && !(rc == EINTR && hea_stop)) { errno = rc; hea_fatal("calibration end"); }
        }
        if (hea_stop || imu_bias_finish(&cal, attitude.bias_dps)) {
            fprintf(stderr, "hea_imu: calibration interrupted, read failed, or motion detected; retry STILL (exit 5)\n");
            fclose(csv); imu_ring_close(&ring); if (!fake_mode) imu_bus_linux_close(&bus);
            return 5;
        }
    }
    motion.still = a.fake_still;
    unsigned rezero_count = 0;
    double drift_angle = 0, drift_seconds = 0;
    float prev_yaw = 0, prev_acc[3] = {0,0,0};
    int prev_still = 0;
    imu_timing_init(&timing, period);
    uint64_t fake_base_us = fake.now_us;
    uint64_t start = hea_now(CLOCK_MONOTONIC), release = start, end = a.duration_s ? start + a.duration_s * UINT64_C(1000000000) : 0;
    uint64_t index = 0, skipped_before = 0, consecutive_errors = 0;
    struct imu_sample last; memset(&last, 0, sizeof(last));
    int have_last = 0, failed = 0;
    motion.t0_us = fake_base_us;
    while (!hea_stop && (!a.count || index < a.count) && (!end || release < end)) {
        rc = hea_sleep_until(release);
        if (rc && !(rc == EINTR && hea_stop)) { errno = rc; hea_fatal("absolute sleep"); }
        if (hea_stop) break;
        if (index > UINT32_MAX) { fprintf(stderr, "hea_imu: index exhausted; start a new run\n"); break; }
        uint64_t wake = hea_now(CLOCK_MONOTONIC);
        if (fake_mode) fake.now_us = fake_base_us + (wake - start) / 1000u;
        struct imu_raw raw;
        uint64_t t0 = hea_now(CLOCK_MONOTONIC);
        int rd = imu_read_raw(&dev, &raw);
        uint64_t t1 = hea_now(CLOCK_MONOTONIC), t_sample = hea_raw_now();
        struct imu_record rec; memset(&rec, 0, sizeof(rec));
        struct imu_sample s;
        if (rd) {
            ++timing.read_errors; rec.flags |= IMU_FLAG_READ_ERROR;
            if (++consecutive_errors >= a.rate_hz) {
                fprintf(stderr, "hea_imu: sensor stopped answering for 1 s (%s); stopping\n", strerror(errno));
                failed = 1; break;
            }
            s = last;
        } else {
            consecutive_errors = 0;
            imu_scale(&dev, &raw, &s);
            if (s.acc_new) rec.flags |= IMU_FLAG_ACC_NEW;
            if (s.gyr_new) rec.flags |= IMU_FLAG_GYR_NEW;
        }
        if (skipped_before) rec.flags |= IMU_FLAG_MISSED;
        uint64_t observed = imu_timing_record(&timing, release, wake, t1 - t0);
        if (!rd || have_last) {
            imu_filter_step(&filter, &s, observed ? (float)((double)observed / 1e9) : 0.0f);
            last = s; have_last = 1;
        }
        float dt = observed ? (float)((double)observed/1e9) : 0;
        if (!rd) imu_mahony_step(&attitude, &s, dt);
        int did_rezero = rezero_requested && attitude.initialised;
        if (did_rezero) {
            imu_mahony_rezero(&attitude); rezero_requested = 0; ++rezero_count;
        }
        imu_quat_euler(attitude.q, &rec.attitude_deg[0], &rec.attitude_deg[1], &rec.attitude_deg[2]);
        memcpy(rec.q, attitude.q, sizeof(rec.q));
        if (attitude.initialised && !rd) rec.flags |= IMU_FLAG_ATT_VALID;
        /* Apparent stationary yaw slope, not an absolute heading reference.
         * Deliberately slow turns can pass this gate; operator must confirm rest. */
        int still = !rd && attitude.initialised && !did_rezero && dt > 0 && dt <= 0.5f;
        float amag2 = 0;
        for (int j = 0; j < 3; ++j) {
            amag2 += s.acc_g[j]*s.acc_g[j];
            if (fabsf(s.gyr_dps[j]-attitude.bias_dps[j]) > 0.5f ||
                fabsf(s.acc_g[j]-prev_acc[j]) > 0.002f) still = 0;
        }
        if (amag2 < 0.95f*0.95f || amag2 > 1.05f*1.05f) still = 0;
        if (still && prev_still) {
            float dy = rec.attitude_deg[2]-prev_yaw;
            if (dy > 180) dy -= 360;
            if (dy < -180) dy += 360;
            drift_angle += dy; drift_seconds += dt;
        }
        prev_still = still; prev_yaw = rec.attitude_deg[2];
        memcpy(prev_acc, s.acc_g, sizeof(prev_acc));
        rec.index = (uint32_t)index; rec.t_ns = t_sample;
        memcpy(rec.acc_g, s.acc_g, sizeof(rec.acc_g)); memcpy(rec.gyr_dps, s.gyr_dps, sizeof(rec.gyr_dps));
        rec.roll_deg = filter.roll_deg; rec.pitch_deg = filter.pitch_deg;
        rec.i2c_ns = (uint32_t)((t1 - t0) > UINT32_MAX ? UINT32_MAX : (t1 - t0));
        rec.period_ns = (uint32_t)(observed > UINT32_MAX ? UINT32_MAX : observed);
        imu_ring_write(&ring, &rec);
        if (fprintf(csv, "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%" PRIu64
                    ",%u,%.5f,%.5f,%.5f,%.4f,%.4f,%.4f,%.3f,%.3f,"
                    "%.7f,%.7f,%.7f,%.7f,%.3f,%.3f,%.3f,%u\n",
                    index, release, wake, t_sample, wake > release ? wake - release : 0u, observed, t1 - t0,
                    skipped_before, rec.flags, (double)s.acc_g[0], (double)s.acc_g[1], (double)s.acc_g[2],
                    (double)s.gyr_dps[0], (double)s.gyr_dps[1], (double)s.gyr_dps[2],
                    (double)filter.roll_deg, (double)filter.pitch_deg,
                    (double)rec.q[0], (double)rec.q[1], (double)rec.q[2], (double)rec.q[3],
                    (double)rec.attitude_deg[0], (double)rec.attitude_deg[1], (double)rec.attitude_deg[2],
                    rezero_count) < 0) hea_fatal("IMU CSV");
        ++index; release += period; skipped_before = 0;
        uint64_t now = hea_now(CLOCK_MONOTONIC);
        if (now > release) {
            uint64_t skip = (now - release) / period + 1u;
            release += skip * period; skipped_before = skip;
            imu_timing_missed(&timing, skip);
        }
    }
    if (fclose(csv)) hea_fatal("close IMU CSV");
    FILE *sum = a.summary ? fopen(a.summary, "w") : stderr;
    if (!sum) { perror("hea_imu: open summary"); sum = stderr; }
    fprintf(sum, "{\"program\":\"hea_imu\",\"backend\":\"%s\",\"bus\":\"%s\",\"map\":\"%s\",\"acc_addr\":%u,\"gyro_addr\":%u,"
            "\"chip_id_acc\":%u,\"chip_id_gyro\":%u,\"rate_hz\":%u,\"samples\":%" PRIu64 ",\"shm\":\"%s\",\"slots\":%u,"
            "\"config\":{\"acc_range_g\":%u,\"acc_odr_hz\":%.1f,\"gyro_range_dps\":%u,\"gyro_bw_code\":%u},"
            "\"filter\":{\"tau_s\":%.3f,\"gyro_only_steps\":%lu,\"final_roll_deg\":%.3f,\"final_pitch_deg\":%.3f},"
            "\"scheduling\":{",
            a.backend, fake_mode ? "fake" : a.bus, imu_map_name(dev.map), dev.acc_addr, dev.gyr_addr,
            dev.chip_id_acc, dev.chip_id_gyr, a.rate_hz, index, a.shm, a.slots, a.acc_range_g, a.acc_odr_hz,
            a.gyr_range_dps, a.gyr_bw, a.tau_s, filter.gyro_only_steps, (double)filter.roll_deg,
            (double)filter.pitch_deg);
    sched_report(sum, &a.sched);
    fputs("},\"timing\":", sum);
    imu_timing_json(sum, &timing);
    fprintf(sum, ",\"attitude\":{\"kp\":%.4f,\"ki\":%.4f,\"bias_seconds\":%.3f,\"bias_samples\":%u,"
            "\"bias_dps\":[%.6f,%.6f,%.6f],\"rezero_count\":%u,\"drift_basis\":\"apparent stationary yaw slope; operator must confirm rest\","
            "\"drift_stationary_seconds\":%.6f,\"drift_deg_per_min\":",
            a.kp, a.ki, a.bias_seconds, cal.n, (double)attitude.bias_dps[0],
            (double)attitude.bias_dps[1], (double)attitude.bias_dps[2], rezero_count, drift_seconds);
    if (drift_seconds >= 1) fprintf(sum, "%.6f", 60*drift_angle/drift_seconds);
    else fputs("null", sum);
    fputs("}", sum);
    fprintf(sum, ",\"status\":\"%s\"}\n", failed ? "SENSOR_LOST" : "OK");
    if (sum != stderr && fclose(sum)) perror("hea_imu: close summary");
    imu_ring_close(&ring);
    if (!fake_mode) imu_bus_linux_close(&bus);
    return failed ? 4 : 0;
}
