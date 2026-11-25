#include "oled.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Classic 5x7 column font, ASCII 0x20..0x5A (space .. Z). */
static const uint8_t font[59][5] = {
    {0x00,0x00,0x00,0x00,0x00}, {0x00,0x00,0x5F,0x00,0x00}, {0x00,0x07,0x00,0x07,0x00}, {0x14,0x7F,0x14,0x7F,0x14},
    {0x24,0x2A,0x7F,0x2A,0x12}, {0x23,0x13,0x08,0x64,0x62}, {0x36,0x49,0x56,0x20,0x50}, {0x00,0x08,0x07,0x03,0x00},
    {0x00,0x1C,0x22,0x41,0x00}, {0x00,0x41,0x22,0x1C,0x00}, {0x2A,0x1C,0x7F,0x1C,0x2A}, {0x08,0x08,0x3E,0x08,0x08},
    {0x00,0x80,0x70,0x30,0x00}, {0x08,0x08,0x08,0x08,0x08}, {0x00,0x00,0x60,0x60,0x00}, {0x20,0x10,0x08,0x04,0x02},
    {0x3E,0x51,0x49,0x45,0x3E}, {0x00,0x42,0x7F,0x40,0x00}, {0x72,0x49,0x49,0x49,0x46}, {0x21,0x41,0x49,0x4D,0x33},
    {0x18,0x14,0x12,0x7F,0x10}, {0x27,0x45,0x45,0x45,0x39}, {0x3C,0x4A,0x49,0x49,0x31}, {0x41,0x21,0x11,0x09,0x07},
    {0x36,0x49,0x49,0x49,0x36}, {0x46,0x49,0x49,0x29,0x1E}, {0x00,0x00,0x14,0x00,0x00}, {0x00,0x40,0x34,0x00,0x00},
    {0x00,0x08,0x14,0x22,0x41}, {0x14,0x14,0x14,0x14,0x14}, {0x00,0x41,0x22,0x14,0x08}, {0x02,0x01,0x59,0x09,0x06},
    {0x3E,0x41,0x5D,0x59,0x4E}, {0x7C,0x12,0x11,0x12,0x7C}, {0x7F,0x49,0x49,0x49,0x36}, {0x3E,0x41,0x41,0x41,0x22},
    {0x7F,0x41,0x41,0x41,0x3E}, {0x7F,0x49,0x49,0x49,0x41}, {0x7F,0x09,0x09,0x09,0x01}, {0x3E,0x41,0x41,0x51,0x73},
    {0x7F,0x08,0x08,0x08,0x7F}, {0x00,0x41,0x7F,0x41,0x00}, {0x20,0x40,0x41,0x3F,0x01}, {0x7F,0x08,0x14,0x22,0x41},
    {0x7F,0x40,0x40,0x40,0x40}, {0x7F,0x02,0x1C,0x02,0x7F}, {0x7F,0x04,0x08,0x10,0x7F}, {0x3E,0x41,0x41,0x41,0x3E},
    {0x7F,0x09,0x09,0x09,0x06}, {0x3E,0x41,0x51,0x21,0x5E}, {0x7F,0x09,0x19,0x29,0x46}, {0x26,0x49,0x49,0x49,0x32},
    {0x03,0x01,0x7F,0x01,0x03}, {0x3F,0x40,0x40,0x40,0x3F}, {0x1F,0x20,0x40,0x20,0x1F}, {0x3F,0x40,0x38,0x40,0x3F},
    {0x63,0x14,0x08,0x14,0x63}, {0x03,0x04,0x78,0x04,0x03}, {0x61,0x59,0x49,0x4D,0x43},
};
const uint8_t *oled_glyph(char c)
{
    if (c >= 'a' && c <= 'z') c = (char)(c - 'a' + 'A');
    if (c < 0x20 || c > 0x5A) c = '?';
    return font[c - 0x20];
}
static int cmds(const struct imu_bus *bus, uint8_t addr, const uint8_t *c, size_t n)
{
    uint8_t buf[40];
    if (n + 1u > sizeof(buf)) { errno = EINVAL; return -1; }
    buf[0] = OLED_CTRL_CMD; memcpy(buf + 1, c, n);
    return bus->raw_write(bus->ctx, addr, buf, n + 1u);
}
int oled_probe(const struct imu_bus *bus, uint8_t want, uint8_t *found, char *report, size_t size)
{
    const uint8_t addrs[2] = { 0x3C, 0x3D }, nop = 0xE3;
    size_t used = 0;
    if (report && size) report[0] = '\0';
    for (int i = 0; i < 2; ++i) {
        uint8_t a = want ? want : addrs[i];
        int ok = !cmds(bus, a, &nop, 1);
        if (report && used < size) {
            int n = snprintf(report + used, size - used, "  display 0x%02X: %s\n", a, ok ? "ACK" : "no answer");
            if (n > 0) used += (size_t)n;
        }
        if (ok) { *found = a; return 0; }
        if (want) break;
    }
    if (report && used < size)
        snprintf(report + used, size - used, "no display answered: check 3.3 V, GND, SDA pin 3, SCL pin 5, address jumper\n");
    return -1;
}
int oled_init(const struct imu_bus *bus, uint8_t addr)
{
    static const uint8_t seq[] = {
        0xAE,             /* display off */
        0xD5, 0x80,       /* clock divide / oscillator */
        0xA8, 0x3F,       /* multiplex 64 */
        0xD3, 0x00,       /* display offset */
        0x40,             /* start line 0 */
        0x8D, 0x14,       /* charge pump on */
        0x20, 0x00,       /* horizontal addressing */
        0xA1, 0xC8,       /* segment remap, COM scan descending */
        0xDA, 0x12,       /* COM pins: alternative, 128x64 */
        0x81, 0x7F,       /* contrast */
        0xD9, 0xF1,       /* pre-charge */
        0xDB, 0x40,       /* VCOMH deselect */
        0xA4, 0xA6,       /* follow RAM, normal (not inverted) */
        0x2E,             /* scrolling off */
        0xAF,             /* display on */
    };
    return cmds(bus, addr, seq, sizeof(seq));
}
int oled_off(const struct imu_bus *bus, uint8_t addr) { const uint8_t c = 0xAE; return cmds(bus, addr, &c, 1); }
int oled_flush(const struct imu_bus *bus, uint8_t addr, const struct oled_fb *fb, struct oled_fb *shown,
               int force, size_t chunk, size_t *bytes)
{
    int pages = 0;
    size_t total = 0;
    if (!chunk || chunk > 32u) chunk = 32u;
    for (uint8_t p = 0; p < OLED_PAGES; ++p) {
        if (!force && !memcmp(fb->px[p], shown->px[p], OLED_W)) continue;
        size_t first = 0, last = OLED_W - 1u;
        if (!force) {
            while (first < OLED_W && fb->px[p][first] == shown->px[p][first]) ++first;
            while (last > first && fb->px[p][last] == shown->px[p][last]) --last;
        }
        const uint8_t win[] = { 0x21, (uint8_t)first, (uint8_t)last, 0x22, p, p };
        if (cmds(bus, addr, win, sizeof(win))) return -1;
        total += sizeof(win) + 1u;
        for (size_t off = first; off <= last; off += chunk) {
            size_t n = last + 1u - off < chunk ? last + 1u - off : chunk;
            uint8_t buf[33];
            buf[0] = OLED_CTRL_DATA; memcpy(buf + 1, fb->px[p] + off, n);
            if (bus->raw_write(bus->ctx, addr, buf, n + 1u)) return -1;
            total += n + 1u;
        }
        memcpy(shown->px[p], fb->px[p], OLED_W);
        ++pages;
    }
    if (bytes) *bytes = total;
    return pages;
}
void oled_clear(struct oled_fb *fb) { memset(fb, 0, sizeof(*fb)); }
void oled_set_pixel(struct oled_fb *fb, int x, int y)
{
    if (x >= 0 && x < 128 && y >= 0 && y < 64)
        fb->px[y/8][x] |= (uint8_t)(1u << (unsigned)(y%8));
}
void oled_line(struct oled_fb *fb, int x0, int y0, int x1, int y1)
{
    int dx = abs(x1-x0), sx = x0 < x1 ? 1 : -1;
    int dy = -abs(y1-y0), sy = y0 < y1 ? 1 : -1, err = dx+dy;
    for (;;) {
        oled_set_pixel(fb, x0, y0);
        if (x0 == x1 && y0 == y1) break;
        int e2 = 2*err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}
void oled_label(struct oled_fb *fb, int x, int y, char c)
{
    const uint8_t *g = oled_glyph(c);
    for (int i = 0; i < 5; ++i)
        for (int j = 0; j < 7; ++j)
            if ((g[i] >> (unsigned)j) & 1u) oled_set_pixel(fb, x+i, y+j);
}
int oled_text(struct oled_fb *fb, unsigned row, unsigned col, const char *s)
{
    int n = 0;
    if (row >= OLED_PAGES) return 0;
    for (; *s && col < OLED_COLS; ++s, ++col, ++n) {
        const uint8_t *g = oled_glyph(*s);
        unsigned x = col * 6u;
        for (unsigned i = 0; i < 5u; ++i) fb->px[row][x + i] = g[i];
        fb->px[row][x + 5u] = 0;
    }
    return n;
}
int oled_pixel(const struct oled_fb *fb, unsigned x, unsigned y)
{
    if (x >= OLED_W || y >= OLED_PAGES * 8u) return 0;
    return (fb->px[y / 8u][x] >> (y % 8u)) & 1;
}
int oled_write_pbm(const struct oled_fb *fb, const char *path)
{
    FILE *f = fopen(path, "w");
    if (!f) return -1;
    fprintf(f, "P1\n%u %u\n", OLED_W, OLED_PAGES * 8u);
    for (unsigned y = 0; y < OLED_PAGES * 8u; ++y) {
        for (unsigned x = 0; x < OLED_W; ++x) fputc(oled_pixel(fb, x, y) ? '1' : '0', f);
        fputc('\n', f);
    }
    return fclose(f);
}
