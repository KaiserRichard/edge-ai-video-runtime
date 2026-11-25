#ifndef HEA_IMU_RING_H
#define HEA_IMU_RING_H
#include <stddef.h>
#include <stdint.h>

/* IMU ring ABI v2, same conventions as the camera ring (linux/camera/ring.h):
 * native little endian, 64-byte header published by a release store of
 * `ready`, fixed 128-byte slots guarded by a per-slot sequence counter (odd
 * while being written). Slot for sample i is i % slots. `head` is the number
 * of published samples (latest index = head - 1). */
#define IMU_RING_MAGIC 0x49414548u /* "HEAI" */
#define IMU_RING_VERSION 2u
#define IMU_RING_STRIDE 128u
#define IMU_RING_MAX_SLOTS 65536u
struct imu_ring_header {
    uint32_t magic, version, slots, stride, rate_hz, map, ready, reserved0;
    uint64_t head;
    uint8_t reserved[24];
};
/* Slot words after the 8-byte seq (all uint32, floats stored as IEEE-754 bits):
 * 0 index, 1 flags, 2 t_ns low, 3 t_ns high, 4..6 acc g, 7..9 gyro dps,
 * 10 roll deg, 11 pitch deg, 12 i2c read ns, 13 period ns; 14..17 quaternion wxyz, 18..20 Mahony roll/pitch/yaw deg;
 * 21..29 reserved zero. Legacy tilt fields 10/11 retain their meaning. */
#define IMU_RING_WORDS 30u
#define IMU_FLAG_ATT_VALID 16u
#define IMU_FLAG_ACC_NEW 1u
#define IMU_FLAG_GYR_NEW 2u
#define IMU_FLAG_READ_ERROR 4u  /* I2C read failed; values repeat the last good sample */
#define IMU_FLAG_MISSED 8u      /* one or more releases were skipped before this one */
struct imu_record {
    uint32_t index, flags;
    uint64_t t_ns;              /* CLOCK_MONOTONIC_RAW after the I2C read */
    float acc_g[3], gyr_dps[3], roll_deg, pitch_deg;
    uint32_t i2c_ns, period_ns;
    float q[4], attitude_deg[3];
};
struct imu_ring {
    int fd, owner;
    size_t size;
    struct imu_ring_header *h;
    char name[128];
};
int imu_ring_create(struct imu_ring *r, const char *name, uint32_t slots, uint32_t rate_hz, uint32_t map,
                    char *err, size_t err_size);
int imu_ring_open(struct imu_ring *r, const char *name, char *err, size_t err_size);
void imu_ring_close(struct imu_ring *r);
void imu_ring_write(struct imu_ring *r, const struct imu_record *rec);
/* 0 success, 1 overwritten/unpublished, 2 torn/busy; one bounded attempt. */
int imu_ring_read(const struct imu_ring *r, uint32_t index, struct imu_record *out);
uint64_t imu_ring_head(const struct imu_ring *r);
/* Latest sample with up to `tries` attempts; 0 success, 1 empty, 2 torn. */
int imu_ring_latest(const struct imu_ring *r, struct imu_record *out, int tries);
#endif
