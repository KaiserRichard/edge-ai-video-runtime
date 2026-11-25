#ifndef HEA_OLED_STATUS_H
#define HEA_OLED_STATUS_H
#include <stddef.h>
#include <stdint.h>

/* Live demo state gathered READ-ONLY from files the existing processes already
 * write (line-buffered CSVs in the pipeline run directory) and from the IMU
 * ring. Nothing here signals, opens for writing, or otherwise touches the
 * pipeline processes. */
#define DEMO_STATE_UNKNOWN (-1)
struct demo_status {
    int state;                 /* supervisor state 0 INIT 1 FRESH 2 HOLD 3 FAILSAFE, or -1 */
    int state_stale;           /* last MCU status older than max age */
    int have_fps; double cam_fps;
    int have_infer; double infer_ms;
    int have_imu; float roll_deg, pitch_deg; double imu_age_ms;
    unsigned long frame;       /* display refresh counter */
};
const char *demo_state_name(int state);

/* CSV helpers. Column index of `name` in a header line, or -1. */
int csv_column(const char *header, const char *name);
/* Copy field `col` of `line` into out; 0 ok, -1 missing/empty. */
int csv_field(const char *line, int col, char *out, size_t size);
int csv_field_u64(const char *line, int col, uint64_t *out);

/* Read the header line and up to `max_lines` last complete lines of a file
 * (reads at most the final `tail_bytes`). Lines are NUL-terminated pointers
 * into `buf`. Returns the number of data lines, or -1 if the file is missing. */
int csv_tail(const char *path, char *buf, size_t buf_size, size_t tail_bytes,
             char *header, size_t header_size, const char **lines, int max_lines);

/* Derivations (pure; unit-tested). now_raw_ns 0 or max_age_ns 0 disables staleness. */
int status_from_mcu(const char *header, const char *const *lines, int n, uint64_t now_raw_ns,
                    uint64_t max_age_ns, int *state, int *stale);
int fps_from_source(const char *header, const char *const *lines, int n, uint64_t now_raw_ns,
                    uint64_t max_age_ns, double *fps);
int infer_from_bridge(const char *header, const char *const *lines, int n, uint64_t now_raw_ns,
                      uint64_t max_age_ns, double *ms);
/* Gather from a run directory (mcu_status.csv, source.csv, bridge.csv). */
void demo_status_from_run(struct demo_status *s, const char *run_dir, uint64_t now_raw_ns, uint64_t max_age_ns);
/* Eight display lines of at most 21 characters. */
void demo_status_lines(const struct demo_status *s, unsigned rate_hz, char lines[8][22]);
#endif
