#ifndef HEA_IMU_BUS_H
#define HEA_IMU_BUS_H
#include <stddef.h>
#include <stdint.h>

/* Register-oriented I2C bus. Every call is one bus transaction (write of the
 * register address followed by a repeated-start read, or one write). Return 0
 * on success, -1 on NACK/I/O error (errno is set by the Linux backend). */
struct imu_bus {
    int (*read)(void *ctx, uint8_t addr, uint8_t reg, uint8_t *buf, size_t n);
    int (*write)(void *ctx, uint8_t addr, uint8_t reg, const uint8_t *buf, size_t n);
    /* Raw write without a register byte (the display's control byte goes first). */
    int (*raw_write)(void *ctx, uint8_t addr, const uint8_t *buf, size_t n);
    void (*delay_us)(void *ctx, uint32_t us);
    void *ctx;
};

static inline int imu_bus_read(const struct imu_bus *b, uint8_t a, uint8_t r, uint8_t *v, size_t n)
{ return b->read(b->ctx, a, r, v, n); }
static inline int imu_bus_write1(const struct imu_bus *b, uint8_t a, uint8_t r, uint8_t v)
{ return b->write(b->ctx, a, r, &v, 1); }
static inline void imu_bus_delay(const struct imu_bus *b, uint32_t us) { b->delay_us(b->ctx, us); }

/* Linux /dev/i2c-N backend (I2C_RDWR combined transfers). On non-Linux hosts
 * open fails with ENOSYS. Returns 0 or -1 with errno set and a reason in err. */
int imu_bus_linux_open(struct imu_bus *bus, const char *path, char *err, size_t err_size);
void imu_bus_linux_close(struct imu_bus *bus);

/* ---- Fake register-file backend (host tests and --backend fake) ---- */
#define IMU_FAKE_LOG 512u
struct imu_fake_op { uint64_t t_us; uint8_t addr, reg, value, is_write; };
struct imu_fake_device { uint8_t addr, present; uint8_t regs[256]; };
enum imu_fake_kind { IMU_FAKE_PLAIN = 0, IMU_FAKE_CHIP, IMU_FAKE_INVENSENSE };
struct imu_fake;
/* Device model state: sample presented when the sensor is powered, plus the
 * virtual times of the power-sequence writes so timing violations are visible. */
struct imu_fake_model {
    enum imu_fake_kind kind;
    uint8_t acc_addr, gyr_addr;
    int16_t acc[3], gyr[3];
    uint64_t acc_reset_us, acc_conf_us, acc_on_us, gyr_reset_us, inv_reset_us;
    uint8_t acc_reset_seen, acc_conf_seen, gyr_reset_seen, inv_reset_seen;
    unsigned ignored_writes;            /* writes dropped for violating a wait */
    void (*generator)(struct imu_fake *f); /* optional: refresh acc/gyr before a data read */
    uint64_t generated;
    void *user;
};
struct imu_fake {
    struct imu_fake_device dev[4];
    unsigned ndev;
    uint64_t now_us;                    /* virtual time, advanced by delay_us */
    uint32_t read_cost_us;              /* virtual time per transaction */
    struct imu_fake_op log[IMU_FAKE_LOG];
    unsigned nlog;
    unsigned fail_reads;                /* force this many read I/O errors */
    struct imu_fake_model model;
    unsigned raw_writes;                /* display writes */
    uint8_t raw_last[160];
    size_t raw_last_n;
    uint8_t raw_addr;
    void (*on_raw)(struct imu_fake *f, const uint8_t *buf, size_t n);
    void *raw_user;
};
void imu_fake_init(struct imu_fake *f, struct imu_bus *bus);
struct imu_fake_device *imu_fake_add(struct imu_fake *f, uint8_t addr);
struct imu_fake_device *imu_fake_find(struct imu_fake *f, uint8_t addr);
/* Install a device model; replaces any previous model. */
void imu_fake_model_chip(struct imu_fake *f, uint8_t acc_addr, uint8_t gyr_addr);
void imu_fake_model_invensense(struct imu_fake *f, uint8_t addr, uint8_t who_am_i);
/* Index of the first logged write to (addr, reg) at or after `from`, or -1. */
int imu_fake_find_write(const struct imu_fake *f, uint8_t addr, uint8_t reg, unsigned from);
#endif
