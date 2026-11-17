#!/usr/bin/env bash
# Build against existing ns-3.44 libraries; never write inside third_party/.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
ns=$(cd third_party/ns-3.44 && pwd -P)
out=${1:-build/rtp-video}
mkdir -p "$(dirname "$out")"
libs=()
while IFS= read -r library; do
  name=${library##*/lib}
  libs+=("-l${name%.*}")
done < <(find "$ns/build/lib" -maxdepth 1 \
  \( -name 'libns3.44-*-optimized.dylib' -o -name 'libns3.44-*-optimized.so' \))
if ((${#libs[@]} == 0)); then
  echo "No prebuilt ns-3.44 libraries in $ns/build/lib" >&2
  exit 1
fi
${CXX:-clang++} -std=c++20 -O2 -Wall -Wextra -Werror \
  -isystem "$ns/build/include" -I sim/rtp \
  sim/rtp/rtp-video.cc sim/rtp/rtp-apps.cc -L "$ns/build/lib" "${libs[@]}" \
  -Wl,-rpath,"$ns/build/lib" -o "$out"
echo "built $out"
