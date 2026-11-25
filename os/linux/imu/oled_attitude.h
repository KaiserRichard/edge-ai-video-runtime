#ifndef HEA_OLED_ATTITUDE_H
#define HEA_OLED_ATTITUDE_H
#include "oled.h"
/* Rotated basis columns R e_i, projected onto fixed orthonormal view rows.
 * Outputs displacement in pixels (screen y points down). */
void attitude_project(const float q[4], float xy[3][2]);
void attitude_render(struct oled_fb *fb, const float q[4], float fps, int valid);
#endif
