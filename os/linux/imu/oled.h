#ifndef HEA_OLED_H
#define HEA_OLED_H
#include "imu_bus.h"
#include <stddef.h>
#include <stdint.h>

/* 128x64 monochrome I2C display, SSD1306-compatible command set (the SSD1315
 * controller accepts the same sequence). Framebuffer is 8 pages x 128 columns,
 * bit 0 of each byte is the top pixel of the page. */
#define OLED_W 128u
#define OLED_PAGES 8u
#define OLED_COLS 21u /* 6-pixel character cells */
#define OLED_CTRL_CMD 0x00u
#define OLED_CTRL_DATA 0x40u
struct oled_fb { uint8_t px[OLED_PAGES][OLED_W]; };

int oled_probe(const struct imu_bus *bus, uint8_t want, uint8_t *found, char *report, size_t size);
int oled_init(const struct imu_bus *bus, uint8_t addr);
int oled_off(const struct imu_bus *bus, uint8_t addr);
/* Send first..last dirty columns in each changed page (full pages when force).
 * Data payloads are min(chunk,32) bytes plus one control byte, so bus users can interleave.
 * Updates `shown`. Returns pages sent, or -1 on I/O error. `bytes` (optional)
 * receives the number of bytes put on the bus. */
int oled_flush(const struct imu_bus *bus, uint8_t addr, const struct oled_fb *fb, struct oled_fb *shown,
               int force, size_t chunk, size_t *bytes);
void oled_clear(struct oled_fb *fb);
void oled_set_pixel(struct oled_fb *fb, int x, int y);
void oled_line(struct oled_fb *fb, int x0, int y0, int x1, int y1);
void oled_label(struct oled_fb *fb, int x, int y, char c);
/* Draw text on a page (row 0..7) from character column 0..20; lowercase is
 * shown as uppercase, unsupported characters as '?'. Returns characters drawn. */
int oled_text(struct oled_fb *fb, unsigned row, unsigned col, const char *s);
int oled_pixel(const struct oled_fb *fb, unsigned x, unsigned y);
/* Glyph columns for a character (5 bytes), for tests. */
const uint8_t *oled_glyph(char c);
/* Write the framebuffer as a plain PBM (P1) image for host evidence. */
int oled_write_pbm(const struct oled_fb *fb, const char *path);
#endif
