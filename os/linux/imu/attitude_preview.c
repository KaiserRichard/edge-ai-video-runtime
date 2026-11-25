/* Host-only preview: uses the exact renderer linked into hea_oled. */
#include "oled_attitude.h"
#include "imu_filter.h"
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv)
{
    if (argc != 5) { fprintf(stderr, "usage: attitude_preview ROLL_DEG PITCH_DEG YAW_DEG OUT.pbm\n"); return 2; }
    float angle[3], q[4];
    for (int i = 0; i < 3; ++i) {
        char *end;
        errno = 0; angle[i] = strtof(argv[i+1], &end);
        if (errno || end == argv[i+1] || *end || !isfinite(angle[i]) || fabsf(angle[i]) > 36000) return 2;
    }
    imu_quat_from_euler(angle[0], angle[1], angle[2], q);
    struct oled_fb fb;
    attitude_render(&fb, q, 20, 1);
    if (oled_write_pbm(&fb, argv[4])) { perror("preview"); return 1; }
    return 0;
}
