#!/usr/bin/env bash
# Optional IMU sensor producer (+ optional status display). OFF BY DEFAULT:
# run_pipeline.sh, camera_pipeline.sh and the experiment campaigns never call
# this script. Start it by hand, in a second terminal, only for the demo.
set -euo pipefail
repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
duration=60; rate_hz=200; cpu=3; priority=40; mlock=1; bus=/dev/i2c-1; map=auto
oled=0; oled_rate=""; oled_mode=status; kp=2; ki=0.05; bias_seconds=2; oled_cpu=3; oled_nice=19; pipeline_run=""; run=""; probe_only=0
usage() {
  cat <<'EOF'
Usage: scripts/pi/run_imu.sh [--duration S] [--rate-hz 200] [--cpu 3] [--priority 40] [--no-mlock]
  [--bus /dev/i2c-1] [--map auto|imu|invensense] [--probe-only]
  [--oled] [--oled-mode status|attitude] [--oled-rate FPS] [--mahony-kp 2] [--mahony-ki 0.05] [--bias-seconds 2] [--oled-cpu 3] [--oled-nice 19] [--pipeline-run DIR|latest] [--run-dir DIR]
Defaults keep the pipeline pinning untouched: IMU on CPU3 SCHED_FIFO 40 (below source 60 / bridge 70),
display on CPU3 SCHED_OTHER nice 19. See docs/IMU_EXTENSION.md.
EOF
}
original_args=("$@")
while (($#)); do
  case "$1" in
    --no-mlock) mlock=0; shift; continue ;;
    --oled) oled=1; shift; continue ;;
    --probe-only) probe_only=1; shift; continue ;;
    -h|--help) usage; exit 0 ;;
    --duration|--rate-hz|--cpu|--priority|--bus|--map|--oled-mode|--mahony-kp|--mahony-ki|--bias-seconds|--oled-rate|--oled-cpu|--oled-nice|--pipeline-run|--run-dir)
      (($# >= 2)) || { echo "missing value for $1" >&2; exit 2; }
      case "$1" in
        --duration) duration="$2" ;; --rate-hz) rate_hz="$2" ;; --cpu) cpu="$2" ;; --priority) priority="$2" ;;
        --oled-mode) oled_mode="$2"; oled=1 ;; --mahony-kp) kp="$2" ;; --mahony-ki) ki="$2" ;; --bias-seconds) bias_seconds="$2" ;;
        --bus) bus="$2" ;; --map) map="$2" ;; --oled-rate) oled_rate="$2" ;; --oled-cpu) oled_cpu="$2" ;;
        --oled-nice) oled_nice="$2" ;; --pipeline-run) pipeline_run="$2" ;; --run-dir) run="$2" ;;
      esac
      shift 2 ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ "$oled_mode" == status || "$oled_mode" == attitude ]] || { echo "invalid OLED mode" >&2; exit 2; }
[[ -n "$oled_rate" ]] || { if [[ "$oled_mode" == attitude ]]; then oled_rate=20; else oled_rate=2; fi; }
for n in "$duration" "$rate_hz" "$cpu" "$priority" "$oled_rate" "$oled_cpu" "$oled_nice"; do
  [[ "$n" =~ ^[0-9]+$ ]] || { echo "numeric option expected, got: $n" >&2; exit 2; }
done
((duration >= 1 && duration <= 86400)) || { echo "--duration must be 1..86400" >&2; exit 2; }
((priority <= 59)) || { echo "--priority must stay below the source (60) and bridge (70)" >&2; exit 2; }
[[ "$(uname -s)" == Linux ]] || { echo "run_imu.sh requires the Linux Pi target; use make -C linux/imu test on a host" >&2; exit 2; }
make -C "$repo/linux/imu" all
imu="$repo/linux/imu/build/hea_imu"; disp="$repo/linux/imu/build/hea_oled"
if ((probe_only)); then exec "$imu" --bus "$bus" --map "$map" --probe-only; fi
if [[ "$pipeline_run" == latest ]]; then
  pipeline_run="$(ls -td "$repo"/results/*/pipeline-* 2>/dev/null | head -n 1 || true)"
  [[ -n "$pipeline_run" ]] || echo "no pipeline run directory found; display shows NO DATA for the pipeline" >&2
fi
[[ -n "$run" ]] || run="$repo/results/$(date -u +%Y-%m-%d)/imu-$(date -u +%H%M%S)-$$"
mkdir -p "$(dirname "$run")"
mkdir "$run" # Refuse to overwrite an existing run (earlier results are evidence).
run="$(cd "$run" && pwd)"
printf '%q ' "$0" "${original_args[@]}" > "$run/command.txt"; printf '\n' >> "$run/command.txt"
python3 - "$run" "$duration" "$rate_hz" "$cpu" "$priority" "$mlock" "$bus" "$map" "$oled" "$oled_rate" "$oled_cpu" "$oled_nice" "$pipeline_run" "$oled_mode" "$kp" "$ki" "$bias_seconds" <<'PY'
import json, sys
from pathlib import Path
run, duration, rate, cpu, prio, mlock, bus, imap, oled, orate, ocpu, onice, prun, mode, kp, ki, bias_seconds = sys.argv[1:]
cfg = dict(evidence="IMU extension run (optional, not part of the measured pipeline)", duration_seconds=int(duration),
           rate_hz=int(rate), imu_cpu=int(cpu), imu_fifo_priority=int(prio), mlock=bool(int(mlock)), bus=bus, map=imap,
           oled=bool(int(oled)), oled_rate_hz=int(orate), oled_cpu=int(ocpu), oled_nice=int(onice),
           pipeline_run=prun or None, oled_mode=mode, mahony_kp=float(kp), mahony_ki=float(ki), bias_seconds=float(bias_seconds))
(Path(run) / "config.json").write_text(json.dumps(cfg, indent=2) + "\n")
PY
snapshot() { # IRQ placement of the I2C controller and RT throttling settings, as evidence
  local tag="$1"
  cat /proc/interrupts > "$run/interrupts_$tag.txt" 2>/dev/null || true
  { echo "sched_rt_runtime_us=$(cat /proc/sys/kernel/sched_rt_runtime_us 2>/dev/null || echo UNKNOWN)"
    echo "sched_rt_period_us=$(cat /proc/sys/kernel/sched_rt_period_us 2>/dev/null || echo UNKNOWN)"
    grep -h '^[[:space:]]*dtparam' /boot/firmware/config.txt 2>/dev/null | sed 's/^/config.txt: /' || echo "config.txt: UNKNOWN"
    for d in /sys/class/i2c-adapter/i2c-*; do [[ -e "$d/name" ]] && echo "$(basename "$d")=$(cat "$d/name")"; done
    vcgencmd get_throttled 2>/dev/null || echo "throttled=UNKNOWN"
  } > "$run/system_$tag.txt" 2>/dev/null || true
  (cd "$repo" && bash scripts/pi/collect_metadata.sh) > "$run/meta_$tag.json" 2> "$run/meta_$tag.stderr.log" || true
}
imu_pid=""; oled_pid=""
cleanup() {
  local rc=$?
  trap - EXIT INT TERM
  set +e
  for pid in "$oled_pid" "$imu_pid"; do
    [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null && kill -TERM "$pid" 2>/dev/null
    [[ -n "$pid" ]] && wait "$pid"
  done
  snapshot after
  printf '%s\n' "$rc" > "$run/exit_code"
  if ((rc == 0)); then touch "$run/DONE"; else touch "$run/FAILED"; fi
  echo "Run directory: $run"
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
snapshot before
imu_cmd=("$imu" --bus "$bus" --map "$map" --rate-hz "$rate_hz" --duration "$duration" --shm hea_imu
         --mahony-kp "$kp" --mahony-ki "$ki" --bias-seconds "$bias_seconds"
         --csv "$run/imu.csv" --summary "$run/imu_summary.json" --cpu "$cpu" --fifo-priority "$priority")
((mlock)) && imu_cmd+=(--mlock)
printf '%q ' "${imu_cmd[@]}" >> "$run/process_commands.txt"; printf '\n' >> "$run/process_commands.txt"
"${imu_cmd[@]}" > "$run/imu.stdout.log" 2> "$run/imu.stderr.log" & imu_pid=$!
printf '%s\n' "$imu_pid" > "$run/imu.pid"
if ((oled)); then
  oled_cmd=("$disp" --bus "$bus" --mode "$oled_mode" --fps "$oled_rate" --duration "$duration" --imu-shm hea_imu
            --csv "$run/oled.csv" --frame-out "$run/oled_last.pbm" --cpu "$oled_cpu" --nice "$oled_nice")
  [[ -n "$pipeline_run" ]] && oled_cmd+=(--run-dir "$pipeline_run")
  printf '%q ' "${oled_cmd[@]}" >> "$run/process_commands.txt"; printf '\n' >> "$run/process_commands.txt"
  "${oled_cmd[@]}" > "$run/oled.stdout.log" 2> "$run/oled.stderr.log" & oled_pid=$!
fi
rc=0
wait "$imu_pid" || rc=$?
imu_pid=""
if [[ -n "$oled_pid" ]]; then wait "$oled_pid" || rc=$((rc ? rc : $?)); oled_pid=""; fi
exit "$rc"
