#include "imu_filter.h"
#include <math.h>
#include <string.h>

#define RAD2DEG 57.29577951308232f

void imu_filter_init(struct imu_filter *f, float tau_s)
{
    f->tau_s = tau_s > 0.0f ? tau_s : 0.5f;
    f->acc_min_g = 0.7f; f->acc_max_g = 1.3f;
    f->roll_deg = f->pitch_deg = 0.0f;
    f->initialised = 0; f->gyro_only_steps = 0;
}
void imu_accel_tilt(const float a[3], float *roll, float *pitch)
{
    *roll = atan2f(a[1], a[2]) * RAD2DEG;
    *pitch = atan2f(-a[0], sqrtf(a[1] * a[1] + a[2] * a[2])) * RAD2DEG;
}
static float wrap180(float x)
{
    while (x > 180.0f) x -= 360.0f;
    while (x <= -180.0f) x += 360.0f;
    return x;
}
void imu_filter_step(struct imu_filter *f, const struct imu_sample *s, float dt)
{
    float roll_acc, pitch_acc;
    imu_accel_tilt(s->acc_g, &roll_acc, &pitch_acc);
    if (!f->initialised || dt <= 0.0f || dt > 0.5f) {
        f->roll_deg = roll_acc; f->pitch_deg = pitch_acc; f->initialised = 1;
        return;
    }
    float roll_p = f->roll_deg + s->gyr_dps[0] * dt;
    float pitch_p = f->pitch_deg + s->gyr_dps[1] * dt;
    float mag = sqrtf(s->acc_g[0] * s->acc_g[0] + s->acc_g[1] * s->acc_g[1] + s->acc_g[2] * s->acc_g[2]);
    if (mag < f->acc_min_g || mag > f->acc_max_g) {
        ++f->gyro_only_steps;
        f->roll_deg = wrap180(roll_p); f->pitch_deg = pitch_p;
        return;
    }
    float k = dt / (f->tau_s + dt); /* 1 - a */
    f->roll_deg = wrap180(roll_p + k * wrap180(roll_acc - roll_p));
    f->pitch_deg = pitch_p + k * (pitch_acc - pitch_p);
}

void imu_quat_from_euler(float roll, float pitch, float yaw, float q[4])
{
    float r = roll / (2 * RAD2DEG), p = pitch / (2 * RAD2DEG), y = yaw / (2 * RAD2DEG);
    float cr = cosf(r), sr = sinf(r), cp = cosf(p), sp = sinf(p), cy = cosf(y), sy = sinf(y);
    q[0] = cr*cp*cy + sr*sp*sy; q[1] = sr*cp*cy - cr*sp*sy;
    q[2] = cr*sp*cy + sr*cp*sy; q[3] = cr*cp*sy - sr*sp*cy;
}
void imu_quat_euler(const float q[4], float *roll, float *pitch, float *yaw)
{
    float w = q[0], x = q[1], y = q[2], z = q[3];
    float sp = 2*(w*y - z*x);
    sp = fmaxf(-1, fminf(1, sp));
    *roll = atan2f(2*(w*x + y*z), 1-2*(x*x+y*y)) * RAD2DEG;
    *pitch = asinf(sp) * RAD2DEG;
    *yaw = atan2f(2*(w*z + x*y), 1-2*(y*y+z*z)) * RAD2DEG;
}
void imu_mahony_init(struct imu_mahony *f, float kp, float ki)
{
    memset(f, 0, sizeof(*f)); f->q[0] = 1; f->kp = kp; f->ki = ki;
}
void imu_mahony_rezero(struct imu_mahony *f)
{
    float r, p, y;
    imu_quat_euler(f->q, &r, &p, &y);
    /* Left multiply by world-Z rotation -yaw; preserve gravity and bias. */
    float c = cosf(-y / (2 * RAD2DEG)), s = sinf(-y / (2 * RAD2DEG));
    float w = f->q[0], x = f->q[1], yy = f->q[2], z = f->q[3];
    f->q[0] = c*w - s*z; f->q[1] = c*x - s*yy;
    f->q[2] = c*yy + s*x; f->q[3] = c*z + s*w;
}
void imu_mahony_step(struct imu_mahony *f, const struct imu_sample *s, float dt)
{
    float mag = sqrtf(s->acc_g[0]*s->acc_g[0]+s->acc_g[1]*s->acc_g[1]+s->acc_g[2]*s->acc_g[2]);
    int gravity = isfinite(mag) && mag >= 0.7f && mag <= 1.3f;
    if (!f->initialised) {
        if (!gravity) return;
        float r, p;
        imu_accel_tilt(s->acc_g, &r, &p);
        imu_quat_from_euler(r, p, 0, f->q); f->initialised = 1;
        return;
    }
    if (!(dt > 0 && dt <= 0.5f)) return; /* hold across invalid intervals */
    for (int i = 0; i < 3; ++i) if (!isfinite(s->gyr_dps[i])) return;
    float w = f->q[0], x = f->q[1], y = f->q[2], z = f->q[3];
    float e[3] = {0,0,0};
    if (gravity) {
        float a[3] = {s->acc_g[0]/mag, s->acc_g[1]/mag, s->acc_g[2]/mag};
        float v[3] = {2*(x*z-w*y), 2*(w*x+y*z), 1-2*(x*x+y*y)};
        e[0] = a[1]*v[2]-a[2]*v[1]; e[1] = a[2]*v[0]-a[0]*v[2]; e[2] = a[0]*v[1]-a[1]*v[0];
    }
    float g[3];
    for (int i = 0; i < 3; ++i) {
        /* Bounded integral prevents windup during long disturbances. */
        if (f->ki > 0 && gravity)
            f->integral[i] = fmaxf(-0.35f, fminf(0.35f, f->integral[i] + f->ki*e[i]*dt));
        if (f->ki == 0) f->integral[i] = 0;
        g[i] = (s->gyr_dps[i]-f->bias_dps[i])/RAD2DEG + f->kp*e[i] + f->integral[i];
    }
    /* Exponential quaternion increment, exact for constant corrected rate. */
    float rate = sqrtf(g[0]*g[0]+g[1]*g[1]+g[2]*g[2]), half = 0.5f*rate*dt;
    float c = cosf(half), k = rate > 1e-8f ? sinf(half)/rate : 0.5f*dt;
    float dx = g[0]*k, dy = g[1]*k, dz = g[2]*k;
    f->q[0] = w*c-x*dx-y*dy-z*dz;
    f->q[1] = w*dx+x*c+y*dz-z*dy;
    f->q[2] = w*dy-x*dz+y*c+z*dx;
    f->q[3] = w*dz+x*dy-y*dx+z*c;
    float norm = 0;
    for (int i = 0; i < 4; ++i) norm += f->q[i]*f->q[i];
    norm = sqrtf(norm);
    for (int i = 0; i < 4; ++i) f->q[i] /= norm;
}
void imu_bias_add(struct imu_bias_cal *c, const struct imu_sample *s)
{
    double mag2 = 0;
    ++c->n;
    for (int i = 0; i < 3; ++i) {
        double g = s->gyr_dps[i];
        mag2 += (double)s->acc_g[i]*s->acc_g[i];
        if (!isfinite(g) || fabs(g) > 5) c->moving = 1;
        c->sum[i] += g; c->sumsq[i] += g*g;
    }
    if (!(mag2 >= 0.95*0.95 && mag2 <= 1.05*1.05)) c->moving = 1;
}
int imu_bias_finish(const struct imu_bias_cal *c, float bias[3])
{
    if (c->moving || c->n < 2) return -1;
    for (int i = 0; i < 3; ++i) {
        double mean = c->sum[i]/c->n, var = c->sumsq[i]/c->n-mean*mean;
        if (!isfinite(mean) || var > 0.04) return -1;
    }
    for (int i = 0; i < 3; ++i) bias[i] = (float)(c->sum[i]/c->n);
    return 0;
}
