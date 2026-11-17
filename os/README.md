# Original OS pipeline

Imported from heterogeneous-edge-ai-os, camera/results branch at
730b9a173e854e8e9f5551c4fb6970d88404b944. See the root NOTICE and CREDITS.
The report under docs/os-report was imported from a separate newer docs commit.

`linux/camera` captures frames on the Pi; `linux/inference` runs the workload.
`linux` provides the IPC/UART bridge; `protocol` defines framing and age fields;
`stm32` provides host-testable supervision and board firmware.
`results` retains measurements, failed runs and validity/exclusion records.

Run host C checks with `make test PYTHON=python3` after installing a C/C++
toolchain, GNU make and the Python development dependencies. See the component
READMEs for camera, protocol and firmware details. On the Pi, install libcamera
development support and separately supply the ONNX runtime/model if required.
Use a PTY for a labelled software demonstration; a PTY is not a physical UART.

Hardware setup and physical experiments are not run during this staging task.
The board build needs the external pinned reference in ../third_party/README.md.
Model weights, firmware dependencies and toolchains are not bundled.
