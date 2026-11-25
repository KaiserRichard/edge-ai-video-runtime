/* Host tests for the IMU extension. All sensor data here is SYNTHETIC (fake
 * register file); nothing is a hardware measurement. */
#include "imu_bus.h"
#include "imu_filter.h"
#include "imu_ring.h"
#include "imu_sensor.h"
#include "imu_stats.h"
#include "oled.h"
#include "oled_status.h"
#include "oled_attitude.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static unsigned checks, failures;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); } } while (0)
#define NEAR(a, b, tol) CHECK(fabs((double)(a) - (double)(b)) <= (double)(tol))

static void no_delay(void *ctx, uint32_t us) { (void)ctx; (void)us; }

/* ---------------- probing ---------------- */
static void test_probe(void)
{
    struct imu_fake f; struct imu_bus bus; struct imu_device d; char rep[2048];
    imu_fake_init(&f, &bus); imu_fake_model_chip(&f, 0x18, 0x68);
    CHECK(!imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)));
    CHECK(d.map == IMU_MAP_CHIP && d.acc_addr == 0x18 && d.gyr_addr == 0x68);
    CHECK(d.chip_id_acc == 0x1E && d.chip_id_gyr == 0x0F);

    imu_fake_init(&f, &bus); imu_fake_model_chip(&f, 0x19, 0x69);   /* SDO pins high */
    CHECK(!imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)));
    CHECK(d.acc_addr == 0x19 && d.gyr_addr == 0x69);
    CHECK(strstr(rep, "0x18: no answer") && strstr(rep, "NACK"));

    imu_fake_init(&f, &bus);                                           /* empty bus */
    CHECK(imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)) == -1);
    CHECK(d.map == IMU_MAP_NONE);
    CHECK(strstr(rep, "no IMU sensor answered") && strstr(rep, "pin 3") && strstr(rep, "0x75"));

    imu_fake_init(&f, &bus); imu_fake_model_chip(&f, 0x18, 0x68);   /* gyro die missing */
    imu_fake_find(&f, 0x68)->present = 0;
    CHECK(imu_probe(&d, &bus, IMU_REQ_CHIP, 0, 0, rep, sizeof(rep)) == -1);
    CHECK(strstr(rep, "only the accelerometer die answered") && strstr(rep, "PS is high"));

    imu_fake_init(&f, &bus); imu_fake_model_chip(&f, 0x18, 0x68);   /* wrong chip ID */
    imu_fake_find(&f, 0x18)->regs[IMU_ACC_CHIP_ID] = 0x1F;
    CHECK(imu_probe(&d, &bus, IMU_REQ_CHIP, 0, 0, rep, sizeof(rep)) == -1);
    CHECK(strstr(rep, "= 0x1F (expected 0x1E)"));

    imu_fake_init(&f, &bus); imu_fake_model_invensense(&f, 0x68, 0x70); /* fallback map */
    CHECK(!imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)));
    CHECK(d.map == IMU_MAP_INVENSENSE && d.acc_addr == 0x68 && d.chip_id_acc == 0x70);
    CHECK(imu_probe(&d, &bus, IMU_REQ_CHIP, 0, 0, rep, sizeof(rep)) == -1);
    imu_fake_find(&f, 0x68)->regs[INV_WHO_AM_I] = 0x55;
    CHECK(imu_probe(&d, &bus, IMU_REQ_INVENSENSE, 0, 0, rep, sizeof(rep)) == -1);
    CHECK(strstr(rep, "not a supported WHO_AM_I"));

    imu_fake_init(&f, &bus); imu_fake_model_chip(&f, 0x19, 0x68);   /* explicit addresses */
    CHECK(imu_probe(&d, &bus, IMU_REQ_CHIP, 0x18, 0x68, rep, sizeof(rep)) == -1);
    CHECK(!imu_probe(&d, &bus, IMU_REQ_CHIP, 0x19, 0x68, rep, sizeof(rep)));
}

/* ---------------- configuration / power-on sequence ---------------- */
static void test_configure(void)
{
    struct imu_fake f; struct imu_bus bus; struct imu_device d; struct imu_config c; char rep[2048], err[256];
    imu_fake_init(&f, &bus); imu_fake_model_chip(&f, 0x18, 0x68);
    imu_config_default(&c);
    CHECK(!imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)));
    unsigned before = f.nlog;
    CHECK(!imu_configure(&d, &c, err, sizeof(err)));
    CHECK(f.model.ignored_writes == 0);
    int rst = imu_fake_find_write(&f, 0x18, IMU_ACC_SOFTRESET, before);
    int pc = imu_fake_find_write(&f, 0x18, IMU_ACC_PWR_CONF, before);
    int pw = imu_fake_find_write(&f, 0x18, IMU_ACC_PWR_CTRL, before);
    int conf = imu_fake_find_write(&f, 0x18, IMU_ACC_CONF, before);
    int range = imu_fake_find_write(&f, 0x18, IMU_ACC_RANGE, before);
    int grst = imu_fake_find_write(&f, 0x68, IMU_GYR_SOFTRESET, before);
    int grange = imu_fake_find_write(&f, 0x68, IMU_GYR_RANGE, before);
    CHECK(rst >= 0 && pc > rst && pw > pc && conf > pw && range > pw && grst > range && grange > grst);
    CHECK(f.log[rst].value == 0xB6 && f.log[pc].value == 0x00 && f.log[pw].value == 0x04);
    CHECK(f.log[pc].t_us - f.log[rst].t_us >= IMU_ACC_RESET_WAIT_US);
    CHECK(f.log[pw].t_us - f.log[pc].t_us >= IMU_ACC_PWR_CONF_WAIT_US);
    CHECK(f.log[conf].t_us - f.log[pw].t_us >= IMU_ACC_PWR_CTRL_WAIT_US);
    CHECK(f.log[grange].t_us - f.log[grst].t_us >= IMU_GYR_RESET_WAIT_US);
    struct imu_fake_device *a = imu_fake_find(&f, 0x18), *g = imu_fake_find(&f, 0x68);
    CHECK(a->regs[IMU_ACC_CONF] == 0xAA && a->regs[IMU_ACC_RANGE] == 0x01);
    CHECK(a->regs[IMU_ACC_PWR_CONF] == 0x00 && a->regs[IMU_ACC_PWR_CTRL] == 0x04);
    CHECK(g->regs[IMU_GYR_RANGE] == 0x02 && g->regs[IMU_GYR_BANDWIDTH] == 0x83 && g->regs[IMU_GYR_LPM1] == 0);
    NEAR(d.acc_lsb_per_g, 32768.0 / 6.0, 0.01);
    NEAR(d.gyr_lsb_per_dps, 65.536, 1e-4);

    /* A driver that skipped the datasheet waits would have writes ignored;
     * read-back verification must catch it. */
    struct imu_bus hasty = bus; hasty.delay_us = no_delay;
    imu_fake_model_chip(&f, 0x18, 0x68);
    CHECK(!imu_probe(&d, &hasty, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)));
    CHECK(imu_configure(&d, &c, err, sizeof(err)) == -1);
    CHECK(f.model.ignored_writes > 0 && strstr(err, "not accepted"));

    /* Invalid codes are refused before touching the bus. */
    imu_fake_model_chip(&f, 0x18, 0x68);
    CHECK(!imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)));
    struct imu_config bad = c; bad.acc_odr = 0x04;
    unsigned n0 = f.nlog;
    CHECK(imu_configure(&d, &bad, err, sizeof(err)) == -1 && f.nlog == n0);
    bad = c; bad.gyr_range = 5;
    CHECK(imu_configure(&d, &bad, err, sizeof(err)) == -1);

    /* Bus error mid-sequence gives a clear message. */
    imu_fake_find(&f, 0x68)->present = 0;
    CHECK(imu_configure(&d, &c, err, sizeof(err)) == -1 && strstr(err, "I2C transfer failed"));

    /* InvenSense map. */
    imu_fake_init(&f, &bus); imu_fake_model_invensense(&f, 0x69, 0x71);
    CHECK(!imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)) && d.acc_addr == 0x69);
    CHECK(!imu_configure(&d, &c, err, sizeof(err)));
    struct imu_fake_device *iv = imu_fake_find(&f, 0x69);
    CHECK(iv->regs[INV_PWR_MGMT_1] == 0x01 && iv->regs[INV_GYRO_CONFIG] == 0x08 && iv->regs[INV_ACCEL_CONFIG] == 0x08);
    CHECK(iv->regs[INV_CONFIG] == 3 && iv->regs[INV_SMPLRT_DIV] == 1 && f.model.ignored_writes == 0);
}

/* ---------------- reading and scaling ---------------- */
static void test_scaling(void)
{
    NEAR(imu_chip_acc_lsb_per_g(0), 32768.0 / 3.0, 0.01);
    NEAR(imu_chip_acc_lsb_per_g(3), 32768.0 / 24.0, 0.01);
    CHECK(imu_chip_acc_lsb_per_g(4) == 0.0f);
    NEAR(imu_chip_gyr_lsb_per_dps(0), 16.384, 1e-5);
    NEAR(imu_chip_gyr_lsb_per_dps(4), 262.144, 1e-3);
    NEAR(imu_inv_acc_lsb_per_g(1), 8192, 0); NEAR(imu_inv_gyr_lsb_per_dps(3), 16.384, 1e-5);
    NEAR(imu_chip_acc_odr_hz(0x05), 12.5, 0); NEAR(imu_chip_acc_odr_hz(0x0C), 1600, 0);
    CHECK(imu_chip_acc_odr_hz(0x0D) == 0.0f);
    NEAR(imu_chip_gyr_odr_hz(3), 400, 0);

    struct imu_fake f; struct imu_bus bus; struct imu_device d; struct imu_config c; char rep[2048], err[256];
    struct imu_raw r; struct imu_sample s;
    imu_fake_init(&f, &bus); imu_fake_model_chip(&f, 0x18, 0x68); imu_config_default(&c);
    CHECK(!imu_probe(&d, &bus, IMU_REQ_AUTO, 0, 0, rep, sizeof(rep)));
    /* Before the power-on sequence the accelerometer reports no data. */
    f.model.acc[2] = 1000;
    CHECK(!imu_read_raw(&d, &r) && r.acc[2] == 0 && r.acc_new == 0);
    CHECK(!imu_configure(&d, &c, err, sizeof(err)));
    f.model.acc[0] = 8192; f.model.acc[1] = -5461; f.model.acc[2] = 5461;
    f.model.gyr[0] = 16384; f.model.gyr[1] = -32768; f.model.gyr[2] = 0;
    CHECK(!imu_read_raw(&d, &r) && r.acc_new == 1 && r.gyr_new == 1);
    CHECK(r.acc[0] == 8192 && r.acc[1] == -5461 && r.gyr[1] == -32768);
    imu_scale(&d, &r, &s);
    NEAR(s.acc_g[0], 1.5, 1e-4); NEAR(s.acc_g[1], -1.0, 2e-4); NEAR(s.acc_g[2], 1.0, 2e-4);
    NEAR(s.gyr_dps[0], 250.0, 1e-3); NEAR(s.gyr_dps[1], -500.0, 1e-3);

    /* "Recorded" register frames (synthetic bytes): little-endian decoding. */
    static const uint8_t frames[3][6] = {
        { 0x00, 0x80, 0xFF, 0x7F, 0x01, 0x00 },   /* -32768, 32767, 1 */
        { 0xFF, 0xFF, 0x00, 0x00, 0x00, 0x40 },   /* -1, 0, 16384 */
        { 0x34, 0x12, 0xCC, 0xED, 0x55, 0x15 },   /* 4660, -4660, 5461 */
    };
    static const int16_t want[3][3] = { { -32768, 32767, 1 }, { -1, 0, 16384 }, { 4660, -4660, 5461 } };
    for (int k = 0; k < 3; ++k) {
        f.model.acc[0] = (int16_t)(uint16_t)(frames[k][0] | frames[k][1] << 8);
        f.model.acc[1] = (int16_t)(uint16_t)(frames[k][2] | frames[k][3] << 8);
        f.model.acc[2] = (int16_t)(uint16_t)(frames[k][4] | frames[k][5] << 8);
        CHECK(!imu_read_raw(&d, &r));
        CHECK(!memcmp(&imu_fake_find(&f, 0x18)->regs[IMU_ACC_X_LSB], frames[k], 6));
        CHECK(r.acc[0] == want[k][0] && r.acc[1] == want[k][1] && r.acc[2] == want[k][2]);
    }
    /* Read errors propagate. */
    f.fail_reads = 1;
    CHECK(imu_read_raw(&d, &r) == -1);

    /* InvenSense big-endian path, +-4 g / +-500 dps. */
    imu_fake_init(&f, &bus); imu_fake_model_invensense(&f, 0x68, 0x68);
    CHECK(!imu_probe(&d, &bus, IMU_REQ_INVENSENSE, 0, 0, rep, sizeof(rep)) && !imu_configure(&d, &c, err, sizeof(err)));
    f.model.acc[2] = 8192; f.model.gyr[2] = -655;
    CHECK(!imu_read_raw(&d, &r) && r.acc_new == 1);
    CHECK(imu_fake_find(&f, 0x68)->regs[INV_ACCEL_XOUT_H + 4] == 0x20);  /* MSB first */
    imu_scale(&d, &r, &s);
    NEAR(s.acc_g[2], 1.0, 1e-5); NEAR(s.gyr_dps[2], -655.0 / 65.536, 1e-4);
}

/* ---------------- shared-memory ring ---------------- */
static struct imu_ring *hook_ring; static int hook_armed;
void hea_imu_copy_hook(void);
void hea_imu_copy_hook(void)
{
    if (!hook_armed) return;
    hook_armed = 0;
    struct imu_record r; memset(&r, 0, sizeof(r)); r.index = 3;
    imu_ring_write(hook_ring, &r);          /* concurrent rewrite of the slot being copied */
}
static void test_ring(void)
{
    char name[64], err[256];
    snprintf(name, sizeof(name), "hea_imu_test_%ld", (long)getpid());
    struct imu_ring w, rd, dup;
    CHECK(!imu_ring_create(&w, name, 8, 200, IMU_MAP_CHIP, err, sizeof(err)));
    CHECK(imu_ring_create(&dup, name, 8, 200, 1, err, sizeof(err)) == -1 && strstr(err, "stale object"));
    CHECK(imu_ring_create(&dup, "bad/name", 8, 200, 1, err, sizeof(err)) == -1);
    CHECK(imu_ring_create(&dup, "ok_name", 0, 200, 1, err, sizeof(err)) == -1);
    CHECK(!imu_ring_open(&rd, name, err, sizeof(err)));
    w.h->version = 1;
    CHECK(imu_ring_open(&dup, name, err, sizeof(err)) == -1 && strstr(err, "unsupported ABI"));
    w.h->version = IMU_RING_VERSION;
    CHECK(rd.h->slots == 8 && rd.h->rate_hz == 200 && rd.h->map == IMU_MAP_CHIP && rd.h->stride == IMU_RING_STRIDE);
    struct imu_record x, out;
    CHECK(imu_ring_latest(&rd, &out, 3) == 1);                 /* empty */
    CHECK(imu_ring_read(&rd, 0, &out) == 1);
    for (uint32_t i = 0; i < 20; ++i) {
        memset(&x, 0, sizeof(x));
        x.index = i; x.flags = i & 3u; x.t_ns = UINT64_C(0x100000000) * i + 7u;
        x.acc_g[2] = 1.0f + (float)i; x.gyr_dps[0] = -(float)i; x.roll_deg = 0.5f * (float)i;
        x.i2c_ns = 1000u + i; x.period_ns = 5000000u;
        x.q[0] = 0.5f; x.q[1] = -0.5f; x.q[2] = 0.5f; x.q[3] = -0.5f;
        x.attitude_deg[0] = 10; x.attitude_deg[1] = -20; x.attitude_deg[2] = 30;
        imu_ring_write(&w, &x);
    }
    CHECK(imu_ring_head(&rd) == 20);
    CHECK(imu_ring_read(&rd, 19, &out) == 0 && out.index == 19 && out.t_ns == UINT64_C(0x100000000) * 19 + 7u);
    CHECK(out.acc_g[2] == 20.0f && out.gyr_dps[0] == -19.0f && out.roll_deg == 9.5f && out.i2c_ns == 1019u);
    CHECK(out.q[0] == 0.5f && out.q[1] == -0.5f && out.q[2] == 0.5f && out.q[3] == -0.5f);
    CHECK(out.attitude_deg[0] == 10 && out.attitude_deg[1] == -20 && out.attitude_deg[2] == 30);
    CHECK(imu_ring_read(&rd, 12, &out) == 0 && out.index == 12);  /* oldest retained */
    CHECK(imu_ring_read(&rd, 11, &out) == 1);                    /* overwritten by 19 */
    CHECK(imu_ring_read(&rd, 20, &out) == 1);                    /* not yet published */
    CHECK(imu_ring_latest(&rd, &out, 3) == 0 && out.index == 19);
    /* Wrap of the 32-bit index across slots: index i lands in slot i % slots. */
    memset(&x, 0, sizeof(x)); x.index = UINT32_MAX;               /* slot 7 */
    imu_ring_write(&w, &x);
    CHECK(imu_ring_read(&rd, UINT32_MAX, &out) == 0 && imu_ring_read(&rd, 15, &out) == 1);
    /* Torn read: the writer rewrites the slot during the copy. */
    hook_ring = &w; hook_armed = 1;
    CHECK(imu_ring_read(&rd, 19, &out) == 2);
    /* Odd sequence (writer mid-update) is busy. */
    uint64_t *seq = (uint64_t *)(void *)((uint8_t *)w.h + 64 + 2 * IMU_RING_STRIDE);
    __atomic_store_n(seq, *seq + 1u, __ATOMIC_SEQ_CST);
    CHECK(imu_ring_read(&rd, 18, &out) == 2);
    imu_ring_close(&rd);
    imu_ring_close(&w);
    CHECK(imu_ring_open(&rd, name, err, sizeof(err)) == -1);     /* owner unlinked it */
}

/* ---------------- complementary filter ---------------- */
static struct imu_sample tilt_sample(float roll_deg, float gx)
{
    struct imu_sample s; memset(&s, 0, sizeof(s));
    float r = roll_deg * 3.14159265f / 180.0f;
    s.acc_g[1] = sinf(r); s.acc_g[2] = cosf(r); s.gyr_dps[0] = gx;
    return s;
}
static void test_filter(void)
{
    struct imu_filter f; const float dt = 0.005f, tau = 0.5f;
    imu_filter_init(&f, tau);
    struct imu_sample level = tilt_sample(0, 0), tilted = tilt_sample(30, 0);
    imu_filter_step(&f, &level, 0);
    CHECK(f.initialised && fabsf(f.roll_deg) < 1e-4f && fabsf(f.pitch_deg) < 1e-4f);
    /* Step in the accelerometer angle with no rotation rate: first-order
     * response with time constant tau. */
    double k = (double)dt / ((double)tau + (double)dt), prev = 0;
    int monotonic = 1;
    for (int i = 1; i <= 500; ++i) {
        imu_filter_step(&f, &tilted, dt);
        if ((double)f.roll_deg < prev - 1e-6 || f.roll_deg > 30.0f + 1e-4f) monotonic = 0;
        prev = (double)f.roll_deg;
        if (i == 100) {
            NEAR(f.roll_deg, 30.0 * (1.0 - pow(1.0 - k, 100)), 0.01);    /* exact discrete response */
            NEAR(f.roll_deg, 30.0 * (1.0 - exp(-1.0)), 0.1);             /* ~63 % after tau */
        }
    }
    CHECK(monotonic);
    CHECK(f.roll_deg > 29.7f && f.roll_deg <= 30.0001f);                 /* >99 % after 5 tau */
    /* Gyro path: accelerometer says level, gyro integrates 10 dps for 1 s;
     * with a long tau the output follows the gyro. */
    imu_filter_init(&f, 1000.0f);
    struct imu_sample spin = tilt_sample(0, 10.0f);
    imu_filter_step(&f, &spin, 0);
    for (int i = 0; i < 200; ++i) imu_filter_step(&f, &spin, dt);
    NEAR(f.roll_deg, 10.0, 0.05);
    /* Linear acceleration (|a| = 2 g): accelerometer rejected, gyro only. */
    imu_filter_init(&f, tau);
    imu_filter_step(&f, &level, 0);
    struct imu_sample shove = level; shove.acc_g[1] = 1.7f; shove.acc_g[2] = 1.0f;
    for (int i = 0; i < 10; ++i) imu_filter_step(&f, &shove, dt);
    CHECK(f.gyro_only_steps == 10 && fabsf(f.roll_deg) < 1e-4f);
    /* Wrap near +-180: no excursion through zero. */
    imu_filter_init(&f, tau);
    struct imu_sample a179 = tilt_sample(179, 0), am179 = tilt_sample(-179, 0);
    imu_filter_step(&f, &a179, 0);
    for (int i = 0; i < 500; ++i) { imu_filter_step(&f, &am179, dt); CHECK(fabsf(f.roll_deg) > 178.0f); }
    NEAR(fabsf(f.roll_deg), 179.0, 0.05);
    /* Large dt (stall) re-initialises from the accelerometer. */
    imu_filter_step(&f, &tilted, 1.0f);
    NEAR(f.roll_deg, 30.0, 1e-3);
    /* Pitch sign: nose down (+x gravity component) is negative pitch. */
    float roll, pitch, a[3] = { 0.5f, 0.0f, 0.8660254f };
    imu_accel_tilt(a, &roll, &pitch);
    NEAR(pitch, -30.0, 1e-3); NEAR(roll, 0.0, 1e-4);
}

/* ---------------- jitter accounting ---------------- */
static void test_timing(void)
{
    static struct imu_timing t;
    const uint64_t P = 5000000, us = 1000;
    imu_timing_init(&t, P);
    const uint64_t late[5] = { 10, 20, 10, 50, 10 };
    for (int i = 0; i < 5; ++i) {
        uint64_t rel = 1000000000u + (uint64_t)i * P;
        uint64_t per = imu_timing_record(&t, rel, rel + late[i] * us, 300 * us);
        if (i) CHECK(per == P + (late[i] - late[i - 1]) * us);
        else CHECK(per == 0);
    }
    CHECK(t.releases == 5 && t.jitter_count == 4);
    CHECK(t.jitter_min_ns == -40000 && t.jitter_max_ns == 40000);
    NEAR(imu_timing_jitter_rms_ns(&t), sqrt(850.0) * 1000.0, 1e-6);
    CHECK(imu_hist_percentile_us(&t.lateness, 50) == 10 && imu_hist_percentile_us(&t.lateness, 100) == 50);
    CHECK(t.lateness.max_ns == 50000 && t.i2c.count == 5 && imu_hist_percentile_us(&t.i2c, 99) == 300);
    CHECK(imu_hist_percentile_us(&t.abs_jitter, 50) == 10 && imu_hist_percentile_us(&t.abs_jitter, 100) == 40);
    /* A skipped release: the planned interval is 2P, so on-time wakes are zero jitter. */
    uint64_t rel = 1000000000u + 6 * P;
    imu_timing_missed(&t, 1);
    CHECK(imu_timing_record(&t, rel, rel + 10 * us, 300 * us) == 2 * P);
    CHECK(t.missed == 1 && t.jitter_max_ns == 40000 && t.jitter_count == 5);
    /* Nearest-rank percentiles and overflow. */
    static struct imu_hist h;
    imu_hist_init(&h);
    for (uint64_t v = 1; v <= 100; ++v) imu_hist_add(&h, v * us);
    CHECK(imu_hist_percentile_us(&h, 50) == 50 && imu_hist_percentile_us(&h, 95) == 95 &&
          imu_hist_percentile_us(&h, 99) == 99 && imu_hist_percentile_us(&h, 100) == 100);
    imu_hist_add(&h, 25000 * us);
    CHECK(h.overflow == 1 && imu_hist_percentile_us(&h, 100) == UINT64_MAX && h.max_ns == 25000 * us);
    imu_hist_init(&h);
    CHECK(imu_hist_percentile_us(&h, 50) == 0);
    /* JSON summary. */
    char path[64]; snprintf(path, sizeof(path), "/tmp/hea_imu_json_%ld", (long)getpid());
    FILE *fp = fopen(path, "w+");
    CHECK(fp != NULL);
    if (fp) {
        imu_timing_json(fp, &t);
        char buf[4096]; rewind(fp); size_t n = fread(buf, 1, sizeof(buf) - 1, fp); buf[n] = '\0';
        CHECK(strstr(buf, "\"missed_releases\":1") && strstr(buf, "\"releases\":6"));
        CHECK(strstr(buf, "\"release_lateness\":{\"count\":6") && strstr(buf, "\"max_us\":50.000"));
        CHECK(strstr(buf, "\"period_jitter\":{\"count\":5"));
        fclose(fp); remove(path);
    }
}

/* ---------------- display ---------------- */
static void test_oled(void)
{
    struct imu_fake f; struct imu_bus bus; uint8_t addr = 0; char rep[512];
    imu_fake_init(&f, &bus);
    CHECK(oled_probe(&bus, 0, &addr, rep, sizeof(rep)) == -1 && strstr(rep, "0x3C: no answer") && strstr(rep, "0x3D"));
    imu_fake_add(&f, 0x3D);
    CHECK(!oled_probe(&bus, 0, &addr, rep, sizeof(rep)) && addr == 0x3D);
    CHECK(oled_probe(&bus, 0x3C, &addr, rep, sizeof(rep)) == -1);
    CHECK(!oled_init(&bus, 0x3D));
    CHECK(f.raw_last[0] == OLED_CTRL_CMD && f.raw_last[1] == 0xAE && f.raw_last[f.raw_last_n - 1] == 0xAF);
    int pump = 0;
    for (size_t i = 1; i + 1 < f.raw_last_n; ++i) if (f.raw_last[i] == 0x8D && f.raw_last[i + 1] == 0x14) pump = 1;
    CHECK(pump);
    const uint8_t zero[5] = { 0x3E, 0x51, 0x49, 0x45, 0x3E };
    CHECK(!memcmp(oled_glyph('0'), zero, 5) && oled_glyph('a') == oled_glyph('A') && oled_glyph('~') == oled_glyph('?'));
    struct oled_fb fb, shown; oled_clear(&fb); oled_clear(&shown);
    CHECK(oled_text(&fb, 2, 0, "0") == 1);
    CHECK(oled_pixel(&fb, 0, 17) == 1 && oled_pixel(&fb, 0, 16) == 0 && oled_pixel(&fb, 5, 17) == 0);
    CHECK(oled_text(&fb, 0, 0, "0123456789012345678901234") == 21);
    CHECK(oled_text(&fb, 9, 0, "X") == 0);
    size_t bytes = 0; unsigned w0 = f.raw_writes;
    CHECK(oled_flush(&bus, 0x3D, &fb, &shown, 1, 32, &bytes) == 8);
    CHECK(bytes == 8u * (7u + 4u * 33u) && f.raw_writes - w0 == 8u * 5u);
    CHECK(f.raw_last[0] == OLED_CTRL_DATA && f.raw_last_n == 33);
    CHECK(oled_flush(&bus, 0x3D, &fb, &shown, 0, 32, &bytes) == 0 && bytes == 0);
    oled_text(&fb, 5, 3, "HOLD");
    CHECK(oled_flush(&bus, 0x3D, &fb, &shown, 0, 128, &bytes) == 1 && bytes == 7u + 24u);
    fb.px[7][127] = 0x80;
    CHECK(oled_flush(&bus, 0x3D, &fb, &shown, 0, 32, &bytes) == 1 && bytes == 9);
    fb.px[7][127] = 0; /* erasures also count as dirty */
    CHECK(oled_flush(&bus, 0x3D, &fb, &shown, 0, 32, &bytes) == 1 && bytes == 9);
    CHECK(oled_flush(&bus, 0x3D, &fb, &shown, 0, 32, &bytes) == 0 && bytes == 0);
    char path[64]; snprintf(path, sizeof(path), "/tmp/hea_oled_pbm_%ld.pbm", (long)getpid());
    CHECK(!oled_write_pbm(&fb, path));
    FILE *fp = fopen(path, "r"); char line[160];
    CHECK(fp && fgets(line, sizeof(line), fp) && !strcmp(line, "P1\n"));
    if (fp) fclose(fp);
    remove(path);
    f.dev[f.ndev - 1].present = 0;
    CHECK(oled_flush(&bus, 0x3D, &fb, &shown, 1, 32, &bytes) == -1);
}

/* ---------------- status sources ---------------- */
static void write_file(const char *path, const char *text)
{
    FILE *fp = fopen(path, "w");
    if (fp) { fputs(text, fp); fclose(fp); }
}
static void test_status(void)
{
    const char *hdr = "seq,version,t_rx_pi_ns,mcu_us,state,missed_heartbeats";
    CHECK(csv_column(hdr, "state") == 4 && csv_column(hdr, "seq") == 0 && csv_column(hdr, "nope") == -1);
    char f[32]; uint64_t v;
    CHECK(!csv_field("1,,3", 2, f, sizeof(f)) && !strcmp(f, "3") && csv_field("1,,3", 1, f, sizeof(f)) == -1);
    CHECK(!csv_field_u64("7,123456789012", 1, &v) && v == UINT64_C(123456789012));
    CHECK(csv_field_u64("7,-1", 1, &v) == -1 && csv_field_u64("7", 3, &v) == -1);
    const char *mcu[2] = { "1,3,1000000000,5,1,0", "2,3,2000000000,6,2,0" };
    int state, stale;
    CHECK(!status_from_mcu(hdr, mcu, 2, 0, 0, &state, &stale) && state == 2 && !stale);
    CHECK(!status_from_mcu(hdr, mcu, 2, 2500000000u, 3000000000u, &state, &stale) && !stale);
    CHECK(!status_from_mcu(hdr, mcu, 2, 9000000000u, 3000000000u, &state, &stale) && stale);
    const char *bad[1] = { "2,3,2000000000,6,9,0" };
    CHECK(status_from_mcu(hdr, bad, 1, 0, 0, &state, &stale) == -1 && state == DEMO_STATE_UNKNOWN);
    CHECK(!strcmp(demo_state_name(3), "FAILSAFE") && !strcmp(demo_state_name(-1), "UNKNOWN"));

    char dir[64], path[128];
    snprintf(dir, sizeof(dir), "/tmp/hea_oled_run_%ld", (long)getpid());
    char cmd[160]; snprintf(cmd, sizeof(cmd), "mkdir -p %s", dir);
    CHECK(system(cmd) == 0);
    /* Camera CSV at 30 fps over 31 frames, plus a partial line being written. */
    static char text[16384]; size_t n = 0;
    n += (size_t)snprintf(text + n, sizeof(text) - n, "frame_id,seq,t_sensor_ns,t_recv_raw_ns,t_input_ns,status,t_clock_offset_ns\n");
    for (int i = 0; i < 40; ++i)
        n += (size_t)snprintf(text + n, sizeof(text) - n, "%d,%d,0,0,%llu,sent,0\n", i, i,
                              (unsigned long long)(1000000000ull + (unsigned long long)i * 33333333ull));
    snprintf(text + n, sizeof(text) - n, "40,40,0,0,99");
    snprintf(path, sizeof(path), "%s/source.csv", dir); write_file(path, text);
    n = (size_t)snprintf(text, sizeof(text), "seq,frame_id,t_input_ns,t_done_ns,t_send_ns\n");
    for (int i = 0; i < 10; ++i)
        n += (size_t)snprintf(text + n, sizeof(text) - n, "%d,%d,%llu,%llu,0\n", i, i,
                              1000000000ull + (unsigned long long)i * 100000000ull,
                              1000000000ull + (unsigned long long)i * 100000000ull + 20000000ull + (i % 2 ? 2000000ull : 0ull));
    snprintf(path, sizeof(path), "%s/bridge.csv", dir); write_file(path, text);
    snprintf(path, sizeof(path), "%s/mcu_status.csv", dir);
    write_file(path, "seq,version,t_rx_pi_ns,mcu_us,state,missed_heartbeats\n1,3,1000,5,0,0\n2,3,2000000000,6,1,0\n");

    char buf[512], header[256]; const char *lines[4];
    snprintf(path, sizeof(path), "%s/source.csv", dir);
    int k = csv_tail(path, buf, sizeof(buf), 200, header, sizeof(header), lines, 4);
    CHECK(k == 4 && !strncmp(lines[3], "39,", 3) && csv_column(header, "t_input_ns") == 4);
    snprintf(path, sizeof(path), "%s/none.csv", dir);
    CHECK(csv_tail(path, buf, sizeof(buf), 200, header, sizeof(header), lines, 4) == -1);

    struct demo_status s; memset(&s, 0, sizeof(s));
    demo_status_from_run(&s, dir, 0, 0);
    CHECK(s.state == 1 && !s.state_stale);
    CHECK(s.have_fps); NEAR(s.cam_fps, 30.0, 0.01);
    CHECK(s.have_infer); NEAR(s.infer_ms, 21.0, 1e-6);
    demo_status_from_run(&s, dir, UINT64_C(60000000000), UINT64_C(3000000000));
    CHECK(s.state == 1 && s.state_stale && !s.have_fps && !s.have_infer);
    demo_status_from_run(&s, NULL, 0, 0);
    CHECK(s.state == DEMO_STATE_UNKNOWN && !s.have_fps);

    char l[8][22];
    s.state = 3; s.state_stale = 0; s.have_fps = 1; s.cam_fps = 29.97; s.have_infer = 1; s.infer_ms = 34.25;
    s.have_imu = 1; s.roll_deg = 12.34f; s.pitch_deg = -4.1f; s.imu_age_ms = 4; s.frame = 7;
    demo_status_lines(&s, 2, l);
    CHECK(!strcmp(l[1], "STATE: FAILSAFE") && !strcmp(l[2], "CAM FPS: 30.0") && !strcmp(l[3], "INFER MS: 34.2"));
    CHECK(!strcmp(l[4], "ROLL: +12.3") && !strcmp(l[5], "PITCH: -4.1") && !strcmp(l[7], "2HZ #7"));
    for (int i = 0; i < 8; ++i) CHECK(strlen(l[i]) <= 21);
    s.have_imu = 0; s.state = DEMO_STATE_UNKNOWN;
    demo_status_lines(&s, 5, l);
    CHECK(!strcmp(l[1], "STATE: NO DATA") && !strcmp(l[6], "IMU: NONE"));
    snprintf(cmd, sizeof(cmd), "rm -rf %s", dir);
    CHECK(system(cmd) == 0);
}

int main(void)
{
    test_probe();
    test_configure();
    test_scaling();
    test_ring();
    test_filter();
    test_timing();
    test_oled();
    test_status();
    printf("test_imu: %u checks, %u failures\n", checks, failures);
    return failures ? 1 : 0;
}
