#ifndef HEA_IMU_FILTER_H
#define HEA_IMU_FILTER_H
#include "imu_sensor.h"

/* Complementary filter for roll/pitch (degrees). Per step:
 *   predicted = angle + rate * dt          (gyro integration)
 *   angle     = predicted + (1 - a) * wrap(accel_angle - predicted)
 * with a = tau / (tau + dt), so the accelerometer correction is a first-order
 * low-pass with time constant tau and the gyro path is the complementary
 * high-pass. When |acc| is outside [acc_min_g, acc_max_g] the accelerometer
 * is not a gravity reference (linear acceleration) and only the gyro is used. */
struct imu_filter {
    float tau_s, acc_min_g, acc_max_g;
    float roll_deg, pitch_deg;
    int initialised;
    unsigned long gyro_only_steps;
};
void imu_filter_init(struct imu_filter *f, float tau_s);
/* dt_s <= 0 or > 0.5 s re-initialises from the accelerometer. */
void imu_filter_step(struct imu_filter *f, const struct imu_sample *s, float dt_s);
void imu_accel_tilt(const float acc_g[3], float *roll_deg, float *pitch_deg);

/* Hamilton quaternion [w,x,y,z], active body -> world, right handed, +Z up.
 * Startup gyro bias is in dps; integral correction is in rad/s. */
struct imu_mahony {
    float q[4], integral[3], bias_dps[3], kp, ki;
    int initialised;
};
void imu_mahony_init(struct imu_mahony *f, float kp, float ki);
void imu_mahony_step(struct imu_mahony *f, const struct imu_sample *s, float dt_s);
void imu_quat_euler(const float q[4], float *roll, float *pitch, float *yaw);
void imu_quat_from_euler(float roll, float pitch, float yaw, float q[4]);
void imu_mahony_rezero(struct imu_mahony *f);

/* Reject obvious motion; stillness remains an operator assumption. */
struct imu_bias_cal {
    unsigned n;
    double sum[3], sumsq[3];
    int moving;
};
void imu_bias_add(struct imu_bias_cal *c, const struct imu_sample *s);
int imu_bias_finish(const struct imu_bias_cal *c, float bias_dps[3]);
#endif
