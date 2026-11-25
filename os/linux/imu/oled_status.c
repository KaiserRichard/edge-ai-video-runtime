#include "oled_status.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

const char *demo_state_name(int state)
{
    static const char *names[4] = { "INIT", "FRESH", "HOLD", "FAILSAFE" };
    return state >= 0 && state <= 3 ? names[state] : "UNKNOWN";
}
int csv_field(const char *line, int col, char *out, size_t size)
{
    if (col < 0 || !size) return -1;
    const char *p = line;
    for (int i = 0; i < col; ++i) {
        p = strchr(p, ',');
        if (!p) return -1;
        ++p;
    }
    size_t n = strcspn(p, ",\r\n");
    if (!n || n >= size) return -1;
    memcpy(out, p, n); out[n] = '\0';
    return 0;
}
int csv_column(const char *header, const char *name)
{
    size_t want = strlen(name);
    const char *p = header;
    for (int i = 0;; ++i) {
        size_t n = strcspn(p, ",\r\n");
        if (n == want && !strncmp(p, name, want)) return i;
        if (p[n] != ',') return -1;
        p += n + 1;
    }
}
int csv_field_u64(const char *line, int col, uint64_t *out)
{
    char f[32], *end = NULL;
    if (csv_field(line, col, f, sizeof(f)) || f[0] == '-') return -1;
    errno = 0;
    unsigned long long v = strtoull(f, &end, 10);
    if (errno || *end) return -1;
    *out = (uint64_t)v; return 0;
}
int csv_tail(const char *path, char *buf, size_t buf_size, size_t tail_bytes,
             char *header, size_t header_size, const char **lines, int max_lines)
{
    FILE *f = fopen(path, "r");
    if (!f) return -1;
    header[0] = '\0';
    if (!fgets(header, (int)header_size, f)) { fclose(f); return 0; }
    header[strcspn(header, "\r\n")] = '\0';
    long header_end = ftell(f);
    if (tail_bytes + 1u > buf_size) tail_bytes = buf_size - 1u;
    if (fseek(f, 0, SEEK_END)) { fclose(f); return 0; }
    long size = ftell(f), start = size - (long)tail_bytes;
    if (start < header_end) start = header_end;
    if (start >= size || fseek(f, start, SEEK_SET)) { fclose(f); return 0; }
    size_t got = fread(buf, 1, (size_t)(size - start), f);
    fclose(f);
    buf[got] = '\0';
    /* Drop a partial first line (unless we started right after the header)
     * and a partial last line (writer mid-line). */
    char *p = buf;
    if (start > header_end) { char *nl = strchr(p, '\n'); if (!nl) return 0; p = nl + 1; }
    char *last_nl = strrchr(p, '\n');
    if (!last_nl) return 0;
    last_nl[1] = '\0';
    /* Collect, keeping only the final max_lines. */
    int n = 0;
    while (*p) {
        char *nl = strchr(p, '\n');
        *nl = '\0';
        if (*p) {
            if (n == max_lines) { memmove(lines, lines + 1, (size_t)(max_lines - 1) * sizeof(*lines)); --n; }
            lines[n++] = p;
        }
        p = nl + 1;
    }
    return n;
}
static int fresh(uint64_t t, uint64_t now, uint64_t max_age)
{
    return !now || !max_age || (t <= now ? now - t <= max_age : 1);
}
int status_from_mcu(const char *header, const char *const *lines, int n, uint64_t now, uint64_t max_age,
                    int *state, int *stale)
{
    int cs = csv_column(header, "state"), ct = csv_column(header, "t_rx_pi_ns");
    *state = DEMO_STATE_UNKNOWN; *stale = 0;
    if (cs < 0 || n <= 0) return -1;
    uint64_t v, t;
    if (csv_field_u64(lines[n - 1], cs, &v) || v > 3u) return -1;
    *state = (int)v;
    if (ct >= 0 && !csv_field_u64(lines[n - 1], ct, &t)) *stale = !fresh(t, now, max_age);
    return 0;
}
int fps_from_source(const char *header, const char *const *lines, int n, uint64_t now, uint64_t max_age, double *fps)
{
    int c = csv_column(header, "t_input_ns");
    uint64_t first, last;
    if (c < 0 || n < 2 || csv_field_u64(lines[0], c, &first) || csv_field_u64(lines[n - 1], c, &last) ||
        last <= first || !fresh(last, now, max_age)) return -1;
    *fps = (double)(n - 1) * 1e9 / (double)(last - first);
    return 0;
}
int infer_from_bridge(const char *header, const char *const *lines, int n, uint64_t now, uint64_t max_age, double *ms)
{
    int ci = csv_column(header, "t_input_ns"), cd = csv_column(header, "t_done_ns");
    double sum = 0; int used = 0;
    uint64_t newest = 0;
    if (ci < 0 || cd < 0) return -1;
    for (int i = 0; i < n; ++i) {
        uint64_t a, b;
        if (csv_field_u64(lines[i], ci, &a) || csv_field_u64(lines[i], cd, &b) || b < a) continue;
        sum += (double)(b - a); ++used;
        if (b > newest) newest = b;
    }
    if (!used || !fresh(newest, now, max_age)) return -1;
    *ms = sum / (double)used / 1e6;
    return 0;
}
void demo_status_from_run(struct demo_status *s, const char *dir, uint64_t now, uint64_t max_age)
{
    static char buf[16384], header[1024];
    const char *lines[32];
    char path[1024];
    int n;
    s->state = DEMO_STATE_UNKNOWN; s->state_stale = 0; s->have_fps = s->have_infer = 0;
    if (!dir) return;
    snprintf(path, sizeof(path), "%s/mcu_status.csv", dir);
    if ((n = csv_tail(path, buf, sizeof(buf), 4096, header, sizeof(header), lines, 4)) > 0)
        status_from_mcu(header, lines, n, now, max_age, &s->state, &s->state_stale);
    snprintf(path, sizeof(path), "%s/source.csv", dir);
    if ((n = csv_tail(path, buf, sizeof(buf), 8192, header, sizeof(header), lines, 31)) > 0)
        s->have_fps = !fps_from_source(header, lines, n, now, max_age, &s->cam_fps);
    snprintf(path, sizeof(path), "%s/bridge.csv", dir);
    if ((n = csv_tail(path, buf, sizeof(buf), 8192, header, sizeof(header), lines, 30)) > 0)
        s->have_infer = !infer_from_bridge(header, lines, n, now, max_age, &s->infer_ms);
}
void demo_status_lines(const struct demo_status *s, unsigned rate_hz, char l[8][22])
{
    snprintf(l[0], 22, "EDGE AI DEMO");
    if (s->state == DEMO_STATE_UNKNOWN) snprintf(l[1], 22, "STATE: NO DATA");
    else snprintf(l[1], 22, "STATE: %s%s", demo_state_name(s->state), s->state_stale ? " OLD" : "");
    if (s->have_fps) snprintf(l[2], 22, "CAM FPS: %.1f", s->cam_fps);
    else snprintf(l[2], 22, "CAM FPS: --");
    if (s->have_infer) snprintf(l[3], 22, "INFER MS: %.1f", s->infer_ms);
    else snprintf(l[3], 22, "INFER MS: --");
    if (s->have_imu) {
        snprintf(l[4], 22, "ROLL: %+.1f", (double)s->roll_deg);
        snprintf(l[5], 22, "PITCH: %+.1f", (double)s->pitch_deg);
        snprintf(l[6], 22, "IMU AGE MS: %.0f", s->imu_age_ms);
    } else {
        snprintf(l[4], 22, "ROLL: --");
        snprintf(l[5], 22, "PITCH: --");
        snprintf(l[6], 22, "IMU: NONE");
    }
    snprintf(l[7], 22, "%uHZ #%lu", rate_hz, s->frame);
}
