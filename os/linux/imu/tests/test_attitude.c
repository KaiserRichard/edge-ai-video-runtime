/* Deterministic host simulation, independent gravity fixtures, no hardware. */
#include "imu_filter.h"
#include "oled_attitude.h"
#include <math.h>
#include <stdio.h>
#include <string.h>
static unsigned checks, failures;
#define CHECK(c) do { ++checks; if (!(c)) { ++failures; fprintf(stderr, "FAIL %d: %s\n", __LINE__, #c); } } while (0)
#define NEAR(a,b,t) CHECK(fabs((double)(a)-(double)(b)) <= (t))
static float radians(float d) { return d * 0.0174532925199433f; }
static struct imu_sample gravity(float r, float p)
{
    struct imu_sample s; memset(&s, 0, sizeof(s));
    s.acc_g[0] = -sinf(radians(p));
    s.acc_g[1] = sinf(radians(r))*cosf(radians(p));
    s.acc_g[2] = cosf(radians(r))*cosf(radians(p));
    return s;
}
static void angles(const struct imu_mahony *f, float r, float p, float y, float tol)
{
    float rr, pp, yy;
    imu_quat_euler(f->q, &rr, &pp, &yy);
    NEAR(rr,r,tol); NEAR(pp,p,tol); NEAR(yy,y,tol);
}
static void test_mahony(void)
{
    struct imu_mahony f;
    imu_mahony_init(&f, 2, 0);
    f.initialised = 1; /* force convergence rather than accel initialisation */
    struct imu_sample s = gravity(30,-20);
    for (int i = 0; i < 3000; ++i) imu_mahony_step(&f, &s, 0.005f);
    float r,p,y; imu_quat_euler(f.q,&r,&p,&y);
    NEAR(r,30,0.02); NEAR(p,-20,0.02); /* heading is unobservable */
    for (int axis = 0; axis < 3; ++axis) {
        imu_mahony_init(&f,2,0.05f);
        s = gravity(0,0); imu_mahony_step(&f,&s,0);
        for (int i = 0; i < 2000; ++i) {
            float a = (float)i*0.005f*12;
            s = gravity(axis == 0 ? a : 0, axis == 1 ? a : 0);
            s.gyr_dps[axis] = 12;
            imu_mahony_step(&f,&s,0.005f);
            double norm = 0;
            for (int j = 0; j < 4; ++j) norm += (double)f.q[j]*f.q[j];
            NEAR(norm,1,5e-7);
        }
        /* Quaternion comparison avoids Euler singularity beyond 90 pitch. */
        float expected[4]; imu_quat_from_euler(axis == 0 ? 120 : 0, axis == 1 ? 120 : 0, axis == 2 ? 120 : 0,expected);
        double dot = 0;
        for (int j = 0; j < 4; ++j) dot += (double)f.q[j]*expected[j];
        CHECK(fabs(dot) > 0.99999);
    }
    imu_mahony_init(&f,2,0.2f); s = gravity(0,0);
    imu_mahony_step(&f,&s,0);
    s.gyr_dps[0] = 0.6f; s.gyr_dps[1] = -0.4f; s.gyr_dps[2] = 0.3f;
    for (int i = 0; i < 24000; ++i) imu_mahony_step(&f,&s,0.005f);
    imu_quat_euler(f.q,&r,&p,&y);
    NEAR(r,0,0.01); NEAR(p,0,0.01);
    NEAR(f.integral[0],-radians(0.6f),0.0001); NEAR(f.integral[1],radians(0.4f),0.0001);
    NEAR(y,36,0.05); /* deliberately proves lack of Z-bias observability */
    struct imu_bias_cal c; memset(&c,0,sizeof(c));
    for (int i = 0; i < 400; ++i) imu_bias_add(&c,&s);
    imu_mahony_init(&f,2,0.05f);
    CHECK(!imu_bias_finish(&c,f.bias_dps));
    for (int i = 0; i < 24000; ++i) imu_mahony_step(&f,&s,0.005f);
    angles(&f,0,0,0,0.001f);
    s.gyr_dps[0] = 20; imu_bias_add(&c,&s);
    CHECK(imu_bias_finish(&c,f.bias_dps) == -1);
    memset(&c,0,sizeof(c)); s.gyr_dps[0] = 0;
    for (int i = 0; i < 100; ++i) { s.gyr_dps[1] = i%2 ? 1 : -1; imu_bias_add(&c,&s); }
    CHECK(imu_bias_finish(&c,f.bias_dps) == -1); /* variance rejects motion */
    imu_quat_from_euler(32,-21,73,f.q);
    float saved[4]; memcpy(saved,f.q,sizeof(saved));
    s.gyr_dps[0] = NAN; imu_mahony_step(&f,&s,0.005f);
    CHECK(!memcmp(saved,f.q,sizeof(saved)));
    imu_mahony_step(&f,&s,0); imu_mahony_step(&f,&s,1);
    CHECK(!memcmp(saved,f.q,sizeof(saved)));
    imu_mahony_rezero(&f); angles(&f,32,-21,0,0.0001f);
    imu_mahony_init(&f,2,0.05f); s = gravity(0,0); s.acc_g[2] = 2;
    imu_mahony_step(&f,&s,0.005f); CHECK(!f.initialised);
    s = gravity(0,0); imu_mahony_step(&f,&s,0);
    s.acc_g[2] = 2; s.gyr_dps[2] = 90;
    for (int i = 0; i < 200; ++i) imu_mahony_step(&f,&s,0.005f);
    angles(&f,0,0,90,0.001f); /* gravity correction gated */
}
static void test_projection(void)
{
    float q[4], xy[3][2];
    imu_quat_from_euler(0,0,0,q); attitude_project(q,xy);
    NEAR(xy[0][0],14.1421356,1e-5); NEAR(xy[0][1],8.164966,1e-5);
    NEAR(xy[1][0],-14.1421356,1e-5); NEAR(xy[1][1],8.164966,1e-5);
    NEAR(xy[2][0],0,1e-5); NEAR(xy[2][1],-16.329932,1e-5);
    const float level[3][2] = {{14.1421356f,8.164966f},{-14.1421356f,8.164966f},{0,-16.329932f}};
    for (int axis = 0; axis < 3; ++axis) {
        imu_quat_from_euler(axis == 0 ? 90 : 0, axis == 1 ? 90 : 0, axis == 2 ? 90 : 0,q);
        attitude_project(q,xy);
        for (int j = 0; j < 2; ++j) {
            NEAR(xy[axis][j],level[axis][j],1e-5);
            int next = (axis+1)%3, last = (axis+2)%3;
            NEAR(xy[next][j],level[last][j],1e-5);
            NEAR(xy[last][j],-level[next][j],1e-5);
        }
    }
    const float pose[6][3] = {{0,0,0},{30,0,0},{0,45,0},{0,0,90},{30,-25,60},{180,0,0}};
    const int counts[6] = {570,565,559,567,543,559}, ymin[6] = {3,1,13,3,4,11};
    for (int k = 0; k < 6; ++k) {
        struct oled_fb fb;
        imu_quat_from_euler(pose[k][0],pose[k][1],pose[k][2],q);
        attitude_render(&fb,q,20,1);
        int n = 0, left = 128, right = -1, top = 64, bottom = -1;
        for (int yy = 0; yy < 64; ++yy) for (int xx = 0; xx < 128; ++xx)
            if (oled_pixel(&fb,(unsigned)xx,(unsigned)yy)) {
                ++n;
                if (xx < left) left = xx;
                if (xx > right) right = xx;
                if (yy < top) top = yy;
                if (yy > bottom) bottom = yy;
            }
        CHECK(n == counts[k]); CHECK(left == 0 && right == 112 && top == ymin[k] && bottom == 62);
    }
    struct oled_fb fb; oled_clear(&fb);
    oled_line(&fb,-5,-5,5,5);
    for (unsigned i = 0; i < 6; ++i) CHECK(oled_pixel(&fb,i,i));
    CHECK(sizeof(fb) == 1024);
}
int main(void)
{
    test_mahony(); test_projection();
    printf("test_attitude: %u checks, %u failures\n",checks,failures);
    return failures ? 1 : 0;
}
