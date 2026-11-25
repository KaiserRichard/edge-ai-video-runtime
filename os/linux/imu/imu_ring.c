#include "imu_ring.h"
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef HEA_IMU_TEST_HOOK
void hea_imu_copy_hook(void);
#endif

/* C99 compile-time ABI checks (negative array size on failure). */
typedef char imu_ring_header_abi[sizeof(struct imu_ring_header) == 64 ? 1 : -1];
typedef char imu_ring_slot_abi[8 + 4 * IMU_RING_WORDS == IMU_RING_STRIDE ? 1 : -1];

static int object_name(const char *name, char *out, size_t size)
{
    if (name[0] == '/') ++name;
    size_t n = strlen(name);
    if (!n || n > 100 || strspn(name, "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-") != n)
        return -1;
#ifdef __APPLE__
    snprintf(out, size, "/tmp/hea-imu-%s", name); /* macOS host-only surrogate, as the camera ring */
#else
    snprintf(out, size, "/%s", name);
#endif
    return 0;
}
static int open_object(const char *name, int flags)
{
#ifdef __APPLE__
    return open(name, flags | O_NOFOLLOW, 0600);
#else
    return shm_open(name, flags, 0600);
#endif
}
static void remove_object(const char *name)
{
#ifdef __APPLE__
    unlink(name);
#else
    shm_unlink(name);
#endif
}
static uint8_t *slot_at(const struct imu_ring *r, uint32_t index)
{
    return (uint8_t *)r->h + sizeof(struct imu_ring_header) + (size_t)(index % r->h->slots) * IMU_RING_STRIDE;
}
static size_t layout(uint32_t slots) { return sizeof(struct imu_ring_header) + (size_t)slots * IMU_RING_STRIDE; }

int imu_ring_create(struct imu_ring *r, const char *name, uint32_t slots, uint32_t rate_hz, uint32_t map,
                    char *err, size_t err_size)
{
    memset(r, 0, sizeof(*r)); r->fd = -1;
    const uint16_t endian = 1;
    if (*(const uint8_t *)&endian != 1) { snprintf(err, err_size, "ring ABI requires little endian"); return -1; }
    if (object_name(name, r->name, sizeof(r->name))) {
        snprintf(err, err_size, "shm NAME must contain only letters, digits, underscore or hyphen"); return -1;
    }
    if (!slots || slots > IMU_RING_MAX_SLOTS) { snprintf(err, err_size, "ring slots must be 1..%u", IMU_RING_MAX_SLOTS); return -1; }
    r->fd = open_object(r->name, O_RDWR | O_CREAT | O_EXCL);
    if (r->fd < 0) {
        int e = errno;
        snprintf(err, err_size, "create ring %s: %s%s", r->name, strerror(e),
                 e == EEXIST ? " (another hea_imu is running, or a stale object remains: remove /dev/shm/NAME)" : "");
        return -1;
    }
    r->owner = 1; r->size = layout(slots);
    if (ftruncate(r->fd, (off_t)r->size)) { snprintf(err, err_size, "size ring: %s", strerror(errno)); goto fail; }
    void *p = mmap(NULL, r->size, PROT_READ | PROT_WRITE, MAP_SHARED, r->fd, 0);
    if (p == MAP_FAILED) { snprintf(err, err_size, "map ring: %s", strerror(errno)); goto fail; }
    r->h = p;
    memset(p, 0, r->size);
    r->h->magic = IMU_RING_MAGIC; r->h->version = IMU_RING_VERSION; r->h->slots = slots;
    r->h->stride = IMU_RING_STRIDE; r->h->rate_hz = rate_hz; r->h->map = map;
    __atomic_store_n(&r->h->ready, 1u, __ATOMIC_RELEASE);
    return 0;
fail:
    close(r->fd); remove_object(r->name); r->fd = -1;
    return -1;
}
int imu_ring_open(struct imu_ring *r, const char *name, char *err, size_t err_size)
{
    struct stat st;
    memset(r, 0, sizeof(*r)); r->fd = -1;
    if (object_name(name, r->name, sizeof(r->name))) {
        snprintf(err, err_size, "shm NAME must contain only letters, digits, underscore or hyphen"); return -1;
    }
    r->fd = open_object(r->name, O_RDONLY);
    if (r->fd < 0) { snprintf(err, err_size, "open ring %s: %s", r->name, strerror(errno)); return -1; }
    if (fstat(r->fd, &st) || st.st_size < (off_t)sizeof(struct imu_ring_header) ||
        st.st_size > (off_t)layout(IMU_RING_MAX_SLOTS)) { snprintf(err, err_size, "invalid ring size"); goto fail; }
    r->size = (size_t)st.st_size;
    void *p = mmap(NULL, r->size, PROT_READ, MAP_SHARED, r->fd, 0);
    if (p == MAP_FAILED) { snprintf(err, err_size, "map ring: %s", strerror(errno)); goto fail; }
    r->h = p;
    if (__atomic_load_n(&r->h->ready, __ATOMIC_ACQUIRE) != 1u || r->h->magic != IMU_RING_MAGIC ||
        r->h->version != IMU_RING_VERSION || r->h->stride != IMU_RING_STRIDE || !r->h->slots ||
        r->h->slots > IMU_RING_MAX_SLOTS || layout(r->h->slots) != r->size) {
        snprintf(err, err_size, "ring not ready or unsupported ABI");
        munmap(p, r->size); r->h = NULL; goto fail;
    }
    return 0;
fail:
    close(r->fd); r->fd = -1;
    return -1;
}
void imu_ring_close(struct imu_ring *r)
{
    if (r->h) munmap(r->h, r->size);
    if (r->fd >= 0) close(r->fd);
    if (r->owner) remove_object(r->name);
    r->h = NULL; r->fd = -1; r->owner = 0;
}
static uint32_t fbits(float f) { uint32_t u; memcpy(&u, &f, 4); return u; }
static float bitsf(uint32_t u) { float f; memcpy(&f, &u, 4); return f; }
static void pack(const struct imu_record *x, uint32_t w[IMU_RING_WORDS])
{
    memset(w, 0, IMU_RING_WORDS * sizeof(*w));
    for (int i = 0; i < 4; ++i) w[14+i] = fbits(x->q[i]);
    for (int i = 0; i < 3; ++i) w[18+i] = fbits(x->attitude_deg[i]);
    w[0] = x->index; w[1] = x->flags; w[2] = (uint32_t)x->t_ns; w[3] = (uint32_t)(x->t_ns >> 32);
    for (int i = 0; i < 3; ++i) { w[4 + i] = fbits(x->acc_g[i]); w[7 + i] = fbits(x->gyr_dps[i]); }
    w[10] = fbits(x->roll_deg); w[11] = fbits(x->pitch_deg); w[12] = x->i2c_ns; w[13] = x->period_ns;
}
static void unpack(const uint32_t w[IMU_RING_WORDS], struct imu_record *x)
{
    for (int i = 0; i < 4; ++i) x->q[i] = bitsf(w[14+i]);
    for (int i = 0; i < 3; ++i) x->attitude_deg[i] = bitsf(w[18+i]);
    x->index = w[0]; x->flags = w[1]; x->t_ns = (uint64_t)w[2] | ((uint64_t)w[3] << 32);
    for (int i = 0; i < 3; ++i) { x->acc_g[i] = bitsf(w[4 + i]); x->gyr_dps[i] = bitsf(w[7 + i]); }
    x->roll_deg = bitsf(w[10]); x->pitch_deg = bitsf(w[11]); x->i2c_ns = w[12]; x->period_ns = w[13];
}
void imu_ring_write(struct imu_ring *r, const struct imu_record *rec)
{
    uint8_t *s = slot_at(r, rec->index);
    uint64_t *seq = (uint64_t *)(void *)s;
    uint32_t *words = (uint32_t *)(void *)(s + 8), w[IMU_RING_WORDS];
    pack(rec, w);
    uint64_t v = __atomic_load_n(seq, __ATOMIC_RELAXED);
    __atomic_store_n(seq, v + 1, __ATOMIC_SEQ_CST);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    for (unsigned i = 0; i < IMU_RING_WORDS; ++i) __atomic_store_n(&words[i], w[i], __ATOMIC_RELAXED);
    __atomic_store_n(seq, v + 2, __ATOMIC_RELEASE);
    __atomic_store_n(&r->h->head, (uint64_t)rec->index + 1u, __ATOMIC_RELEASE);
}
int imu_ring_read(const struct imu_ring *r, uint32_t index, struct imu_record *out)
{
    const uint8_t *s = slot_at(r, index);
    const uint64_t *seq = (const uint64_t *)(const void *)s;
    const uint32_t *words = (const uint32_t *)(const void *)(s + 8);
    uint32_t w[IMU_RING_WORDS];
    uint64_t before = __atomic_load_n(seq, __ATOMIC_ACQUIRE);
    if (before & 1u) return 2;
    if (!before) return 1;
    for (unsigned i = 0; i < IMU_RING_WORDS; ++i) w[i] = __atomic_load_n(&words[i], __ATOMIC_RELAXED);
#ifdef HEA_IMU_TEST_HOOK
    hea_imu_copy_hook();
#endif
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    if (__atomic_load_n(seq, __ATOMIC_ACQUIRE) != before) return 2;
    if (w[0] != index) return 1;
    unpack(w, out);
    return 0;
}
uint64_t imu_ring_head(const struct imu_ring *r) { return __atomic_load_n(&r->h->head, __ATOMIC_ACQUIRE); }
int imu_ring_latest(const struct imu_ring *r, struct imu_record *out, int tries)
{
    int rc = 1;
    for (int i = 0; i < tries; ++i) {
        uint64_t head = imu_ring_head(r);
        if (!head) return 1;
        rc = imu_ring_read(r, (uint32_t)(head - 1u), out);
        if (rc == 0) return 0;
    }
    return rc;
}
