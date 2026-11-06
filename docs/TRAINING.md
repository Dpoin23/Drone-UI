# Training the vision models

The detectors work out of the box, but not at their best:

- **Intruder detection** falls back to the stock COCO `yolov8n.pt`. Its person and vehicle classes are trained on ground-level photos, so aerial footage is harder.
- **Maintenance detection** is unavailable until MBDD2025 weights exist.

This guide covers what to train, where to get the data, and the cheapest ways to get the compute. For how training fits into the running pipeline, see [VISION_PIPELINE.md](VISION_PIPELINE.md#training).

**Training on your own NVIDIA GPU** Go straight to [Train on an RTX 4080](#train-on-an-rtx-4080). One script does the whole run.

Weights are not committed to the repo. They live in `ground-station/models/`, which is ignored by Git. Trained weights are shared as GitHub Releases (tagged `models-<date>`), and `./scripts/fetch-models.sh` installs the newest ones on any clone.

## What you need to produce

| Stream | Dataset | Output file | Used when the file exists | Without it |
|---|---|---|---|---|
| Intruder | VisDrone2019-DET | `models/yolov8n-visdrone.pt` | Automatically | Stock COCO `yolov8n.pt` |
| Maintenance | MBDD2025 | `models/yolov8n-mbdd2025.pt` | Automatically | Stream shows as unavailable |

Both are YOLOv8n detection models, fine-tuned from `yolov8n.pt`. The training script copies the best checkpoint into `models/` under the names above. You can point elsewhere with `DRONE_UI_INTRUDER_MODEL` and `DRONE_UI_MAINTENANCE_MODEL`.

Each file is a complete Ultralytics checkpoint of about 6 MB: the network, its fp16 weights, and the class names. Nothing else is needed to run it, but the ground station should have the same Ultralytics major version (8.x) that trained it.

## Train on an RTX 4080

This is the recommended path. `scripts/train-models.sh` runs the whole thing on one local NVIDIA GPU:

1. Checks the machine: GPU, driver, Python version, and free disk space.
2. Creates the Python environment and installs the CUDA build of PyTorch, Ultralytics, and the other dependencies.
3. Downloads the COCO starting weights.
4. Downloads MBDD2025 from Zenodo, verifies its checksum, unpacks it, and converts it to YOLO format.
5. Runs a 1-epoch smoke test on 1% of each dataset. Ultralytics downloads VisDrone during the first one.
6. Trains intruder detection (VisDrone), then maintenance detection (MBDD2025), 100 epochs each.
7. Measures mAP, precision, and recall on each validation split.
8. Packs the trained weights, the accuracy numbers, and the training curves into one `.tar.gz` file.
9. Publishes the weights and that bundle as a GitHub Release, so everyone on the team can install them with `./scripts/fetch-models.sh`.

The script is safe to rerun. Finished steps are skipped. If training stops partway (Ctrl-C, a crash, a Windows Update reboot), running the same command again resumes from the last completed epoch.

### What to expect

| | RTX 4080 (16 GB) |
|---|---|
| Training time, both models | About 3–4 hours at the default settings, plus 15–40 minutes of downloads (Zenodo often serves MBDD2025 at only a few MB/s) |
| Disk | About 15 GB: ~5 GB in `ground-station/datasets/` and ~5 GB of VisDrone next to the clone (for example `~/datasets/VisDrone`); the script prints the exact path |
| GPU memory | About 4–5 GB at the defaults (640 pixels, batch 16) |
| Electricity | Under $1 (about 400 W for 4 hours is 1.6 kWh) |

These times are planning estimates. With a model this small, data loading on the CPU often limits speed as much as the GPU does. A 12 GB laptop RTX 4080 runs the same defaults without changes.

### 1. Prepare the machine

The script needs Linux and bash. On Windows, run it inside WSL2, which can use the Windows NVIDIA driver directly.

**Windows (WSL2):**

1. Update the NVIDIA driver in Windows (GeForce Experience, the NVIDIA App, or nvidia.com) to version 580 or newer. PyTorch's default build uses CUDA 13, which needs it. **Do not install an NVIDIA driver inside Ubuntu**; WSL2 uses the Windows one.
2. In PowerShell: `wsl --install -d Ubuntu-24.04`, then restart if asked and create a Linux user when Ubuntu opens.
3. In the Ubuntu terminal, confirm the GPU is visible and install the system packages:

   ```bash
   nvidia-smi                      # should list the RTX 4080
   sudo apt update && sudo apt install -y git python3-venv curl tmux gh
   ```

4. Stop Windows from sleeping during the run: **Settings → System → Power → Screen and sleep → "When plugged in, put my device to sleep after" → Never**. Sleep pauses WSL and stops training. Rerunning resumes it, but the time is lost.

**Linux desktop:** install the NVIDIA proprietary driver (580 or newer) so `nvidia-smi` works, plus `git python3-venv curl tmux gh`. Use Ubuntu 24.04 or anything else with Python 3.11 or newer.

**GitHub access (both):** the script publishes the finished weights as a release on `Dpoin23/Drone-UI`, which needs write access to the repo. Ask the repo owner to add you as a collaborator, then sign in once with `gh auth login` (GitHub.com, HTTPS, log in with a web browser). The script checks this in its first minute, so a missing login fails right away rather than after hours of training. To skip publishing, pass `--no-publish` and send the bundle by hand.

### 2. Clone the repo

Clone into the Linux home folder. On WSL2, **not** under `/mnt/c/...`: reading tens of thousands of small images through the Windows drive is many times slower, so the script refuses to run there.

```bash
cd ~
git clone https://github.com/Dpoin23/Drone-UI.git
cd Drone-UI
```

### 3. Run the training

Start it inside `tmux` so it keeps running if the terminal is closed by accident:

```bash
tmux new -s train
./scripts/train-models.sh
```

That's the whole run. Detach with `Ctrl-b d` and reattach with `tmux attach -t train`. On WSL2, keep at least one Ubuntu terminal window open, even minimized, because WSL can shut down when the last one closes.

To check the setup before committing hours, run only the downloads and smoke tests first (20–45 minutes, mostly downloading), then run the full command:

```bash
./scripts/train-models.sh --smoke-only
./scripts/train-models.sh
```

**Watching progress:** each epoch prints a progress bar, then the losses and mAP. The full output is also saved to `ground-station/runs/train-models-<time>.log`. In a second terminal, `nvidia-smi -l 5` shows GPU use and memory. Per-epoch numbers are in `ground-station/runs/intruder/results.csv` and `runs/maintenance/results.csv`.

**If it stops:** run the same command again. Already-installed models are skipped and the interrupted one resumes from `runs/<task>/weights/last.pt`.

### Script options

| Option | Default | Use it to |
|---|---|---|
| `--only intruder` or `--only maintenance` | both | Train one detector |
| `--epochs N` | 100 | Use 30 for a quick first result; 150–200 if mAP is still climbing at 100 |
| `--imgsz N` | 640 | Try 960 for VisDrone's small objects (fits in 16 GB at batch 16) |
| `--batch N` | 16 | Lower it if CUDA runs out of memory |
| `--workers N` | 8 | Lower it (4) if Linux or WSL runs out of RAM |
| `--device D` | 0 | Pick another GPU on a multi-GPU machine |
| `--skip-smoke` | off | Skip the smoke tests on reruns |
| `--smoke-only` | off | Stop after setup, downloads, and smoke tests |
| `--retrain` | off | Train again even though weights are installed. The previous run and weights move to `runs/archive-<time>-<task>/`. |
| `--no-publish` | off | Don't create a GitHub Release; only write the bundle |

Options only apply to a new run. When the script resumes an interrupted run, Ultralytics keeps the original epochs, image size, and batch.

A higher-resolution second pass on VisDrone, once the baseline is done:

```bash
./scripts/train-models.sh --only intruder --retrain --imgsz 960
```

Expect roughly 2.25× the time of the 640 run. Compare the two `runs/benchmarks/intruder.json` results (the archived run keeps its own copy of the curves) and keep the better one.

### 4. Share the results

The script publishes the results itself. The last lines of the output name the release and the bundle, for example:

```text
Published https://github.com/Dpoin23/Drone-UI/releases/tag/models-20261105-2210
Bundle: /home/you/Drone-UI/ground-station/runs/drone-ui-weights-20261105-2210.tar.gz (14M)
```

The release holds `yolov8n-visdrone.pt`, `yolov8n-mbdd2025.pt`, and the bundle, and its notes list the accuracy numbers. Anyone on the team installs the weights with `./scripts/fetch-models.sh` (see [Use the trained weights](#use-the-trained-weights)). If publishing failed, rerun the same command: training is skipped and only the upload is retried. Rerunning after a successful upload doesn't publish the same weights twice.

With `--no-publish`, send the bundle (about 15 MB) through whatever you normally use for file sharing instead. On WSL2, open the folder in Windows Explorer with `explorer.exe ~/Drone-UI/ground-station/runs`. The bundle contains:

- `models/yolov8n-visdrone.pt` and `models/yolov8n-mbdd2025.pt`: the trained weights
- `runs/benchmarks/*.json`: mAP50, mAP50-95, precision, and recall per model
- `runs/intruder/` and `runs/maintenance/`: training settings, `results.csv`, the loss and mAP curves, and confusion matrices
- `runs/environment.txt`: GPU, driver, library versions, and the commit that was trained

### 5. Clean up

Once the release is published (or the bundle has been received), the datasets can go. They take about 10 GB:

```bash
rm -rf ~/Drone-UI/ground-station/datasets ~/datasets/VisDrone   # use the VisDrone path the script printed
```

Keep `ground-station/runs/` if you might train again. It holds `last.pt` checkpoints and the curves.

## Compute: cheapest options first

Training on a CPU is only useful as a smoke test. A full run needs a CUDA GPU. NVIDIA T4-class is enough; an RTX 3090/4090 is faster but not required.

| Option | GPU | Cost | Limits | Best for |
|---|---|---|---|---|
| **Team RTX 4080 (local)** | RTX 4080 (16 GB) | **Electricity only, under $1 for both runs** | Machine must stay awake for ~4 hours | **Start here.** One script, no shared-box constraints. See [Train on an RTX 4080](#train-on-an-rtx-4080). |
| Exovrix tower (SSH) | 2× RTX 3090 (24 GB) | Electricity only, under $1 for both runs | Shared box: GPU 0 is often busy with other training, GPU 1 is shared with Ollama; RAM is tight | When the 4080 isn't available and GPU 1 is free. See [Tower path](#alternative-the-exovrix-tower). |
| **Kaggle Notebooks** | 2× T4 or 1× P100 | **$0** | ~30 GPU-hours/week, 12-hour sessions, single GPU per training job | Fallback when the tower is busy. Both runs usually fit. |
| Google Colab free | T4-class, varies | **$0** | Not published, can be interrupted, 12-hour max | Fallback if Kaggle is busy |
| Google Colab Pro | T4/A100-class | ~$10/month | Compute units; GPU not guaranteed | Interactive tuning, not long unattended runs |
| Vast.ai | RTX 3090/4090 | ~$0.13–0.46/hr | Marketplace hosts vary; per-second billing | Cheapest paid; both runs for a few dollars |
| RunPod Community | RTX 3090 / 4090 | ~$0.22 / $0.34/hr | Per-second billing | Simple managed alternative to Vast |
| Local NVIDIA GPU | GTX 1660 / RTX 3060+ | electricity | 8 GB VRAM is enough at 640 | No upload, repeat runs |
| CPU | any | $0 | Hours per epoch | Code/dataset smoke test only |

Prices checked November 2026; they move often. Check the provider's live pricing before renting. A local RTX 4080 or the tower costs only electricity. Without either, a single 12-hour Kaggle session is usually enough for either dataset at the default settings.

## Dataset facts

| Dataset | Images | Classes | Download | Notes |
|---|---|---|---|---|
| **VisDrone2019-DET** | 8,629 (6,471 train / 548 val / 1,610 test) | 10: pedestrian, people, bicycle, car, van, truck, tricycle, awning-tricycle, bus, motor | ~2 GB, fetched automatically by Ultralytics; allow ~4 GB free disk | Aerial urban scenes, many tiny objects. The detector only reports the person and vehicle classes. |
| **MBDD2025** | 14,471 (70/20/10 split by our prep tool) | 5: crack, leakage, abscission, corrosion, bulge | ~2.5 GB zip from Zenodo | UAV building-facade images, Pascal VOC annotations, CC BY 4.0. A Kaggle mirror also exists. |

VisDrone is downloaded by Ultralytics the first time you pass `VisDrone.yaml`. MBDD2025 must be downloaded by hand:

- Zenodo: <https://zenodo.org/records/15622584> (`MBDD2025.zip`)
- Kaggle mirror (convenient on Kaggle): search for `mbdd2025-building-defects`

MBDD2025 ships `JPEGImages/` and `Annotations/` (VOC XML). `tools/prepare_mbdd2025.py` converts the XML to YOLO labels, keeps the class order explicit, and writes the `mbdd2025.yaml` data file. Do not use its `Labels/` folder directly; the prep tool exists so the class order cannot drift.

## Manual setup

`scripts/train-models.sh` does all of this for you on a Linux or WSL2 machine. Use the manual steps on a cloud notebook, on a machine without bash, or to run one stage at a time.

Use a GPU machine or a cloud notebook. On a laptop without an NVIDIA GPU, the CPU PyTorch build is fine only for the smoke test.

```bash
git clone https://github.com/Dpoin23/Drone-UI.git
cd Drone-UI/ground-station

python3 -m venv .venv
.venv/bin/pip install --upgrade pip

# On a GPU machine, install the normal CUDA build (do NOT use the CPU index):
.venv/bin/pip install torch torchvision

# On a CPU-only laptop, use the smaller CPU build instead:
# .venv/bin/pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu

.venv/bin/pip install -r requirements-vision.txt
```

Check that the GPU is visible:

```bash
.venv/bin/python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else '')"
```

Make sure the starting weights are where `tools/train.py` expects them:

```bash
mkdir -p models
.venv/bin/python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
cp yolov8n.pt models/yolov8n.pt
```

Alternatively, start the ground station once and let it download the stock weights into `models/`, or pass `--base yolov8n.pt` to the training command.

## Smoke test first

Prove the code, dataset path, and GPU setup with one epoch on 1% of the data before spending GPU hours.

```bash
cd ground-station

# Intruder: Ultralytics downloads VisDrone on first use
.venv/bin/python -m tools.train intruder --device cpu --epochs 1 --fraction 0.01 --batch 4 \
  --name smoke-intruder --no-install

# Maintenance: prepare the dataset first (see below), then
.venv/bin/python -m tools.train maintenance --data datasets/mbdd2025/mbdd2025.yaml \
  --device cpu --epochs 1 --fraction 0.01 --batch 4 --name smoke-maintenance --no-install
```

A CPU epoch on 1% of the data still takes a few minutes. The point is to see the dataset load and the first epoch print without errors. `--name` keeps the smoke run out of the real run's folder, and `--no-install` stops its 1-epoch weights from replacing the model the ground station uses.

## Train intruder detection (VisDrone)

```bash
cd ground-station
.venv/bin/python -m tools.train intruder --epochs 100 --device 0
```

What happens:

1. Ultralytics downloads and converts VisDrone into its datasets directory. Watch the first log lines for the exact path.
2. YOLOv8n is fine-tuned for 100 epochs at `imgsz=640`, batch 16.
3. The best checkpoint is copied to `models/yolov8n-visdrone.pt` and the run is kept under `runs/intruder/`.

If the automatic download fails, download VisDrone2019-DET yourself, convert it to YOLO format, and pass your own YAML with `--data /path/to/VisDrone.yaml`.

Small objects are the hard part of VisDrone. Once the 640 baseline works, and if the GPU has headroom, retry at higher resolution:

```bash
.venv/bin/python -m tools.train intruder --epochs 100 --imgsz 960 --batch 8 --device 0
```

960 costs roughly 2.25× the compute of 640, and 1280 roughly 4×. Do not start there.

## Train maintenance detection (MBDD2025)

Download and extract the dataset, then convert it:

```bash
cd ground-station

# Browser download from https://zenodo.org/records/15622584 is easiest.
# On a headless box, the Zenodo API gives a direct link:
mkdir -p datasets
curl -L -o datasets/MBDD2025.zip "https://zenodo.org/api/records/15622584/files/MBDD2025.zip/content"
md5sum datasets/MBDD2025.zip      # should be b2dfdce060ef687c327b1f8203b52636
python3 -m zipfile -e datasets/MBDD2025.zip datasets/mbdd2025-raw

.venv/bin/python -m tools.prepare_mbdd2025 datasets/mbdd2025-raw --out datasets/mbdd2025
```

The prep tool writes:

```text
datasets/mbdd2025/
  images/{train,val,test}/
  labels/{train,val,test}/
  mbdd2025.yaml
```

Then train:

```bash
.venv/bin/python -m tools.train maintenance \
  --data datasets/mbdd2025/mbdd2025.yaml \
  --epochs 100 --device 0
```

The best checkpoint is copied to `models/yolov8n-mbdd2025.pt`. If you move the dataset to another machine, rerun `prepare_mbdd2025` there or edit the absolute `path:` in `mbdd2025.yaml`.

Optional second stage: a defect crop classifier. Train a `yolov8n-cls` model on cropped defect images, then set `DRONE_UI_DEFECT_CLASSIFIER` to the weights file. A severity word in the classifier label (`minor`, `moderate`, `severe`, `critical`) overrides the detector's severity grade.

## Recommended settings

| Flag | Baseline | When to change |
|---|---|---|
| `--epochs` | 100 | Use 30 for a first real result; 150–200 if validation mAP is still climbing |
| `--imgsz` | 640 | 960 or 1280 for VisDrone small objects, if the GPU allows |
| `--batch` | 16 | Halve it on 8 GB cards or when CUDA runs out of memory |
| `--base` | `models/yolov8n.pt` | Keep the COCO starting point; it trains much faster than from scratch |
| `--device` | auto (first GPU) | `0` for the first GPU, `cpu` only for smoke tests |
| `--fraction` | 1.0 | `0.01`–`0.1` to validate the pipeline quickly |
| `--workers` | 8 | Lower on a small cloud VM (for example 2) if data loading stalls |
| `--name` | task name | Run folder under `runs/`. Use a different name for experiments so they don't mix with the real run. |
| `--resume` | off | Continue `runs/<name>/weights/last.pt` after an interruption. If the run had already finished, it just installs that run's best weights. |
| `--no-install` | off | Keep the result in `runs/` instead of copying it into `models/`. Use it for smoke tests and experiments. |

Training prints per-epoch mAP, precision, recall, and losses. Ultralytics also writes `results.csv`, `results.png`, and `confusion_matrix.png` under `runs/<task>/`.

## Cost and time estimates

These are planning numbers for YOLOv8n at 640. Measure your own run from `results.csv` or the elapsed time in the log.

| Run | T4 / P100 (Kaggle) | One RTX 3090 or RTX 4080 | Local electricity | Approx. rented cost |
|---|---|---|---|---|
| VisDrone, 100 epochs | ~2–4 GPU-hours | ~1–1.5 hours | ~$0.10–0.20 | ~$1–2 at Vast/RunPod rates |
| MBDD2025, 100 epochs | ~4–8 GPU-hours | ~2–2.5 hours | ~$0.20–0.35 | ~$1–3 at Vast/RunPod rates |
| VisDrone at `imgsz` 960 (optional) | ~5–9 GPU-hours | ~2.5–3.5 hours | ~$0.25–0.45 | ~$1–3 |
| **Both baseline runs** | ~6–12 hours, two Kaggle sessions | **~3–4 hours** | **~$0.30–0.55** | ~$2–5 |

A 4080 and a 3090 are close enough for YOLOv8n that one column covers both; the 4080 is usually a little faster. The electricity figures assume about 350–400 W of extra draw while training: the GPU at full load (about 250 W for a tower 3090, up to 320 W for a 4080), plus CPU data loading. They also assume $0.30/kWh, close to Californian residential rates. At the US average of about $0.18/kWh, take roughly 40% off. The formula is extra watts × hours ÷ 1000 × your $/kWh.

Recommended path:

1. Run `scripts/train-models.sh` on the team's RTX 4080. It smoke-tests, trains both models one after the other, and publishes the results as a GitHub Release, for well under $1 of electricity.
2. If the 4080 isn't available, use the tower's free GPU. The same script works there (see below).
3. If neither is free, use Kaggle for $0. Rent a 3090/4090 only if you need higher resolution or more epochs and no local GPU is available.

## Alternative: the Exovrix tower

The tower (`exovrix-inference`, Ubuntu 24.04, 24 CPU cores, 30 GB RAM, 2× RTX 3090 24 GB) is reached over SSH. It's a shared box, so the main work is staying out of the way of what's already running there.

What the current stats say:

| Resource | State | What it means for training |
|---|---|---|
| GPU 0 | 100% busy, 20.3 of 24 GB, `ml5b-train` | Don't use it while that job runs. |
| GPU 1 | Idle, 9.8 of 24 GB held (likely Ollama's loaded model) | **Use this one.** ~14 GB free is plenty: YOLOv8n needs ~3–5 GB at 640/batch 16, ~8 GB at 960/batch 16. |
| RAM | 15.6 of 30.3 GB used, **swap 100% full** | The real limit. Keep `--workers` at 4–6 and don't cache the dataset in RAM. The training script doesn't by default. |
| CPU | 24 cores, ~5% busy | Plenty for data loading. |
| Disk | ~750 GB free | Datasets and runs need ~20 GB. |
| Network | Wi-Fi (`wlp11s0`) | The ~4.5 GB of dataset downloads take a few minutes to ~20 minutes depending on signal. |

### 1. Check which GPU is free

```bash
ssh tower            # your SSH alias or user@host for exovrix-inference
nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total --format=csv
free -h
```

Pick a GPU with low utilization and at least 6 GB free. These steps assume GPU 1. If `free -h` shows under ~4 GB available, wait or lower `--workers` further. A data loader pushing the box deeper into swap slows every container on it, and the kernel may kill one.

### 2. Set up once

```bash
git clone https://github.com/Dpoin23/Drone-UI.git ~/Drone-UI
cd ~/Drone-UI/ground-station
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install torch torchvision          # normal CUDA build
.venv/bin/pip install -r requirements-vision.txt
mkdir -p models
.venv/bin/python -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt')"
CUDA_VISIBLE_DEVICES=1 .venv/bin/python -c "import torch; print(torch.cuda.get_device_name(0))"
```

`CUDA_VISIBLE_DEVICES=1` makes the process see only physical GPU 1, which it then calls device `0`. That's why every command below passes `--device 0`. It keeps training off GPU 0 even if a default slips through.

### 3. Train inside tmux

The runs take hours, so start them in `tmux` so a dropped SSH connection doesn't kill them. The training script handles the rest; the GPU choice and the lower worker count are the only tower-specific parts:

```bash
tmux new -s drone-train
cd ~/Drone-UI
CUDA_VISIBLE_DEVICES=1 ./scripts/train-models.sh --workers 6
```

Detach with `Ctrl-b d` and reattach later with `tmux attach -t drone-train`. To run the stages by hand instead:

```bash
cd ~/Drone-UI/ground-station

# Smoke test (a minute or two)
CUDA_VISIBLE_DEVICES=1 .venv/bin/python -m tools.train intruder --epochs 1 --fraction 0.01 --device 0 --workers 4 \
  --name smoke-intruder --no-install

# VisDrone, then MBDD2025, one after the other
CUDA_VISIBLE_DEVICES=1 .venv/bin/python -m tools.train intruder --epochs 100 --device 0 --workers 6

mkdir -p datasets
curl -L -o datasets/MBDD2025.zip "https://zenodo.org/api/records/15622584/files/MBDD2025.zip/content"
python3 -m zipfile -e datasets/MBDD2025.zip datasets/mbdd2025-raw
.venv/bin/python -m tools.prepare_mbdd2025 datasets/mbdd2025-raw --out datasets/mbdd2025 --link
CUDA_VISIBLE_DEVICES=1 .venv/bin/python -m tools.train maintenance \
  --data datasets/mbdd2025/mbdd2025.yaml --epochs 100 --device 0 --workers 6
```

`--link` symlinks the prepared images instead of copying them, which saves ~2.5 GB. If a run is interrupted, add `--resume` to the same command.

GPU 1 has room for both runs at once (~4 GB each). On this box, RAM is what decides it. Running them in parallel saves about an hour, but only do it if `free -h` shows at least 8 GB available, and use `--workers 3` for each.

### 4. Using both GPUs

When `ml5b-train` is finished and GPU 0 is free too, Ultralytics can split one run across both cards:

```bash
.venv/bin/python -m tools.train intruder --epochs 100 --device 0,1 --batch 32 --workers 6
```

Expect about 1.6–1.8× the speed of one 3090, which brings both baseline runs to roughly 2 hours. Electricity per run stays about the same, because two cards run for roughly half as long. It's only worth it for the higher-resolution or longer runs. For the baseline, one GPU is simpler and leaves the other free.

### 5. Effect on other services

Training on GPU 1 shares it with Ollama. Model replies from `exovrix-ollama`, and anything routed through `exovrix-nexus`, may be slower while training runs, but they won't fail at these memory levels. If that matters, run training overnight. Check `nvidia-smi` occasionally. If GPU 1's memory gets near 24 GB, lower `--batch`.

### 6. Copy the weights back

From the laptop that runs the ground station:

```bash
scp tower:~/Drone-UI/ground-station/models/yolov8n-visdrone.pt \
    tower:~/Drone-UI/ground-station/models/yolov8n-mbdd2025.pt \
    ground-station/models/
```

The run folders (`~/Drone-UI/ground-station/runs/`) hold `results.csv`, plots, and `last.pt` for resuming. Delete them and `datasets/` from the tower when you're done, since its disk grows ~36 GB a day already.

## Cheapest path: Kaggle walkthrough

Kaggle gives about 30 free GPU-hours per week, sessions up to 12 hours, and a single T4 or P100 to a training job. Two T4s do not speed up a single YOLO run unless you write multi-GPU code; pick one GPU.

1. Create a Kaggle account and a new Notebook.
2. **Settings → Accelerator → GPU T4 x2** (or P100). **Internet → On** (needed for the repo, Ultralytics, and VisDrone).
3. Clone the repo and install the dependencies:

   ```python
   !git clone https://github.com/Dpoin23/Drone-UI.git
   %cd Drone-UI/ground-station
   !pip install -q ultralytics lap
   !python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))"
   ```

4. Train VisDrone (the download is automatic):

   ```python
   !python -m tools.train intruder --epochs 100 --device 0
   ```

5. For MBDD2025, either attach the Kaggle mirror dataset or download the Zenodo zip, then prepare and train:

   ```python
   !mkdir -p datasets
   !curl -L -o datasets/MBDD2025.zip "https://zenodo.org/api/records/15622584/files/MBDD2025.zip/content"
   !python -m zipfile -e datasets/MBDD2025.zip datasets/mbdd2025-raw
   !python -m tools.prepare_mbdd2025 datasets/mbdd2025-raw --out datasets/mbdd2025
   !python -m tools.train maintenance --data datasets/mbdd2025/mbdd2025.yaml --epochs 100 --device 0
   ```

6. Copy the weights somewhere Kaggle keeps, then download them after the session:

   ```python
   !mkdir -p /kaggle/working/models
   !cp models/*.pt /kaggle/working/models/
   ```

   Files under `/kaggle/working` appear in the notebook's output. Everything else is lost when the session ends.

7. If a run is approaching the 12-hour session limit, copy `runs/<task>/weights/last.pt` to `/kaggle/working` and download it. In the next session, put it back at `runs/<task>/weights/last.pt` and rerun the training command with `--resume`. For very long runs, a rented GPU is simpler.

## Cheapest paid path: Vast.ai or RunPod

Use this when you want one uninterrupted run, more epochs, or higher resolution.

1. Rent one RTX 3090 (24 GB) or RTX 4090, with a PyTorch/CUDA image.
2. Clone the repo and install `ultralytics` and `lap`; the image already has CUDA PyTorch.
3. Run the same commands as above with `--device 0`.
4. Copy `models/*.pt` back with `scp` or the provider's file browser.
5. Stop or destroy the instance. Billing is per second on both providers, but a stopped instance can still cost storage.

Expect roughly $1–4 total for both datasets at the baseline settings.

## Use the trained weights

On any clone of the repo, download the newest published weights into `ground-station/models/`:

```bash
./scripts/fetch-models.sh                         # newest release that has each file
./scripts/fetch-models.sh models-20261105-2210    # a specific release
```

It uses `gh` when you're signed in, and plain `curl` otherwise, which works while the repo is public. The training curves and confusion matrices are in the release's `drone-ui-weights-*.tar.gz`.

A bundle received by hand unpacks straight into place. It also adds the curves and benchmarks under `runs/`, which Git ignores:

```bash
tar -xzf drone-ui-weights-<date>.tar.gz -C /path/to/Drone-UI/ground-station
cat /path/to/Drone-UI/ground-station/runs/benchmarks/*.json     # the trainer's accuracy numbers
```

For loose weight files:

```bash
scp yolov8n-visdrone.pt yolov8n-mbdd2025.pt user@ground-station:/path/to/Drone-UI/ground-station/models/
```

Restart image processing in the UI (or restart the backend). The detectors prefer the trained files automatically. Confirm with:

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/vision/capabilities
```

The response should show `yolov8n-visdrone.pt` and `yolov8n-mbdd2025.pt` as the stream models. If you use different file names, set the environment variables instead:

```bash
DRONE_UI_INTRUDER_MODEL=my-visdrone.pt
DRONE_UI_MAINTENANCE_MODEL=my-mbdd2025.pt
```

## Verify the models

Accuracy on the dataset's validation split:

```bash
cd ground-station
.venv/bin/python -m tools.benchmark accuracy intruder --data VisDrone.yaml
.venv/bin/python -m tools.benchmark accuracy maintenance --data datasets/mbdd2025/mbdd2025.yaml
```

Speed on real footage, then the live pipeline:

```bash
.venv/bin/python -m tools.benchmark speed intruder --source flight.mp4
.venv/bin/python -m tools.benchmark pipeline --source flight.mp4 --mode patrol --seconds 60
```

The first real check is simple: run the same footage with the stock COCO weights and with the VisDrone weights, and compare how many people and vehicles are found from the air. For maintenance, confirm the classes come out as crack, leakage, abscission, corrosion, and bulge, and that the UI no longer shows the stream as unavailable.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `torch.cuda.is_available()` is `False` | Either the CPU PyTorch build is installed (the script replaces it automatically; by hand, reinstall `torch torchvision` without the CPU index URL), or the NVIDIA driver is older than 580. Update the driver; on WSL2, update it in Windows and run `wsl --shutdown` before reopening Ubuntu. |
| `nvidia-smi` not found inside WSL2 | Update the Windows NVIDIA driver and WSL (`wsl --update` in PowerShell), then `wsl --shutdown`. Don't install a Linux NVIDIA driver inside Ubuntu. |
| Script says the repo is on the Windows drive | Clone into the Linux home folder (`cd ~ && git clone ...`), not `/mnt/c/...`. |
| Training dies with `Killed`, or WSL closes during training | Linux ran out of RAM. WSL2 gets half of the Windows RAM by default. Rerun with `--workers 4`, or give WSL more memory in `%UserProfile%\.wslconfig` (`[wsl2]` then `memory=24GB`) and run `wsl --shutdown`. The rerun resumes. |
| Training stopped overnight | Windows went to sleep or restarted for an update. Run the same command again to resume, and set sleep to Never while plugged in. |
| Script stops at the start with a `gh` or "can't create releases" error | Install `gh`, run `gh auth login`, and make sure the repo owner has given your account write access. Or pass `--no-publish` and send the bundle. |
| `fetch-models.sh` says no published weights were found | Nobody has published a release yet, or the repo went private: run `gh auth login` with an account that can see it. |
| `MBDD2025.zip checksum mismatch` | The download was corrupted. The script deletes it, so rerun to download it again. |
| CUDA out of memory | Lower `--batch` (16 → 8 → 4), then `--imgsz` (640). YOLOv8n fits in 8 GB at 640. On the tower, check `nvidia-smi`: another job or Ollama may have grown on that GPU. |
| Tower training lands on the busy GPU | Prefix the command with `CUDA_VISIBLE_DEVICES=<free index>` and pass `--device 0`. Inside the process, `0` is the one GPU you exposed. |
| Tower slows down or a container gets killed during training | The box is out of RAM (swap is already full). Lower `--workers` to 2–4, run one training at a time, and check `free -h` before starting. |
| `Dataset 'VisDrone.yaml' ... not found` or download stalls | Check internet access, free disk (~4 GB), and the dataset path in the first log lines. Pass a local YAML with an absolute path if needed. |
| MBDD run finds no labels | Point `--data` at `datasets/mbdd2025/mbdd2025.yaml`, not at the raw Zenodo folder. Regenerate the YAML with `prepare_mbdd2025` after moving the dataset. |
| Maintenance still unavailable in the UI | The file must be at `models/yolov8n-mbdd2025.pt` (or set `DRONE_UI_MAINTENANCE_MODEL`). Restart processing after copying it. |
| Loss becomes NaN | Delete `*.cache` files under the dataset's `labels/` folders, check for zero-area boxes, and restart training from the pretrained base. Extremely low learning rates can also help. |
| Kaggle session died | Outputs outside `/kaggle/working` are gone. Re-run with `last.pt` and `resume=True`, or use a rented GPU. |
| Training is very slow on a T4 | Expect hours, not minutes. Keep `imgsz=640`, `batch=16`, and use `--fraction` while debugging. Higher resolution is what makes VisDrone slow. |

## Licensing and citations

- **Ultralytics YOLOv8** is AGPL-3.0. Check the implications before shipping or distributing the trained weights or a closed-source product that uses Ultralytics. While the repo is public, its GitHub Releases are too, so publishing weights there distributes them to anyone.
- **VisDrone2019-DET** comes from Tianjin University. Cite Zhu et al., "Detection and Tracking Meet Drones Challenge", IEEE TPAMI 44(11), 2022.
- **MBDD2025** is CC BY 4.0. Cite the dataset paper (Zha et al., *Scientific Data*, 2025) and the Zenodo record <https://zenodo.org/records/15622584>.
