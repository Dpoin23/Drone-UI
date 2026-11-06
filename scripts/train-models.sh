#!/usr/bin/env bash
# Run the full training path on a local NVIDIA GPU (Linux or WSL2): set up the venv, fetch and
# prepare the datasets, smoke-test, train both detectors, benchmark them, bundle the weights, and
# publish them as a GitHub Release so the team can pull them with scripts/fetch-models.sh.
# Safe to rerun: finished steps are skipped and an interrupted run resumes from its last checkpoint.
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: scripts/train-models.sh [options]

  --only intruder|maintenance   Train one detector (default: both)
  --epochs N                    Epochs per full run (default: 100)
  --imgsz N                     Training image size (default: 640)
  --batch N                     Batch size (default: 16)
  --workers N                   Data-loader workers (default: 8)
  --device D                    CUDA device index (default: 0)
  --skip-smoke                  Skip the 1-epoch smoke tests
  --smoke-only                  Stop after the smoke tests
  --retrain                     Train again even if weights are installed (old run is archived)
  --allow-cpu                   Continue without a CUDA GPU (only sensible with --smoke-only)
  --no-publish                  Don't upload the weights to a GitHub Release (just bundle them)
  -h, --help                    Show this help
EOF
}

TASKS=(intruder maintenance)
EPOCHS=100
IMGSZ=640
BATCH=16
WORKERS=8
DEVICE=0
SKIP_SMOKE=0
SMOKE_ONLY=0
RETRAIN=0
ALLOW_CPU=0
PUBLISH=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --only)
      [[ "${2:-}" == intruder || "${2:-}" == maintenance ]] || { usage >&2; exit 2; }
      TASKS=("$2"); shift 2 ;;
    --epochs) EPOCHS="$2"; shift 2 ;;
    --imgsz) IMGSZ="$2"; shift 2 ;;
    --batch) BATCH="$2"; shift 2 ;;
    --workers) WORKERS="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    --smoke-only) SMOKE_ONLY=1; shift ;;
    --retrain) RETRAIN=1; shift ;;
    --allow-cpu) ALLOW_CPU=1; shift ;;
    --no-publish) PUBLISH=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GS="$ROOT/ground-station"
PY="$GS/.venv/bin/python"
cd "$GS"

MBDD_URL="https://zenodo.org/api/records/15622584/files/MBDD2025.zip/content"
MBDD_SIZE=2533687033
MBDD_MD5=b2dfdce060ef687c327b1f8203b52636
MBDD_ZIP=datasets/MBDD2025.zip
MBDD_RAW=datasets/mbdd2025-raw
MBDD_YAML=datasets/mbdd2025/mbdd2025.yaml

mkdir -p runs models datasets
LOG="runs/train-models-$(date +%Y%m%d-%H%M%S).log"
exec > >(tee -a "$LOG") 2>&1
trap 'echo; echo "Interrupted. Rerun scripts/train-models.sh with the same options to resume."; exit 130' INT

step() { printf '\n==> %s\n' "$*"; }
warn() { printf 'warning: %s\n' "$*"; }
die() { printf 'error: %s\n' "$*"; exit 1; }
has_task() { [[ " ${TASKS[*]} " == *" $1 "* ]]; }
output_for() { [[ "$1" == intruder ]] && echo models/yolov8n-visdrone.pt || echo models/yolov8n-mbdd2025.pt; }
data_for() { [[ "$1" == intruder ]] && echo VisDrone.yaml || echo "$MBDD_YAML"; }

step "Checking the machine (log: ground-station/$LOG)"
[[ "$ROOT" != /mnt/* ]] || die "The repo is on the Windows drive ($ROOT). Clone it into the Linux home folder (cd ~ && git clone ...); reading datasets through /mnt is many times slower."
for cmd in python3 curl md5sum; do
  command -v "$cmd" >/dev/null || die "$cmd is missing. On Ubuntu: sudo apt install -y python3-venv curl"
done
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || die "Python 3.11+ is required, found $(python3 --version). Use Ubuntu 24.04 or newer."
if command -v nvidia-smi >/dev/null; then
  nvidia-smi --query-gpu=index,name,memory.used,memory.total,driver_version --format=csv
elif [[ $ALLOW_CPU == 0 ]]; then
  die "nvidia-smi not found. Install the NVIDIA driver (on WSL2: the normal Windows driver, nothing inside Linux)."
fi
free_gb=$(df -Pk . | awk 'NR==2 {print int($4 / 1048576)}')
echo "Free disk: ${free_gb} GB"
(( free_gb >= 20 )) || warn "under 20 GB free; the datasets and runs need about 15 GB."
if [[ $PUBLISH == 1 && $SMOKE_ONLY == 0 ]]; then
  REPO="${DRONE_UI_REPO:-$(git -C "$ROOT" remote get-url origin | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')}"
  command -v gh >/dev/null \
    || die "gh (GitHub CLI) is needed to publish the weights. On Ubuntu: sudo apt install -y gh, then gh auth login. Or pass --no-publish."
  gh auth status >/dev/null 2>&1 || die "gh isn't signed in. Run gh auth login, or pass --no-publish."
  perm=$(gh repo view "$REPO" --json viewerPermission -q .viewerPermission 2>/dev/null || echo NONE)
  [[ $perm == ADMIN || $perm == MAINTAIN || $perm == WRITE ]] \
    || die "Your GitHub account can't create releases on $REPO (permission: $perm). Ask the repo owner for write access, or pass --no-publish and send the bundle instead."
  echo "Will publish to github.com/$REPO (permission: $perm)"
fi

step "Setting up the Python environment"
if [[ ! -x "$PY" ]]; then
  python3 -m venv .venv || die "python3 -m venv failed. On Ubuntu: sudo apt install -y python3-venv"
fi
if ! "$PY" -c "import torch, ultralytics, lap" 2>/dev/null; then
  "$PY" -m pip install --upgrade pip
  "$PY" -m pip install torch torchvision
  "$PY" -m pip install -r requirements-vision.txt
fi
if command -v nvidia-smi >/dev/null && "$PY" -c "import sys, torch; sys.exit('+cpu' not in torch.__version__)"; then
  echo "Replacing the CPU-only PyTorch build with the CUDA build"
  "$PY" -m pip install --force-reinstall torch torchvision
fi
"$PY" - <<'EOF'
import torch, ultralytics
print(f"torch {torch.__version__}, ultralytics {ultralytics.__version__}, CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    p = torch.cuda.get_device_properties(0)
    print(f"GPU 0: {p.name}, {p.total_memory / 2**30:.1f} GB")
EOF
if ! "$PY" -c "import sys, torch; sys.exit(not torch.cuda.is_available())"; then
  [[ $ALLOW_CPU == 1 ]] || die "PyTorch can't see the GPU. See Troubleshooting in docs/TRAINING.md."
  warn "no CUDA GPU; training on the CPU"
  DEVICE=cpu
fi

if [[ ! -f models/yolov8n.pt ]]; then
  step "Downloading the COCO starting weights"
  "$PY" -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt')"
fi

if has_task maintenance && [[ ! -f "$MBDD_YAML" ]]; then
  step "Preparing MBDD2025"
  if [[ ! -f "$MBDD_RAW/.extracted" ]]; then
    size=$(stat -c %s "$MBDD_ZIP" 2>/dev/null || echo 0)
    if (( size != MBDD_SIZE )); then
      echo "Downloading MBDD2025.zip (2.5 GB) from Zenodo"
      curl -L --fail --retry 5 --retry-delay 10 --progress-bar -C - -o "$MBDD_ZIP" "$MBDD_URL"
    fi
    echo "Verifying checksum"
    if [[ "$(md5sum "$MBDD_ZIP" | cut -d' ' -f1)" != "$MBDD_MD5" ]]; then
      rm -f "$MBDD_ZIP"
      die "MBDD2025.zip checksum mismatch; deleted it. Rerun to download again."
    fi
    echo "Extracting"
    rm -rf "$MBDD_RAW"
    python3 -m zipfile -e "$MBDD_ZIP" "$MBDD_RAW"
    touch "$MBDD_RAW/.extracted"
  fi
  "$PY" -m tools.prepare_mbdd2025 "$MBDD_RAW" --out datasets/mbdd2025 --link
fi

if has_task intruder; then
  echo "VisDrone is downloaded by Ultralytics into: $("$PY" -c "from ultralytics.utils import SETTINGS; print(SETTINGS['datasets_dir'])")"
fi

train_args=(--imgsz "$IMGSZ" --batch "$BATCH" --workers "$WORKERS" --device "$DEVICE")

if [[ $SKIP_SMOKE == 0 ]]; then
  for task in "${TASKS[@]}"; do
    if [[ $RETRAIN == 0 ]] && { [[ -f "$(output_for "$task")" ]] || [[ -f "runs/$task/weights/last.pt" ]]; }; then
      continue
    fi
    step "Smoke test: $task (1 epoch on 1% of the data)"
    rm -rf "runs/smoke-$task"
    "$PY" -m tools.train "$task" --data "$(data_for "$task")" --epochs 1 --fraction 0.01 \
      "${train_args[@]}" --name "smoke-$task" --no-install
  done
fi
if [[ $SMOKE_ONLY == 1 ]]; then
  step "Smoke tests passed. Run again without --smoke-only to train."
  exit 0
fi

for task in "${TASKS[@]}"; do
  output="$(output_for "$task")"
  if [[ -f "$output" && $RETRAIN == 0 ]]; then
    step "$task: $output already installed, skipping (use --retrain to train again)"
    continue
  fi
  if [[ $RETRAIN == 1 ]]; then
    archive="runs/archive-$(date +%Y%m%d-%H%M%S)-$task"
    mkdir -p "$archive"
    [[ -d "runs/$task" ]] && mv "runs/$task" "$archive/"
    [[ -f "$output" ]] && mv "$output" "$archive/"
    echo "Archived the previous $task run in $archive"
  fi
  step "Training $task ($EPOCHS epochs at $IMGSZ, batch $BATCH)"
  "$PY" -m tools.train "$task" --data "$(data_for "$task")" --epochs "$EPOCHS" "${train_args[@]}" --resume
done

step "Measuring accuracy on the validation splits"
mkdir -p runs/benchmarks
for task in "${TASKS[@]}"; do
  [[ -f "$(output_for "$task")" ]] || continue
  "$PY" -m tools.benchmark --json "runs/benchmarks/$task.json" accuracy "$task" \
    --data "$(data_for "$task")" --device "$DEVICE" || warn "$task benchmark failed; the weights are still installed"
done

step "Bundling the results"
{
  echo "date: $(date -Is)"
  echo "commit: $(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
  echo "options: epochs=$EPOCHS imgsz=$IMGSZ batch=$BATCH workers=$WORKERS device=$DEVICE"
  "$PY" -c "import torch, ultralytics; print(f'torch {torch.__version__}, ultralytics {ultralytics.__version__}')"
  command -v nvidia-smi >/dev/null && nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader
} > runs/environment.txt
files=(runs/environment.txt)
for f in models/yolov8n-visdrone.pt models/yolov8n-mbdd2025.pt runs/benchmarks/*.json \
         runs/{intruder,maintenance}/{args.yaml,results.csv,results.png,confusion_matrix.png,confusion_matrix_normalized.png}; do
  [[ -f "$f" ]] && files+=("$f")
done
bundle="runs/drone-ui-weights-$(date +%Y%m%d-%H%M).tar.gz"
tar -czf "$bundle" "${files[@]}"

if [[ $PUBLISH == 1 ]]; then
  weights=()
  for f in models/yolov8n-visdrone.pt models/yolov8n-mbdd2025.pt; do
    if [[ -f "$f" ]]; then weights+=("$f"); fi
  done
  digest=""
  if (( ${#weights[@]} > 0 )); then
    digest=$(sha256sum "${weights[@]}" | sha256sum | cut -d' ' -f1)
  fi
  if [[ -z "$digest" ]]; then
    warn "no trained weights to publish"
  elif [[ "$(cat runs/published.sha256 2>/dev/null)" == "$digest" ]]; then
    step "These weights are already published on github.com/$REPO; skipping"
  else
    tag="models-$(date +%Y%m%d-%H%M)"
    step "Publishing $tag to github.com/$REPO"
    {
      echo "Trained with \`scripts/train-models.sh\`. Install with \`./scripts/fetch-models.sh\`."
      echo
      echo '```text'
      cat runs/environment.txt
      echo '```'
      for json in runs/benchmarks/*.json; do
        [[ -f "$json" ]] || continue
        echo
        echo "**$(basename "$json" .json)** validation accuracy:"
        echo
        echo '```json'
        cat "$json"
        echo '```'
      done
    } > runs/release-notes.md
    target=()
    if git -C "$ROOT" branch -r --contains HEAD 2>/dev/null | grep -q .; then
      target=(--target "$(git -C "$ROOT" rev-parse HEAD)")
    fi
    gh release create "$tag" "${weights[@]}" "$bundle" --repo "$REPO" "${target[@]}" \
      --title "Vision models $(date +%Y-%m-%d)" --notes-file runs/release-notes.md \
      || die "Publishing failed. The weights and bundle are saved; rerun the same command to retry, or send $GS/$bundle instead."
    echo "$digest" > runs/published.sha256
    echo "Published https://github.com/$REPO/releases/tag/$tag"
  fi
fi

step "Done"
echo "Bundle: $GS/$bundle ($(du -h "$bundle" | cut -f1))"
if [[ $PUBLISH == 1 ]]; then
  echo "Everyone on the team can now install the weights with ./scripts/fetch-models.sh"
else
  echo "Send that file back. It holds the trained weights, accuracy numbers, and training curves."
fi
