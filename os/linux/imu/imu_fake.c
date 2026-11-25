/* Fake I2C register file with simple models of the two IMU register maps.
 * The models enforce the datasheet waits: a write that arrives too soon after
 * a soft reset or an accelerometer power-configuration change is ignored, and
 * accelerometer data reads as zero until the power-on sequence has completed.
 * Data is SYNTHETIC; nothing here is a hardware measurement. */
#include "imu_bus.h"
#include "imu_sensor.h"
#include <errno.h>
#include <string.h>

static void log_op(struct imu_fake *f, uint8_t addr, uint8_t reg, uint8_t value, uint8_t is_write)
{
    if (f->nlog < IMU_FAKE_LOG)
        f->log[f->nlog++] = (struct imu_fake_op){ f->now_us, addr, reg, value, is_write };
}
struct imu_fake_device *imu_fake_find(struct imu_fake *f, uint8_t addr)
{
    for (unsigned i = 0; i < f->ndev; ++i)
        if (f->dev[i].addr == addr && f->dev[i].present) return &f->dev[i];
    return NULL;
}
struct imu_fake_device *imu_fake_add(struct imu_fake *f, uint8_t addr)
{
    for (unsigned i = 0; i < f->ndev; ++i)
        if (f->dev[i].addr == addr) { f->dev[i].present = 1; return &f->dev[i]; }
    if (f->ndev >= sizeof(f->dev) / sizeof(f->dev[0])) return NULL;
    struct imu_fake_device *d = &f->dev[f->ndev++];
    memset(d, 0, sizeof(*d)); d->addr = addr; d->present = 1;
    return d;
}
int imu_fake_find_write(const struct imu_fake *f, uint8_t addr, uint8_t reg, unsigned from)
{
    for (unsigned i = from; i < f->nlog; ++i)
        if (f->log[i].is_write && f->log[i].addr == addr && f->log[i].reg == reg) return (int)i;
    return -1;
}

static void put16le(uint8_t *p, int16_t v) { uint16_t u = (uint16_t)v; p[0] = (uint8_t)u; p[1] = (uint8_t)(u >> 8); }
static void put16be(uint8_t *p, int16_t v) { uint16_t u = (uint16_t)v; p[0] = (uint8_t)(u >> 8); p[1] = (uint8_t)u; }

static void imu_chip_acc_defaults(struct imu_fake_device *d)
{
    memset(d->regs, 0, sizeof(d->regs));
    d->regs[IMU_ACC_CHIP_ID] = IMU_ACC_CHIP_ID_VALUE;
    d->regs[IMU_ACC_CONF] = 0xA8u; d->regs[IMU_ACC_RANGE] = 0x01u;
    d->regs[IMU_ACC_PWR_CONF] = 0x03u; d->regs[IMU_ACC_PWR_CTRL] = 0x00u;
}
static void imu_chip_gyr_defaults(struct imu_fake_device *d)
{
    memset(d->regs, 0, sizeof(d->regs));
    d->regs[IMU_GYR_CHIP_ID] = IMU_GYR_CHIP_ID_VALUE;
    d->regs[IMU_GYR_BANDWIDTH] = 0x80u;
}
static int acc_powered(const struct imu_fake *f, const struct imu_fake_device *d)
{
    const struct imu_fake_model *m = &f->model;
    return d->regs[IMU_ACC_PWR_CONF] == 0x00u && d->regs[IMU_ACC_PWR_CTRL] == 0x04u &&
           f->now_us >= m->acc_on_us + IMU_ACC_PWR_CTRL_WAIT_US;
}
/* Returns 1 if the write is accepted into the register file. */
static int imu_chip_write(struct imu_fake *f, struct imu_fake_device *d, uint8_t reg, uint8_t v)
{
    struct imu_fake_model *m = &f->model;
    if (d->addr == m->acc_addr) {
        if (m->acc_reset_seen && f->now_us < m->acc_reset_us + IMU_ACC_RESET_WAIT_US) return 0;
        if (m->acc_conf_seen && f->now_us < m->acc_conf_us + IMU_ACC_PWR_CONF_WAIT_US) return 0;
        if (reg == IMU_ACC_SOFTRESET) {
            if (v == IMU_SOFTRESET_CMD) {
                imu_chip_acc_defaults(d); m->acc_reset_us = f->now_us; m->acc_reset_seen = 1; m->acc_conf_seen = 0;
            }
            return 0;
        }
        if (reg == IMU_ACC_PWR_CONF) { m->acc_conf_us = f->now_us; m->acc_conf_seen = 1; }
        if (reg == IMU_ACC_PWR_CTRL && v == 0x04u && d->regs[reg] != 0x04u) m->acc_on_us = f->now_us;
        if (reg == IMU_ACC_CONF) {
            uint8_t odr = v & 0x0Fu, bwp = (uint8_t)(v >> 4);
            d->regs[IMU_ACC_ERR_REG] = (odr < 0x05u || odr > 0x0Cu || bwp < 0x08u || bwp > 0x0Au)
                ? (uint8_t)(1u << 2) : 0u;
        }
        if (reg == IMU_ACC_RANGE) v &= 0x03u;
        if (reg == IMU_ACC_CHIP_ID || reg == IMU_ACC_STATUS || reg == IMU_ACC_ERR_REG) return 0;
        d->regs[reg] = v; return 1;
    }
    if (d->addr == m->gyr_addr) {
        if (m->gyr_reset_seen && f->now_us < m->gyr_reset_us + IMU_GYR_RESET_WAIT_US) return 0;
        if (reg == IMU_GYR_SOFTRESET) {
            if (v == IMU_SOFTRESET_CMD) { imu_chip_gyr_defaults(d); m->gyr_reset_us = f->now_us; m->gyr_reset_seen = 1; }
            return 0;
        }
        if (reg == IMU_GYR_CHIP_ID) return 0;
        if (reg == IMU_GYR_BANDWIDTH) v = (uint8_t)(v | 0x80u);
        d->regs[reg] = v; return 1;
    }
    d->regs[reg] = v; return 1;
}
static void imu_chip_before_read(struct imu_fake *f, struct imu_fake_device *d)
{
    struct imu_fake_model *m = &f->model;
    if (m->generator) m->generator(f);
    if (d->addr == m->acc_addr) {
        int on = acc_powered(f, d);
        for (unsigned i = 0; i < 3; ++i) put16le(&d->regs[IMU_ACC_X_LSB + 2 * i], on ? m->acc[i] : 0);
        d->regs[IMU_ACC_STATUS] = on ? 0x80u : 0x00u;
    } else if (d->addr == m->gyr_addr) {
        for (unsigned i = 0; i < 3; ++i) put16le(&d->regs[IMU_GYR_RATE_X_LSB + 2 * i], m->gyr[i]);
        d->regs[IMU_GYR_INT_STAT_1] = 0x80u;
    }
}
static int inv_write(struct imu_fake *f, struct imu_fake_device *d, uint8_t reg, uint8_t v)
{
    struct imu_fake_model *m = &f->model;
    if (m->inv_reset_seen && f->now_us < m->inv_reset_us + INV_RESET_WAIT_US) return 0;
    if (reg == INV_PWR_MGMT_1 && (v & 0x80u)) {
        uint8_t who = d->regs[INV_WHO_AM_I];
        memset(d->regs, 0, sizeof(d->regs));
        d->regs[INV_WHO_AM_I] = who; d->regs[INV_PWR_MGMT_1] = 0x40u; /* sleep after reset */
        m->inv_reset_us = f->now_us; m->inv_reset_seen = 1;
        return 0;
    }
    if (reg == INV_WHO_AM_I) return 0;
    d->regs[reg] = v; return 1;
}
static void inv_before_read(struct imu_fake *f, struct imu_fake_device *d)
{
    struct imu_fake_model *m = &f->model;
    if (m->generator) m->generator(f);
    int awake = !(d->regs[INV_PWR_MGMT_1] & 0x40u);
    for (unsigned i = 0; i < 3; ++i) {
        put16be(&d->regs[INV_ACCEL_XOUT_H + 2 * i], awake ? m->acc[i] : 0);
        put16be(&d->regs[INV_ACCEL_XOUT_H + 8 + 2 * i], awake ? m->gyr[i] : 0);
    }
    d->regs[INV_INT_STATUS] = awake ? 0x01u : 0x00u;
}

static int fake_read(void *ctx, uint8_t addr, uint8_t reg, uint8_t *buf, size_t n)
{
    struct imu_fake *f = ctx;
    f->now_us += f->read_cost_us;
    struct imu_fake_device *d = imu_fake_find(f, addr);
    if (!d) { errno = ENXIO; return -1; }
    if (f->fail_reads) { --f->fail_reads; errno = EIO; return -1; }
    if (f->model.kind == IMU_FAKE_CHIP) imu_chip_before_read(f, d);
    else if (f->model.kind == IMU_FAKE_INVENSENSE && addr == f->model.acc_addr) inv_before_read(f, d);
    for (size_t i = 0; i < n; ++i) {
        buf[i] = d->regs[(uint8_t)(reg + i)];
        log_op(f, addr, (uint8_t)(reg + i), buf[i], 0);
    }
    return 0;
}
static int fake_write(void *ctx, uint8_t addr, uint8_t reg, const uint8_t *buf, size_t n)
{
    struct imu_fake *f = ctx;
    f->now_us += f->read_cost_us;
    struct imu_fake_device *d = imu_fake_find(f, addr);
    if (!d) { errno = ENXIO; return -1; }
    for (size_t i = 0; i < n; ++i) {
        uint8_t r = (uint8_t)(reg + i);
        log_op(f, addr, r, buf[i], 1);
        int accepted;
        if (f->model.kind == IMU_FAKE_CHIP) accepted = imu_chip_write(f, d, r, buf[i]);
        else if (f->model.kind == IMU_FAKE_INVENSENSE && addr == f->model.acc_addr) accepted = inv_write(f, d, r, buf[i]);
        else { d->regs[r] = buf[i]; accepted = 1; }
        if (!accepted && !(r == IMU_ACC_SOFTRESET || r == IMU_GYR_SOFTRESET ||
                           (f->model.kind == IMU_FAKE_INVENSENSE && r == INV_PWR_MGMT_1)))
            ++f->model.ignored_writes;
    }
    return 0;
}
static int fake_raw_write(void *ctx, uint8_t addr, const uint8_t *buf, size_t n)
{
    struct imu_fake *f = ctx;
    if (!imu_fake_find(f, addr)) { errno = ENXIO; return -1; }
    ++f->raw_writes; f->raw_addr = addr;
    f->raw_last_n = n < sizeof(f->raw_last) ? n : sizeof(f->raw_last);
    memcpy(f->raw_last, buf, f->raw_last_n);
    if (f->on_raw) f->on_raw(f, buf, n);
    return 0;
}
static void fake_delay(void *ctx, uint32_t us) { ((struct imu_fake *)ctx)->now_us += us; }

void imu_fake_init(struct imu_fake *f, struct imu_bus *bus)
{
    memset(f, 0, sizeof(*f));
    bus->read = fake_read; bus->write = fake_write; bus->raw_write = fake_raw_write;
    bus->delay_us = fake_delay; bus->ctx = f;
}
void imu_fake_model_chip(struct imu_fake *f, uint8_t acc_addr, uint8_t gyr_addr)
{
    memset(&f->model, 0, sizeof(f->model));
    f->model.kind = IMU_FAKE_CHIP; f->model.acc_addr = acc_addr; f->model.gyr_addr = gyr_addr;
    struct imu_fake_device *a = imu_fake_add(f, acc_addr), *g = imu_fake_add(f, gyr_addr);
    if (a) imu_chip_acc_defaults(a);
    if (g) imu_chip_gyr_defaults(g);
}
void imu_fake_model_invensense(struct imu_fake *f, uint8_t addr, uint8_t who_am_i)
{
    memset(&f->model, 0, sizeof(f->model));
    f->model.kind = IMU_FAKE_INVENSENSE; f->model.acc_addr = addr; f->model.gyr_addr = addr;
    struct imu_fake_device *d = imu_fake_add(f, addr);
    if (d) { memset(d->regs, 0, sizeof(d->regs)); d->regs[INV_WHO_AM_I] = who_am_i; d->regs[INV_PWR_MGMT_1] = 0x40u; }
}
