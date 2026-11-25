/* hea_oled: optional low-priority status / attitude display (off by default).
 * Reads demo state read-only (pipeline run-directory CSVs + IMU ring) and
 * draws it on a 128x64 I2C display with a configurable 1..25 fps cap. */
#include "hea_runtime.h"
#include "imu_bus.h"
#include "imu_ring.h"
#include "oled.h"
#include "oled_status.h"
#include "oled_attitude.h"
#include <errno.h>
#include <getopt.h>
#include <inttypes.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#ifdef __linux__
#include <sched.h>
#endif

struct args {
    const char *bus, *backend, *run_dir, *imu_shm, *frame_out, *csv, *mode;
    unsigned addr, rate_hz, chunk;
    uint64_t count, duration_s, max_age_s;
    int nice, idle, once, keep_on;
    struct hea_options sched;
};
static void usage(FILE *out)
{
    fputs("hea_oled [--bus /dev/i2c-1] [--backend linux|fake] [--addr 0x3C] [--run-dir DIR]\n"
          "  [--imu-shm hea_imu] [--mode status|attitude] [--fps 1..25] [--duration S | --count N | --once]\n"
          "  [--chunk 32] [--cpu N] [--nice 19] [--idle] [--frame-out PATH.pbm] [--csv PATH] [--keep-on]\n"
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
static int parse(int argc, char **argv, struct args *a)
{
    static const struct option opts[] = {
        {"bus", required_argument, NULL, 'b'}, {"backend", required_argument, NULL, 'B'},
        {"addr", required_argument, NULL, 'a'}, {"run-dir", required_argument, NULL, 'R'},
        {"imu-shm", required_argument, NULL, 'I'}, {"rate-hz", required_argument, NULL, 'r'},
        {"duration", required_argument, NULL, 'd'}, {"count", required_argument, NULL, 'n'},
        {"once", no_argument, NULL, 'o'}, {"max-age-s", required_argument, NULL, 'M'},
        {"chunk", required_argument, NULL, 'k'}, {"cpu", required_argument, NULL, 'c'},
        {"nice", required_argument, NULL, 'N'}, {"idle", no_argument, NULL, 'i'},
        {"frame-out", required_argument, NULL, 'f'}, {"csv", required_argument, NULL, 'l'},
        {"keep-on", no_argument, NULL, 'K'}, {"mode", required_argument, NULL, 'm'},
        {"fps", required_argument, NULL, 'r'},
        {"help", no_argument, NULL, 'h'}, {NULL, 0, NULL, 0}
    };
    memset(a, 0, sizeof(*a));
    a->bus = "/dev/i2c-1"; a->backend = "linux"; a->imu_shm = "hea_imu";
    a->rate_hz = 2; a->chunk = 32; a->max_age_s = 3; a->sched.cpu = -1; a->mode = "status";
    unsigned long v;
    int ch, explicit_fps = 0;
    while ((ch = getopt_long(argc, argv, "", opts, NULL)) != -1) {
        switch (ch) {
        case 'b': a->bus = optarg; break;
        case 'B': a->backend = optarg; break;
        case 'a': if (num(optarg, 0x7F, &v)) return -1; a->addr = (unsigned)v; break;
        case 'R': a->run_dir = optarg; break;
        case 'I': a->imu_shm = optarg; break;
        case 'r': if (num(optarg, 25, &v) || !v) { fprintf(stderr, "--fps / --rate-hz must be 1..25\n"); return -1; }
                  a->rate_hz = (unsigned)v; explicit_fps = 1; break;
        case 'm': a->mode = optarg; break;
        case 'd': if (num(optarg, 86400, &v)) return -1; a->duration_s = v; break;
        case 'n': if (num(optarg, UINT32_MAX, &v)) return -1; a->count = v; break;
        case 'o': a->once = 1; a->count = 1; break;
        case 'M': if (num(optarg, 3600, &v)) return -1; a->max_age_s = v; break;
        case 'k': if (num(optarg, 32, &v) || !v) return -1; a->chunk = (unsigned)v; break;
        case 'c': if (num(optarg, 1023, &v)) return -1; a->sched.cpu = (int)v; break;
        case 'N': if (num(optarg, 19, &v)) return -1; a->nice = (int)v; break;
        case 'i': a->idle = 1; break;
        case 'f': a->frame_out = optarg; break;
        case 'l': a->csv = optarg; break;
        case 'K': a->keep_on = 1; break;
        case 'h': usage(stdout); return 1;
        default: usage(stderr); return -1;
        }
    }
    if (optind != argc) { usage(stderr); return -1; }
    if (strcmp(a->backend, "linux") && strcmp(a->backend, "fake")) { fprintf(stderr, "--backend must be linux or fake\n"); return -1; }
    if (strcmp(a->mode, "status") && strcmp(a->mode, "attitude")) { fprintf(stderr, "--mode must be status or attitude\n"); return -1; }
    if (!explicit_fps && !strcmp(a->mode, "attitude")) a->rate_hz = 20;
    if (!strcmp(a->mode, "attitude") && a->max_age_s == 3) a->max_age_s = 1;
    return 0;
}
/* Lowest priority: SCHED_OTHER with a positive nice value (or SCHED_IDLE). Never real-time. */
static int lower_priority(const struct args *a)
{
    if (hea_schedule(&a->sched)) return -1;
    if (a->nice && setpriority(PRIO_PROCESS, 0, a->nice)) { perror("setpriority"); return -1; }
#ifdef __linux__
    if (a->idle) {
        struct sched_param p; memset(&p, 0, sizeof(p));
        if (sched_setscheduler(0, SCHED_IDLE, &p)) { perror("SCHED_IDLE"); return -1; }
    }
#else
    if (a->idle) { fprintf(stderr, "--idle requires Linux\n"); return -1; }
#endif
    return 0;
}
int main(int argc, char **argv)
{
    struct args a;
    int rc = parse(argc, argv, &a);
    if (rc) return rc > 0 ? 0 : 2;
    hea_signals();
    struct imu_bus bus;
    static struct imu_fake fake;
    char err[256] = "", report[512] = "";
    int fake_mode = !strcmp(a.backend, "fake");
    if (fake_mode) { imu_fake_init(&fake, &bus); imu_fake_add(&fake, a.addr ? (uint8_t)a.addr : 0x3C); }
    else if (imu_bus_linux_open(&bus, a.bus, err, sizeof(err))) { fprintf(stderr, "hea_oled: %s\n", err); return 1; }
    uint8_t addr = 0;
    if (oled_probe(&bus, (uint8_t)a.addr, &addr, report, sizeof(report))) {
        fprintf(stderr, "hea_oled: probe of %s failed\n%s", fake_mode ? "fake bus" : a.bus, report);
        if (!fake_mode) imu_bus_linux_close(&bus);
        return 3;
    }
    if (oled_init(&bus, addr)) { fprintf(stderr, "hea_oled: display init failed: %s\n", strerror(errno)); return 3; }
    if (lower_priority(&a)) return 1;
    FILE *csv = NULL;
    if (a.csv) {
        csv = fopen(a.csv, "w");
        if (!csv) { perror("hea_oled: open CSV"); return 1; }
        fprintf(csv, "frame,t_raw_ns,state,cam_fps,infer_ms,roll_deg,pitch_deg,imu_age_ms,pages,bytes,update_ns,yaw_deg,achieved_fps,mode\n");
    }
    struct imu_ring ring; int have_ring = 0;
    struct oled_fb fb, shown;
    oled_clear(&fb); oled_clear(&shown);
    struct demo_status st; memset(&st, 0, sizeof(st));
    uint64_t period = UINT64_C(1000000000) / a.rate_hz, start = hea_now(CLOCK_MONOTONIC), release = start;
    uint64_t end = a.duration_s ? start + a.duration_s * UINT64_C(1000000000) : 0, max_age = a.max_age_s * UINT64_C(1000000000);
    uint64_t io_errors = 0, first_done = 0, last_done = 0, completed = 0;
    double achieved_fps = 0;
    int force_redraw = 1;
    while (!hea_stop && (!a.count || st.frame < a.count) && (!end || release < end)) {
        rc = hea_sleep_until(release);
        if (rc && !(rc == EINTR && hea_stop)) { errno = rc; hea_fatal("absolute sleep"); }
        if (hea_stop) break;
        uint64_t now_raw = hea_raw_now();
        if (!strcmp(a.mode, "status")) demo_status_from_run(&st, a.run_dir, now_raw, max_age);
        if (!have_ring) have_ring = !imu_ring_open(&ring, a.imu_shm, err, sizeof(err));
        st.have_imu = 0;
        struct imu_record attitude; memset(&attitude, 0, sizeof(attitude));
        if (have_ring) {
            struct imu_record r;
            if (!imu_ring_latest(&ring, &r, 3)) {
                double age = r.t_ns <= now_raw ? (double)(now_raw - r.t_ns) / 1e6 : 0.0;
                if (!max_age || age * 1e6 <= (double)max_age) {
                    st.have_imu = 1; st.roll_deg = r.roll_deg; st.pitch_deg = r.pitch_deg; st.imu_age_ms = age;
                    attitude = r;
                } else { imu_ring_close(&ring); have_ring = 0; } /* producer gone: reopen next time */
            }
        }
        ++st.frame;
        if (!strcmp(a.mode, "attitude")) {
            attitude_render(&fb, attitude.q, (float)achieved_fps, st.have_imu && (attitude.flags & IMU_FLAG_ATT_VALID));
        } else {
            char lines[8][22];
            demo_status_lines(&st, a.rate_hz, lines);
            oled_clear(&fb);
            for (unsigned i = 0; i < 8; ++i) oled_text(&fb, i, 0, lines[i]);
        }
        size_t bytes = 0;
        uint64_t t0 = hea_now(CLOCK_MONOTONIC);
        int pages = oled_flush(&bus, addr, &fb, &shown, force_redraw, a.chunk, &bytes);
        uint64_t t1 = hea_now(CLOCK_MONOTONIC);
        if (pages < 0) {
            ++io_errors; force_redraw = 1;
            fprintf(stderr, "hea_oled: display write failed: %s\n", strerror(errno));
        } else {
            force_redraw = 0;
            if (!completed) first_done = t1;
            last_done = t1; ++completed;
            if (completed > 1 && last_done > first_done)
                achieved_fps = (double)(completed-1)*1e9/(double)(last_done-first_done);
        }
        if (csv) fprintf(csv, "%lu,%" PRIu64 ",%s,%.2f,%.2f,%.2f,%.2f,%.1f,%d,%zu,%" PRIu64 ",%.2f,%.3f,%s\n", st.frame, now_raw,
                         demo_state_name(st.state), st.have_fps ? st.cam_fps : -1.0, st.have_infer ? st.infer_ms : -1.0,
                         st.have_imu ? (double)st.roll_deg : 0.0, st.have_imu ? (double)st.pitch_deg : 0.0,
                         st.have_imu ? st.imu_age_ms : -1.0, pages, bytes, t1 - t0,
                         (double)attitude.attitude_deg[2], achieved_fps, a.mode);
        release += period;
        uint64_t now = hea_now(CLOCK_MONOTONIC);
        if (now > release) release += ((now - release) / period + 1u) * period;
    }
    if (a.frame_out && oled_write_pbm(&fb, a.frame_out)) perror("hea_oled: frame-out");
    if (!a.keep_on && !a.once) oled_off(&bus, addr);
    if (csv && fclose(csv)) perror("hea_oled: close CSV");
    if (have_ring) imu_ring_close(&ring);
    fprintf(stderr, "{\"program\":\"hea_oled\",\"addr\":%u,\"frames\":%lu,\"io_errors\":%" PRIu64
            ",\"display_writes\":%u,\"mode\":\"%s\",\"requested_fps\":%u,\"achieved_fps\":%.3f}\n",
            addr, st.frame, io_errors, fake_mode ? fake.raw_writes : 0u, a.mode, a.rate_hz, achieved_fps);
    if (!fake_mode) imu_bus_linux_close(&bus);
    return 0;
}
