#include "oled_attitude.h"
#include "imu_filter.h"
#include <math.h>
#include <stdio.h>

void attitude_project(const float q[4], float xy[3][2])
{
    float w = q[0], x = q[1], y = q[2], z = q[3];
    float basis[3][3] = {
        {1-2*(y*y+z*z), 2*(x*y+w*z), 2*(x*z-w*y)},
        {2*(x*y-w*z), 1-2*(x*x+z*z), 2*(y*z+w*x)},
        {2*(x*z+w*y), 2*(y*z-w*x), 1-2*(x*x+y*y)}
    };
    for (int i = 0; i < 3; ++i) {
        xy[i][0] = 20 * (0.70710678f*basis[i][0]-0.70710678f*basis[i][1]);
        xy[i][1] = 20 * (0.40824829f*basis[i][0]+0.40824829f*basis[i][1]-0.81649658f*basis[i][2]);
    }
}
void attitude_render(struct oled_fb *fb, const float q[4], float fps, int valid)
{
    oled_clear(fb);
    char line[32];
    if (!valid) {
        oled_text(fb, 2, 1, "IMU: NO FRESH DATA");
        oled_text(fb, 4, 1, "CALIBRATE / WAIT");
        return;
    }
    float xy[3][2], r, p, y;
    attitude_project(q, xy);
    const int cx = 64, cy = 26;
    for (int i = 0; i < 3; ++i) {
        float dx = xy[i][0], dy = xy[i][1], len = hypotf(dx, dy);
        int ex = cx+(int)lroundf(dx), ey = cy+(int)lroundf(dy);
        oled_line(fb, cx, cy, ex, ey);
        if (len > 2) {
            float ux = dx/len, uy = dy/len;
            oled_line(fb, ex, ey, ex-(int)lroundf(4*ux-2*uy), ey-(int)lroundf(4*uy+2*ux));
            oled_line(fb, ex, ey, ex-(int)lroundf(4*ux+2*uy), ey-(int)lroundf(4*uy-2*ux));
        }
        int lx = ex + (dx >= 0 ? 3 : -8), ly = ey + (dy >= 0 ? 1 : -7);
        if (ly < 0) ly = 0;
        if (ly > 41) ly = 41;
        oled_label(fb, lx, ly, (char)('X'+i));
    }
    imu_quat_euler(q, &r, &p, &y);
    /* Two compact 21-character rows leave room for signed three-digit angles. */
    snprintf(line, sizeof(line), "R%+04.0f P%+04.0f DEG", (double)r, (double)p);
    oled_text(fb, 6, 0, line);
    snprintf(line, sizeof(line), "Y%+04.0f DEG F%4.1f FPS", (double)y, (double)fps);
    oled_text(fb, 7, 0, line);
}
