# Optional IMU sensor + status display

Off by default. `make -C linux all` does not build it and no runner starts it.
Full guide (wiring, scheduling choice, evidence, UNKNOWNs):
[docs/IMU_EXTENSION.md](../../docs/IMU_EXTENSION.md).

```sh
make -C linux/imu test                        # host: fake I2C backend, synthetic data
bash scripts/pi/run_imu.sh --probe-only       # Pi: wiring check
sudo bash scripts/pi/run_imu.sh --duration 60 [--oled --pipeline-run latest]
```

| File | Role |
|---|---|
| `imu_bus.h`, `imu_bus_linux.c`, `imu_fake.c` | I2C register bus: Linux `I2C_RDWR` backend and a fake register file with device models |
| `imu_sensor.[ch]` | Probe, power-on/configuration, read and scaling for the two-die map and the InvenSense-style fallback |
| `imu_ring.[ch]` | Shared-memory sample ring (camera-ring conventions) |
| `imu_filter.[ch]` | Complementary roll/pitch filter |
| `imu_stats.[ch]` | Release lateness, period jitter and I2C read-time accounting |
| `hea_imu.c` | Periodic producer |
| `oled.[ch]`, `oled_status.[ch]`, `hea_oled.c` | Display driver, read-only status sources, display process |
