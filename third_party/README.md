# Dependency installation and licence map

No Mac build products or reference submodule source are bundled.
The dashboard replay does not need these dependencies.

ns-3: use upstream release **ns-3.44** (tag `ns-3.44`) from
https://gitlab.com/nsnam/ns-3-dev.git. Install outside the source checkout or in
the ignored `cn/third_party/ns-3.44` directory. Build on the target Linux host:

```sh
git clone --branch ns-3.44 --depth 1 https://gitlab.com/nsnam/ns-3-dev.git cn/third_party/ns-3.44
cd cn/third_party/ns-3.44
./ns3 configure --build-profile=optimized --enable-examples --enable-tests
./ns3 build
```

The version is pinned by release tag; upstream commit/archive digest verification
is an owner release TODO. The imported RTP simulator build script must be checked
against this Linux build layout before reproduction is claimed. It has not run.
ns-3 uses GPL-2.0; simulation sources keep the component notice.

Firmware reference: `nucleo-f446re-freertos` at
`f588dba3c0b22b0305c7e33d9770dc4db755d395`, recorded by the selected OS gitlink.
Its upstream URL is recorded in `firmware-reference.txt`.
Install at `os/third_party/nucleo-f446re-freertos` (ignored) to match the firmware
Makefile. Review the reference GPL-2.0 root licence, FreeRTOS kernel MIT licence
and CMSIS/ST per-file terms before distributing a combined firmware image.
No firmware build has been performed here.

Wiring parts retain CC-BY-SA-3.0 and original attribution beside their sources.
Optional libcamera/ONNX/model weights are external inputs with their own terms.
