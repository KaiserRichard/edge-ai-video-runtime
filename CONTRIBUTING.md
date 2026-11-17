# Local development

Use Python 3.11+. From the repository root install `requirements-dev.txt` into a
virtual environment. Runtime replay needs no packages beyond the standard library.

Run `python -m pytest tests -q` independently from `dashboard/` and `cn/rtp/`.
For OS Python checks, from `os/` run:

```sh
python -m unittest discover -s analysis/tests -v
python -m unittest discover -s linux/inference/tests -v
python -m unittest discover -s linux/camera/tests -v
python -m unittest discover -s tools/la/tests -v
```

With GNU make and C/C++ compilers, `make -C os test` checks host C components.
Firmware needs the pinned reference and Arm tools; see third_party/README.md.
ns-3 integration tests require their separate build. Wiring tests additionally
require the packages declared beside their source. MATLAB requires its licensed
products and is not part of the Python suite.

Read docs/ENGINEERING.md. Keep evidence labels, validity flags, provenance and
existing third-party notices. Obtain contributor consent before a public release.
