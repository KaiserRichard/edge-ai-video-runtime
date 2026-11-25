#include "imu_stats.h"
#include <inttypes.h>
#include <math.h>
#include <string.h>

void imu_hist_init(struct imu_hist *h) { memset(h, 0, sizeof(*h)); h->min_ns = UINT64_MAX; }
void imu_hist_add(struct imu_hist *h, uint64_t ns)
{
    uint64_t us = ns / 1000u;
    if (us < IMU_HIST_BINS) ++h->bins[us];
    else ++h->overflow;
    ++h->count; h->sum_ns += ns;
    if (ns < h->min_ns) h->min_ns = ns;
    if (ns > h->max_ns) h->max_ns = ns;
}
uint64_t imu_hist_percentile_us(const struct imu_hist *h, double p)
{
    if (!h->count || p <= 0.0 || p > 100.0) return 0;
    uint64_t rank = (uint64_t)ceil(p / 100.0 * (double)h->count), seen = 0;
    if (!rank) rank = 1;
    for (uint32_t i = 0; i < IMU_HIST_BINS; ++i) {
        seen += h->bins[i];
        if (seen >= rank) return i;
    }
    return UINT64_MAX;
}
void imu_timing_init(struct imu_timing *t, uint64_t period_ns)
{
    memset(t, 0, sizeof(*t));
    t->period_ns = period_ns;
    imu_hist_init(&t->lateness); imu_hist_init(&t->i2c); imu_hist_init(&t->abs_jitter);
    t->jitter_min_ns = INT64_MAX; t->jitter_max_ns = INT64_MIN;
}
uint64_t imu_timing_record(struct imu_timing *t, uint64_t release, uint64_t wake, uint64_t i2c_ns)
{
    uint64_t period = 0;
    ++t->releases;
    imu_hist_add(&t->lateness, wake > release ? wake - release : 0u);
    imu_hist_add(&t->i2c, i2c_ns);
    if (t->have_prev) {
        period = wake - t->prev_wake;
        int64_t j = (int64_t)period - (int64_t)(release - t->prev_release);
        if (j < t->jitter_min_ns) t->jitter_min_ns = j;
        if (j > t->jitter_max_ns) t->jitter_max_ns = j;
        t->jitter_sum_ns += (double)j; t->jitter_sumsq_ns2 += (double)j * (double)j;
        ++t->jitter_count;
        imu_hist_add(&t->abs_jitter, (uint64_t)(j < 0 ? -j : j));
    }
    t->prev_release = release; t->prev_wake = wake; t->have_prev = 1;
    return period;
}
void imu_timing_missed(struct imu_timing *t, uint64_t skipped) { t->missed += skipped; }
double imu_timing_jitter_rms_ns(const struct imu_timing *t)
{
    return t->jitter_count ? sqrt(t->jitter_sumsq_ns2 / (double)t->jitter_count) : 0.0;
}
static void hist_json(FILE *out, const char *name, const struct imu_hist *h)
{
    fprintf(out, "\"%s\":{\"count\":%" PRIu64 ",\"overflow\":%" PRIu64, name, h->count, h->overflow);
    if (!h->count) { fprintf(out, ",\"min_us\":null,\"mean_us\":null,\"p50_us\":null,\"p95_us\":null,"
                                  "\"p99_us\":null,\"max_us\":null}"); return; }
    fprintf(out, ",\"min_us\":%.3f,\"mean_us\":%.3f", (double)h->min_ns / 1e3,
            (double)h->sum_ns / (double)h->count / 1e3);
    const double ps[3] = { 50.0, 95.0, 99.0 };
    const char *names[3] = { "p50_us", "p95_us", "p99_us" };
    for (int i = 0; i < 3; ++i) {
        uint64_t v = imu_hist_percentile_us(h, ps[i]);
        if (v == UINT64_MAX) fprintf(out, ",\"%s\":\">=%u\"", names[i], IMU_HIST_BINS);
        else fprintf(out, ",\"%s\":%" PRIu64, names[i], v);
    }
    fprintf(out, ",\"max_us\":%.3f}", (double)h->max_ns / 1e3);
}
void imu_timing_json(FILE *out, const struct imu_timing *t)
{
    fprintf(out, "{\"period_ns\":%" PRIu64 ",\"releases\":%" PRIu64 ",\"missed_releases\":%" PRIu64
            ",\"read_errors\":%" PRIu64 ",", t->period_ns, t->releases, t->missed, t->read_errors);
    hist_json(out, "release_lateness", &t->lateness); fputc(',', out);
    hist_json(out, "i2c_read", &t->i2c); fputc(',', out);
    hist_json(out, "abs_period_jitter", &t->abs_jitter);
    if (t->jitter_count)
        fprintf(out, ",\"period_jitter\":{\"count\":%" PRIu64 ",\"min_us\":%.3f,\"max_us\":%.3f,"
                "\"mean_us\":%.3f,\"rms_us\":%.3f}", t->jitter_count, (double)t->jitter_min_ns / 1e3,
                (double)t->jitter_max_ns / 1e3, t->jitter_sum_ns / (double)t->jitter_count / 1e3,
                imu_timing_jitter_rms_ns(t) / 1e3);
    else fprintf(out, ",\"period_jitter\":null");
    fputc('}', out);
}
