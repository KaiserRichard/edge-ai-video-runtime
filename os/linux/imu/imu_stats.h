#ifndef HEA_IMU_STATS_H
#define HEA_IMU_STATS_H
#include <stdint.h>
#include <stdio.h>

/* 1 us bins, 0..IMU_HIST_BINS-1 us; larger values go to `overflow` and are
 * still reflected in max. Percentiles are nearest-rank, like
 * analysis/pipeline_summary.py; a percentile in the overflow reports UINT64_MAX. */
#define IMU_HIST_BINS 20000u
struct imu_hist {
    uint32_t bins[IMU_HIST_BINS];
    uint64_t count, overflow, sum_ns, min_ns, max_ns;
};
void imu_hist_init(struct imu_hist *h);
void imu_hist_add(struct imu_hist *h, uint64_t ns);
/* Value in us at nearest-rank percentile p (0 < p <= 100); UINT64_MAX in overflow. */
uint64_t imu_hist_percentile_us(const struct imu_hist *h, double p);

/* Release-timing accounting for a periodic task.
 *  lateness = wake - release      (release = absolute deadline)
 *  jitter   = (wake - prev_wake) - (release - prev_release)
 * i.e. the deviation of the observed activation period from the planned one,
 * which stays correct across skipped releases. */
struct imu_timing {
    uint64_t period_ns, releases, missed, read_errors;
    struct imu_hist lateness, i2c, abs_jitter;
    int64_t jitter_min_ns, jitter_max_ns;
    double jitter_sum_ns, jitter_sumsq_ns2;
    uint64_t jitter_count;
    uint64_t prev_release, prev_wake;
    int have_prev;
};
void imu_timing_init(struct imu_timing *t, uint64_t period_ns);
/* Account one executed release. Returns the observed period (0 for the first). */
uint64_t imu_timing_record(struct imu_timing *t, uint64_t release_ns, uint64_t wake_ns, uint64_t i2c_ns);
void imu_timing_missed(struct imu_timing *t, uint64_t skipped);
double imu_timing_jitter_rms_ns(const struct imu_timing *t);
/* JSON object (no trailing newline) with counts and P50/P95/P99/max in us. */
void imu_timing_json(FILE *out, const struct imu_timing *t);
#endif
