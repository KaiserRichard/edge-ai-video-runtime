#ifndef HEA_IMU_SENSOR_H
#define HEA_IMU_SENSOR_H
#include "imu_bus.h"
#include <stdint.h>

/* ---- IMU sensor two-die register map (accelerometer die) ---- */
#define IMU_ACC_ADDR_LO 0x18u
#define IMU_ACC_ADDR_HI 0x19u
#define IMU_ACC_CHIP_ID 0x00u
#define IMU_ACC_CHIP_ID_VALUE 0x1Eu
#define IMU_ACC_ERR_REG 0x02u
#define IMU_ACC_STATUS 0x03u      /* bit7 drdy_acc */
#define IMU_ACC_X_LSB 0x12u       /* X,Y,Z little-endian int16, 6 bytes */
#define IMU_ACC_INT_STAT_1 0x1Du
#define IMU_ACC_CONF 0x40u        /* [7:4] bwp, [3:0] odr */
#define IMU_ACC_RANGE 0x41u
#define IMU_ACC_PWR_CONF 0x7Cu    /* 0x00 active, 0x03 suspend */
#define IMU_ACC_PWR_CTRL 0x7Du    /* 0x00 off, 0x04 on */
#define IMU_ACC_SOFTRESET 0x7Eu
#define IMU_SOFTRESET_CMD 0xB6u
#define IMU_ACC_BWP_OSR4 0x08u
#define IMU_ACC_BWP_OSR2 0x09u
#define IMU_ACC_BWP_NORMAL 0x0Au
/* Datasheet timing (microseconds). */
#define IMU_ACC_RESET_WAIT_US 1000u
#define IMU_ACC_PWR_CONF_WAIT_US 450u
#define IMU_ACC_PWR_CTRL_WAIT_US 50000u

/* ---- IMU sensor register map (gyroscope die) ---- */
#define IMU_GYR_ADDR_LO 0x68u
#define IMU_GYR_ADDR_HI 0x69u
#define IMU_GYR_CHIP_ID 0x00u
#define IMU_GYR_CHIP_ID_VALUE 0x0Fu
#define IMU_GYR_RATE_X_LSB 0x02u  /* X,Y,Z little-endian int16, 6 bytes */
#define IMU_GYR_INT_STAT_1 0x0Au  /* bit7 gyro_drdy */
#define IMU_GYR_RANGE 0x0Fu
#define IMU_GYR_BANDWIDTH 0x10u   /* bit7 reads back as 1 */
#define IMU_GYR_LPM1 0x11u        /* 0x00 normal */
#define IMU_GYR_SOFTRESET 0x14u
#define IMU_GYR_INT_CTRL 0x15u
#define IMU_GYR_RESET_WAIT_US 30000u

/* ---- InvenSense-style map (fallback) ---- */
#define INV_WHO_AM_I 0x75u
#define INV_SMPLRT_DIV 0x19u
#define INV_CONFIG 0x1Au
#define INV_GYRO_CONFIG 0x1Bu
#define INV_ACCEL_CONFIG 0x1Cu
#define INV_INT_STATUS 0x3Au         /* bit0 data ready */
#define INV_ACCEL_XOUT_H 0x3Bu       /* 14 bytes big-endian: acc, temp, gyro */
#define INV_PWR_MGMT_1 0x6Bu
#define INV_RESET_WAIT_US 100000u

enum imu_map { IMU_MAP_NONE = 0, IMU_MAP_CHIP = 1, IMU_MAP_INVENSENSE = 2 };
enum imu_map_request { IMU_REQ_AUTO, IMU_REQ_CHIP, IMU_REQ_INVENSENSE };

struct imu_config {
    /* IMU sensor map */
    uint8_t acc_range;   /* 0:+-3 g 1:+-6 g 2:+-12 g 3:+-24 g */
    uint8_t acc_odr;     /* 0x05 12.5 Hz .. 0x0C 1600 Hz */
    uint8_t acc_bwp;     /* IMU_ACC_BWP_* */
    uint8_t gyr_range;   /* 0:+-2000 1:+-1000 2:+-500 3:+-250 4:+-125 dps */
    uint8_t gyr_bw;      /* 0x00..0x07 ODR/filter code */
    /* InvenSense map */
    uint8_t inv_afs;     /* 0..3: +-2/4/8/16 g */
    uint8_t inv_fs;      /* 0..3: +-250/500/1000/2000 dps */
    uint8_t inv_dlpf;    /* CONFIG DLPF_CFG 0..6 */
    uint8_t inv_div;     /* SMPLRT_DIV */
};
void imu_config_default(struct imu_config *c);

struct imu_device {
    const struct imu_bus *bus;
    enum imu_map map;
    uint8_t acc_addr, gyr_addr; /* same address for the InvenSense map */
    uint8_t chip_id_acc, chip_id_gyr;
    float acc_lsb_per_g, gyr_lsb_per_dps;
    struct imu_config cfg;
};

struct imu_raw { int16_t acc[3], gyr[3]; uint8_t acc_new, gyr_new; };
struct imu_sample { float acc_g[3], gyr_dps[3]; uint8_t acc_new, gyr_new; };

/* Probe the bus. Writes a human-readable report of every address tried to
 * `report` (always NUL-terminated). Returns 0 and fills d->map/addresses on
 * success, -1 when no supported sensor answers. acc_addr/gyr_addr 0 = try both. */
int imu_probe(struct imu_device *d, const struct imu_bus *bus, enum imu_map_request req,
              uint8_t acc_addr, uint8_t gyr_addr, char *report, size_t report_size);
/* Soft reset, power-on sequence, range/ODR/bandwidth, read-back verification.
 * Returns 0, or -1 with a message in err. */
int imu_configure(struct imu_device *d, const struct imu_config *cfg, char *err, size_t err_size);
/* One sample: data-ready flags + 6-axis burst read(s). 0 or -1. */
int imu_read_raw(const struct imu_device *d, struct imu_raw *r);
void imu_scale(const struct imu_device *d, const struct imu_raw *r, struct imu_sample *s);

/* Scale factors, exposed for tests and docs. Return 0 for invalid codes. */
float imu_chip_acc_lsb_per_g(uint8_t range);
float imu_chip_gyr_lsb_per_dps(uint8_t range);
float imu_inv_acc_lsb_per_g(uint8_t afs);
float imu_inv_gyr_lsb_per_dps(uint8_t fs);
/* Accelerometer ODR code -> Hz (0 invalid); gyro bandwidth code -> ODR Hz. */
float imu_chip_acc_odr_hz(uint8_t odr);
float imu_chip_gyr_odr_hz(uint8_t bw);
const char *imu_map_name(enum imu_map m);
#endif
