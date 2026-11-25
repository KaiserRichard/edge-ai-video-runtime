#include "imu_sensor.h"
#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#ifndef EREMOTEIO
#define EREMOTEIO ENXIO
#endif

static void append(char *out, size_t size, const char *fmt, ...)
{
    if (!out || !size) return;
    size_t used = strnlen(out, size);
    if (used + 1u >= size) return;
    va_list ap; va_start(ap, fmt);
    vsnprintf(out + used, size - used, fmt, ap);
    va_end(ap);
}

void imu_config_default(struct imu_config *c)
{
    memset(c, 0, sizeof(*c));
    c->acc_range = 1;          /* +-6 g */
    c->acc_odr = 0x0Au;        /* 400 Hz: two samples per 200 Hz loop period */
    c->acc_bwp = IMU_ACC_BWP_NORMAL;
    c->gyr_range = 2;          /* +-500 dps */
    c->gyr_bw = 0x03u;         /* ODR 400 Hz, 47 Hz filter */
    c->inv_afs = 1;            /* +-4 g */
    c->inv_fs = 1;             /* +-500 dps */
    c->inv_dlpf = 3;           /* ~44 Hz */
    c->inv_div = 1;            /* 1 kHz / (1 + 1) = 500 Hz */
}

float imu_chip_acc_lsb_per_g(uint8_t range)
{
    /* full scale = 1.5 g * 2^(range+1): 3, 6, 12, 24 g over 32768 LSB */
    return range > 3u ? 0.0f : 32768.0f / (1.5f * (float)(2u << range));
}
float imu_chip_gyr_lsb_per_dps(uint8_t range)
{
    /* 2000, 1000, 500, 250, 125 dps */
    return range > 4u ? 0.0f : 16.384f * (float)(1u << range);
}
float imu_inv_acc_lsb_per_g(uint8_t afs) { return afs > 3u ? 0.0f : 16384.0f / (float)(1u << afs); }
float imu_inv_gyr_lsb_per_dps(uint8_t fs) { return fs > 3u ? 0.0f : 131.072f / (float)(1u << fs); }
float imu_chip_acc_odr_hz(uint8_t odr)
{
    return (odr < 0x05u || odr > 0x0Cu) ? 0.0f : 12.5f * (float)(1u << (odr - 0x05u));
}
float imu_chip_gyr_odr_hz(uint8_t bw)
{
    static const float hz[8] = { 2000, 2000, 1000, 400, 200, 100, 200, 100 };
    return bw > 7u ? 0.0f : hz[bw];
}
const char *imu_map_name(enum imu_map m)
{
    return m == IMU_MAP_CHIP ? "imu" : m == IMU_MAP_INVENSENSE ? "invensense" : "none";
}
static int inv_known(uint8_t who)
{
    /* WHO_AM_I values of parts sharing the 0x3B data / 0x6B power layout. */
    static const uint8_t ids[] = { 0x68, 0x70, 0x71, 0x73, 0x12, 0x98, 0x19 };
    for (size_t i = 0; i < sizeof(ids); ++i) if (ids[i] == who) return 1;
    return 0;
}
/* Read one ID register; append a line to the report. 1 match, 0 no match. */
static int try_id(const struct imu_bus *bus, uint8_t addr, uint8_t reg, uint8_t expect, int any_inv,
                  const char *what, uint8_t *got, char *report, size_t size)
{
    uint8_t v = 0;
    if (imu_bus_read(bus, addr, reg, &v, 1)) {
        int e = errno;
        append(report, size, "  %s 0x%02X: no answer reading reg 0x%02X (%s)\n", what, addr, reg,
               e == ENXIO || e == EREMOTEIO ? "NACK" : strerror(e));
        return 0;
    }
    int ok = any_inv ? inv_known(v) : v == expect;
    if (any_inv) append(report, size, "  %s 0x%02X: reg 0x%02X = 0x%02X (%s)\n", what, addr, reg, v,
                        ok ? "accepted" : "not a supported WHO_AM_I");
    else append(report, size, "  %s 0x%02X: reg 0x%02X = 0x%02X (expected 0x%02X)%s\n", what, addr, reg, v,
                expect, ok ? " ok" : "");
    *got = v;
    return ok;
}
int imu_probe(struct imu_device *d, const struct imu_bus *bus, enum imu_map_request req,
              uint8_t acc_addr, uint8_t gyr_addr, char *report, size_t size)
{
    memset(d, 0, sizeof(*d));
    d->bus = bus;
    if (report && size) report[0] = '\0';
    uint8_t accs[2] = { IMU_ACC_ADDR_LO, IMU_ACC_ADDR_HI }, gyrs[2] = { IMU_GYR_ADDR_LO, IMU_GYR_ADDR_HI };
    size_t nacc = 2, ngyr = 2;
    if (acc_addr) { accs[0] = acc_addr; nacc = 1; }
    if (gyr_addr) { gyrs[0] = gyr_addr; ngyr = 1; }
    if (req != IMU_REQ_INVENSENSE) {
        append(report, size, "two-die map (accelerometer + gyroscope):\n");
        int acc_ok = 0, gyr_ok = 0;
        uint8_t v = 0;
        for (size_t i = 0; i < nacc && !acc_ok; ++i)
            if (try_id(bus, accs[i], IMU_ACC_CHIP_ID, IMU_ACC_CHIP_ID_VALUE, 0, "accelerometer", &v, report, size)) {
                acc_ok = 1; d->acc_addr = accs[i]; d->chip_id_acc = v;
            }
        for (size_t i = 0; i < ngyr && !gyr_ok; ++i)
            if (try_id(bus, gyrs[i], IMU_GYR_CHIP_ID, IMU_GYR_CHIP_ID_VALUE, 0, "gyroscope", &v, report, size)) {
                gyr_ok = 1; d->gyr_addr = gyrs[i]; d->chip_id_gyr = v;
            }
        if (acc_ok && gyr_ok) { d->map = IMU_MAP_CHIP; return 0; }
        if (acc_ok != gyr_ok)
            append(report, size, "  only the %s die answered: check the module wiring and that PS is high (I2C mode)\n",
                   acc_ok ? "accelerometer" : "gyroscope");
        d->acc_addr = d->gyr_addr = 0;
    }
    if (req != IMU_REQ_CHIP) {
        append(report, size, "InvenSense-style map (WHO_AM_I 0x75):\n");
        uint8_t addrs[2] = { 0x68, 0x69 };
        size_t n = 2;
        if (gyr_addr) { addrs[0] = gyr_addr; n = 1; }
        uint8_t v = 0;
        for (size_t i = 0; i < n; ++i)
            if (try_id(bus, addrs[i], INV_WHO_AM_I, 0, 1, "sensor", &v, report, size)) {
                d->map = IMU_MAP_INVENSENSE; d->acc_addr = d->gyr_addr = addrs[i];
                d->chip_id_acc = d->chip_id_gyr = v;
                return 0;
            }
    }
    append(report, size, "no IMU sensor answered: check 3.3 V, GND, SDA on header pin 3, SCL on pin 5, "
                         "PS high, and `i2cdetect -y 1`\n");
    return -1;
}

/* Write then read back; mask selects bits that must match. */
static int set_reg(const struct imu_device *d, uint8_t addr, uint8_t reg, uint8_t v, uint32_t wait_us)
{
    if (imu_bus_write1(d->bus, addr, reg, v)) return -1;
    if (wait_us) imu_bus_delay(d->bus, wait_us);
    return 0;
}
static int check_reg(const struct imu_device *d, uint8_t addr, uint8_t reg, uint8_t want, uint8_t mask,
                     const char *name, char *err, size_t size)
{
    uint8_t v = 0;
    if (imu_bus_read(d->bus, addr, reg, &v, 1)) {
        snprintf(err, size, "read-back of %s (0x%02X:0x%02X) failed: %s", name, addr, reg, strerror(errno));
        return -1;
    }
    if ((v & mask) != (want & mask)) {
        snprintf(err, size, "%s (0x%02X:0x%02X) reads 0x%02X, wrote 0x%02X: configuration was not accepted",
                 name, addr, reg, v, want);
        return -1;
    }
    return 0;
}
static int imu_chip_configure(struct imu_device *d, char *err, size_t size)
{
    const struct imu_config *c = &d->cfg;
    uint8_t a = d->acc_addr, g = d->gyr_addr, v = 0;
    if (c->acc_range > 3u || !imu_chip_acc_odr_hz(c->acc_odr) || c->acc_bwp < IMU_ACC_BWP_OSR4 ||
        c->acc_bwp > IMU_ACC_BWP_NORMAL || c->gyr_range > 4u || c->gyr_bw > 7u) {
        snprintf(err, size, "invalid range/ODR/bandwidth code"); return -1;
    }
    /* Accelerometer: soft reset, then the datasheet power-on sequence. After
     * reset/POR the die is in suspend; the first writes need the waits below. */
    /* The die resets while the command byte is clocked in and may NACK it
     * (seen on hardware 25 Nov: i2cset reports a write error, chip ID reads
     * back fine). Ignore the write status; the chip-ID read below verifies. */
    (void)imu_bus_write1(d->bus, a, IMU_ACC_SOFTRESET, IMU_SOFTRESET_CMD);
    imu_bus_delay(d->bus, IMU_ACC_RESET_WAIT_US);
    if (imu_bus_read(d->bus, a, IMU_ACC_CHIP_ID, &v, 1)) goto io;
    if (v != IMU_ACC_CHIP_ID_VALUE) { snprintf(err, size, "accelerometer chip ID 0x%02X after reset", v); return -1; }
    if (set_reg(d, a, IMU_ACC_PWR_CONF, 0x00u, IMU_ACC_PWR_CONF_WAIT_US)) goto io;
    if (set_reg(d, a, IMU_ACC_PWR_CTRL, 0x04u, IMU_ACC_PWR_CTRL_WAIT_US)) goto io;
    uint8_t conf = (uint8_t)((c->acc_bwp << 4) | c->acc_odr);
    if (set_reg(d, a, IMU_ACC_CONF, conf, 0) || set_reg(d, a, IMU_ACC_RANGE, c->acc_range, 0)) goto io;
    if (check_reg(d, a, IMU_ACC_PWR_CONF, 0x00u, 0xFFu, "ACC_PWR_CONF", err, size) ||
        check_reg(d, a, IMU_ACC_PWR_CTRL, 0x04u, 0xFFu, "ACC_PWR_CTRL", err, size) ||
        check_reg(d, a, IMU_ACC_CONF, conf, 0xFFu, "ACC_CONF", err, size) ||
        check_reg(d, a, IMU_ACC_RANGE, c->acc_range, 0x03u, "ACC_RANGE", err, size)) return -1;
    if (imu_bus_read(d->bus, a, IMU_ACC_ERR_REG, &v, 1)) goto io;
    if (v & 0x1Du) { snprintf(err, size, "accelerometer error register 0x%02X (fatal or config error)", v); return -1; }
    /* Gyroscope: soft reset (comes up in normal mode), range and bandwidth. */
    (void)imu_bus_write1(d->bus, g, IMU_GYR_SOFTRESET, IMU_SOFTRESET_CMD); /* may NACK, see above */
    imu_bus_delay(d->bus, IMU_GYR_RESET_WAIT_US);
    if (imu_bus_read(d->bus, g, IMU_GYR_CHIP_ID, &v, 1)) goto io;
    if (v != IMU_GYR_CHIP_ID_VALUE) { snprintf(err, size, "gyroscope chip ID 0x%02X after reset", v); return -1; }
    if (set_reg(d, g, IMU_GYR_LPM1, 0x00u, 0) || set_reg(d, g, IMU_GYR_RANGE, c->gyr_range, 0) ||
        set_reg(d, g, IMU_GYR_BANDWIDTH, c->gyr_bw, 0)) goto io;
    if (check_reg(d, g, IMU_GYR_LPM1, 0x00u, 0xFFu, "GYRO_LPM1", err, size) ||
        check_reg(d, g, IMU_GYR_RANGE, c->gyr_range, 0x07u, "GYRO_RANGE", err, size) ||
        check_reg(d, g, IMU_GYR_BANDWIDTH, c->gyr_bw, 0x7Fu, "GYRO_BANDWIDTH", err, size)) return -1;
    d->acc_lsb_per_g = imu_chip_acc_lsb_per_g(c->acc_range);
    d->gyr_lsb_per_dps = imu_chip_gyr_lsb_per_dps(c->gyr_range);
    return 0;
io:
    snprintf(err, size, "I2C transfer failed during configuration: %s", strerror(errno));
    return -1;
}
static int inv_configure(struct imu_device *d, char *err, size_t size)
{
    const struct imu_config *c = &d->cfg;
    uint8_t a = d->acc_addr;
    if (c->inv_afs > 3u || c->inv_fs > 3u || c->inv_dlpf > 6u) { snprintf(err, size, "invalid range/DLPF code"); return -1; }
    if (set_reg(d, a, INV_PWR_MGMT_1, 0x80u, INV_RESET_WAIT_US) ||
        set_reg(d, a, INV_PWR_MGMT_1, 0x01u, 10000u) ||          /* wake, gyro PLL clock */
        set_reg(d, a, INV_SMPLRT_DIV, c->inv_div, 0) || set_reg(d, a, INV_CONFIG, c->inv_dlpf, 0) ||
        set_reg(d, a, INV_GYRO_CONFIG, (uint8_t)(c->inv_fs << 3), 0) ||
        set_reg(d, a, INV_ACCEL_CONFIG, (uint8_t)(c->inv_afs << 3), 0)) {
        snprintf(err, size, "I2C transfer failed during configuration: %s", strerror(errno)); return -1;
    }
    if (check_reg(d, a, INV_PWR_MGMT_1, 0x01u, 0xFFu, "PWR_MGMT_1", err, size) ||
        check_reg(d, a, INV_SMPLRT_DIV, c->inv_div, 0xFFu, "SMPLRT_DIV", err, size) ||
        check_reg(d, a, INV_CONFIG, c->inv_dlpf, 0x07u, "CONFIG", err, size) ||
        check_reg(d, a, INV_GYRO_CONFIG, (uint8_t)(c->inv_fs << 3), 0x18u, "GYRO_CONFIG", err, size) ||
        check_reg(d, a, INV_ACCEL_CONFIG, (uint8_t)(c->inv_afs << 3), 0x18u, "ACCEL_CONFIG", err, size)) return -1;
    d->acc_lsb_per_g = imu_inv_acc_lsb_per_g(c->inv_afs);
    d->gyr_lsb_per_dps = imu_inv_gyr_lsb_per_dps(c->inv_fs);
    return 0;
}
int imu_configure(struct imu_device *d, const struct imu_config *cfg, char *err, size_t size)
{
    d->cfg = *cfg;
    if (d->map == IMU_MAP_CHIP) return imu_chip_configure(d, err, size);
    if (d->map == IMU_MAP_INVENSENSE) return inv_configure(d, err, size);
    snprintf(err, size, "no sensor probed"); return -1;
}

static int16_t le16(const uint8_t *p) { return (int16_t)(uint16_t)((unsigned)p[0] | ((unsigned)p[1] << 8)); }
static int16_t be16(const uint8_t *p) { return (int16_t)(uint16_t)(((unsigned)p[0] << 8) | (unsigned)p[1]); }

int imu_read_raw(const struct imu_device *d, struct imu_raw *r)
{
    uint8_t st = 0, b[14];
    memset(r, 0, sizeof(*r));
    if (d->map == IMU_MAP_CHIP) {
        /* Status first: drdy_acc clears when the data registers are read. A
         * burst read of X..Z keeps the LSB/MSB pairs from one conversion. */
        if (imu_bus_read(d->bus, d->acc_addr, IMU_ACC_STATUS, &st, 1)) return -1;
        r->acc_new = (uint8_t)(st >> 7);
        if (imu_bus_read(d->bus, d->acc_addr, IMU_ACC_X_LSB, b, 6)) return -1;
        for (int i = 0; i < 3; ++i) r->acc[i] = le16(b + 2 * i);
        if (imu_bus_read(d->bus, d->gyr_addr, IMU_GYR_INT_STAT_1, &st, 1)) return -1;
        r->gyr_new = (uint8_t)(st >> 7);
        if (imu_bus_read(d->bus, d->gyr_addr, IMU_GYR_RATE_X_LSB, b, 6)) return -1;
        for (int i = 0; i < 3; ++i) r->gyr[i] = le16(b + 2 * i);
        return 0;
    }
    if (d->map == IMU_MAP_INVENSENSE) {
        if (imu_bus_read(d->bus, d->acc_addr, INV_INT_STATUS, &st, 1)) return -1;
        r->acc_new = r->gyr_new = (uint8_t)(st & 1u);
        if (imu_bus_read(d->bus, d->acc_addr, INV_ACCEL_XOUT_H, b, 14)) return -1;
        for (int i = 0; i < 3; ++i) { r->acc[i] = be16(b + 2 * i); r->gyr[i] = be16(b + 8 + 2 * i); }
        return 0;
    }
    errno = ENODEV; return -1;
}
void imu_scale(const struct imu_device *d, const struct imu_raw *r, struct imu_sample *s)
{
    for (int i = 0; i < 3; ++i) {
        s->acc_g[i] = (float)r->acc[i] / d->acc_lsb_per_g;
        s->gyr_dps[i] = (float)r->gyr[i] / d->gyr_lsb_per_dps;
    }
    s->acc_new = r->acc_new; s->gyr_new = r->gyr_new;
}
