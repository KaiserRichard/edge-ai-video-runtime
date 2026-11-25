# Optional IMU sensor + status display extension. Not built by `make -C linux all`
# and not started by any runner: off by default.
CC ?= cc
PYTHON ?= python3
CFLAGS ?= -std=c99 -O2 -g -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror
SAN ?= -fsanitize=address,undefined
CPPFLAGS += -D_GNU_SOURCE -D_DEFAULT_SOURCE -D_DARWIN_C_SOURCE -D_POSIX_C_SOURCE=200809L -I. -I../include
BUILD := build
LIB_SRC := imu_bus_linux.c imu_fake.c imu_sensor.c imu_ring.c imu_filter.c imu_stats.c
OLED_SRC := oled.c oled_status.c oled_attitude.c
HEADERS := $(wildcard *.h) ../include/hea_runtime.h
RUNTIME := ../src/hea_runtime.c
LDLIBS += -lm
ifneq ($(shell uname -s),Darwin)
LDLIBS += -lrt
endif

.PHONY: all test clean
all: $(BUILD)/hea_imu $(BUILD)/hea_oled $(BUILD)/attitude_preview
$(BUILD):
	mkdir -p $@
$(BUILD)/hea_imu: hea_imu.c $(LIB_SRC) $(RUNTIME) $(HEADERS) | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) hea_imu.c $(LIB_SRC) $(RUNTIME) $(LDFLAGS) $(LDLIBS) -o $@
$(BUILD)/hea_oled: hea_oled.c $(LIB_SRC) $(OLED_SRC) $(RUNTIME) $(HEADERS) | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) hea_oled.c $(LIB_SRC) $(OLED_SRC) $(RUNTIME) $(LDFLAGS) $(LDLIBS) -o $@
$(BUILD)/attitude_preview: attitude_preview.c oled.c oled_attitude.c imu_filter.c $(HEADERS) | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) attitude_preview.c oled.c oled_attitude.c imu_filter.c $(LDFLAGS) $(LDLIBS) -o $@
$(BUILD)/test_imu: tests/test_imu.c $(LIB_SRC) $(OLED_SRC) $(HEADERS) | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SAN) -DHEA_IMU_TEST_HOOK tests/test_imu.c $(LIB_SRC) $(OLED_SRC) $(LDFLAGS) $(LDLIBS) -o $@
$(BUILD)/test_attitude: tests/test_attitude.c imu_filter.c oled.c oled_attitude.c $(HEADERS) | $(BUILD)
	$(CC) $(CPPFLAGS) $(CFLAGS) $(SAN) tests/test_attitude.c imu_filter.c oled.c oled_attitude.c $(LDFLAGS) $(LDLIBS) -o $@
test: all $(BUILD)/test_imu $(BUILD)/test_attitude
	./$(BUILD)/test_imu
	./$(BUILD)/test_attitude
	PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s tests -v
clean:
	rm -rf $(BUILD)
