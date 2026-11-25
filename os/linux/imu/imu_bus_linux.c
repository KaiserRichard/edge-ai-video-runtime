#include "imu_bus.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef __linux__
#include <fcntl.h>
#include <linux/i2c.h>
#include <linux/i2c-dev.h>
#include <sys/ioctl.h>
#include <unistd.h>

struct linux_ctx { int fd; };

static int linux_read(void *ctx, uint8_t addr, uint8_t reg, uint8_t *buf, size_t n)
{
    struct linux_ctx *c = ctx;
    struct i2c_msg msgs[2];
    struct i2c_rdwr_ioctl_data x;
    if (n == 0 || n > 255u) { errno = EINVAL; return -1; }
    msgs[0].addr = addr; msgs[0].flags = 0; msgs[0].len = 1; msgs[0].buf = &reg;
    msgs[1].addr = addr; msgs[1].flags = I2C_M_RD; msgs[1].len = (uint16_t)n; msgs[1].buf = buf;
    x.msgs = msgs; x.nmsgs = 2;
    return ioctl(c->fd, I2C_RDWR, &x) == 2 ? 0 : -1;
}
static int linux_raw_write(void *ctx, uint8_t addr, const uint8_t *buf, size_t n)
{
    struct linux_ctx *c = ctx;
    struct i2c_msg msg;
    struct i2c_rdwr_ioctl_data x;
    uint8_t tmp[260];
    if (n == 0 || n > sizeof(tmp)) { errno = EINVAL; return -1; }
    memcpy(tmp, buf, n); /* the kernel ABI takes a non-const buffer */
    msg.addr = addr; msg.flags = 0; msg.len = (uint16_t)n; msg.buf = tmp;
    x.msgs = &msg; x.nmsgs = 1;
    return ioctl(c->fd, I2C_RDWR, &x) == 1 ? 0 : -1;
}
static int linux_write(void *ctx, uint8_t addr, uint8_t reg, const uint8_t *buf, size_t n)
{
    uint8_t tmp[257];
    if (n == 0 || n > 256u) { errno = EINVAL; return -1; }
    tmp[0] = reg; memcpy(tmp + 1, buf, n);
    return linux_raw_write(ctx, addr, tmp, n + 1u);
}
static void linux_delay(void *ctx, uint32_t us)
{
    (void)ctx;
    struct timespec t = { (time_t)(us / 1000000u), (long)(us % 1000000u) * 1000L };
    while (nanosleep(&t, &t) && errno == EINTR) {}
}
int imu_bus_linux_open(struct imu_bus *bus, const char *path, char *err, size_t err_size)
{
    unsigned long funcs = 0;
    int fd = open(path, O_RDWR | O_CLOEXEC);
    if (fd < 0) {
        int e = errno;
        snprintf(err, err_size, "cannot open %s: %s%s", path, strerror(e),
                 e == ENOENT ? " (I2C bus not enabled: the i2c_arm interface and the i2c-dev "
                               "module are needed; see os/docs/IMU_EXTENSION.md)" :
                 e == EACCES ? " (add the user to group i2c or run with the runner's privileges)" : "");
        errno = e; return -1;
    }
    if (ioctl(fd, I2C_FUNCS, &funcs) < 0 || !(funcs & I2C_FUNC_I2C)) {
        int e = errno ? errno : EOPNOTSUPP;
        snprintf(err, err_size, "%s does not support plain I2C combined transfers", path);
        close(fd); errno = e; return -1;
    }
    struct linux_ctx *c = malloc(sizeof(*c));
    if (!c) { close(fd); snprintf(err, err_size, "out of memory"); errno = ENOMEM; return -1; }
    c->fd = fd;
    bus->read = linux_read; bus->write = linux_write; bus->raw_write = linux_raw_write;
    bus->delay_us = linux_delay; bus->ctx = c;
    return 0;
}
void imu_bus_linux_close(struct imu_bus *bus)
{
    struct linux_ctx *c = bus->ctx;
    if (c) { close(c->fd); free(c); }
    bus->ctx = NULL;
}
#else
int imu_bus_linux_open(struct imu_bus *bus, const char *path, char *err, size_t err_size)
{
    (void)bus;
    snprintf(err, err_size, "cannot open %s: Linux i2c-dev is required (use --backend fake on this host)", path);
    errno = ENOSYS; return -1;
}
void imu_bus_linux_close(struct imu_bus *bus) { (void)bus; }
#endif
