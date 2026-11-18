# Trained Vision Models — Drone-UI

Two YOLOv8n detectors fine-tuned for the ground station: aerial intruder detection
(VisDrone2019-DET) and building-defect detection (MBDD2025). Trained on an RTX 4080 SUPER
(2026-11-14).

The two checkpoints **ship in the repo** under `ground-station/models/` (~6 MB each). A
fresh clone already has them; no release download is required for normal use. Optional
GitHub Releases (`models-*`) and `scripts/fetch-models.sh --force` remain available when
a later training run should replace them.

**Original handoff bundle:** `drone-ui-weights-20261114-0643.tar.gz` (12.5 MB) — still
useful if you want the training curves and confusion matrices under `runs/`.

---

## Contents

| File | What it is |
|---|---|
| `models/yolov8n-visdrone.pt` | Intruder detector — people and vehicles from the air (10 classes) |
| `models/yolov8n-mbdd2025.pt` | Maintenance detector — building defects (5 classes) |
| `runs/benchmarks/*.json` | Validation metrics (mAP50, mAP50-95, precision, recall) |
| `runs/{intruder,maintenance}/` | Training curves, confusion matrices, checkpoints |
| `runs/environment.txt` | GPU, driver, and library versions used |

Nothing else is needed at runtime — each `.pt` is a complete Ultralytics checkpoint
(network + fp16 weights + class names).

---

## Install

After a normal `git pull` / clone, confirm the files are present:

```bash
ls -lh ~/Drone-UI/ground-station/models/
```

```
yolov8n-visdrone.pt     6.2M
yolov8n-mbdd2025.pt     6.2M
yolov8n.pt              6.3M   # stock COCO weights, downloaded on first use
```

From a handoff bundle instead:

```bash
tar -xzf drone-ui-weights-20261114-0643.tar.gz -C ~/Drone-UI/ground-station
```

Then **restart the backend**. The vision pipeline caches models at startup, so without a
restart it keeps using the old ones:

```bash
cd ~/Drone-UI/ground-station
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

No config changes. The detectors prefer these files automatically because of their names.

---

## Verify it worked

**In the UI** (fastest): Livestream → Image processing panel.

- The **Maintenance** detector is no longer greyed out as *unavailable* — it was unusable
  before, since there were no MBDD2025 weights.
- Pick **Perimeter patrol** and press **Start**. Boxes should appear on the video.

**Via the API:**

```bash
curl -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/vision/capabilities
```

The response should list `yolov8n-visdrone.pt` and `yolov8n-mbdd2025.pt` as the active
stream models.

---

## What actually changed

| | Before | After |
|---|---|---|
| Intruder detection | Stock COCO `yolov8n.pt` — trained on ground-level photos | Fine-tuned on aerial footage |
| Maintenance detection | Unavailable | Working |
| False classes | Reports `cell phone`, `book`, `suitcase` on aerial scenes | Only the 10 VisDrone classes |

The stock COCO model doesn't just under-detect small objects — it misclassifies them.
On VisDrone validation frames it labels vehicle roofs as `cell phone` and `book`, because
it has never seen a top-down view. One dense street frame it scored as *2 cars, 17 cell
phones*; the fine-tuned model finds *30 cars, 15 motorcycles, 15 pedestrians* on the same
image.

---

## Metrics (validation splits, 100 epochs @ 640 px)

| Model | mAP50 | mAP50-95 | Precision | Recall |
|---|---|---|---|---|
| `yolov8n-visdrone.pt` | 0.329 | 0.185 | 0.448 | 0.348 |
| `yolov8n-mbdd2025.pt` | **0.879** | 0.485 | 0.867 | 0.816 |

**Maintenance detection is production-ready.** Defects are large, high-contrast targets and
a nano model handles them comfortably.

**Intruder detection is in line with published YOLOv8n/VisDrone baselines** (~0.33–0.39
mAP50), so nothing is broken — but per-class performance splits hard (mAP50-95):

| Class | Score | Class | Score |
|---|---|---|---|
| car | 0.497 | pedestrian | 0.142 |
| bus | 0.298 | tricycle | 0.117 |
| van | 0.259 | people | 0.092 |
| truck | 0.187 | awning-tricycle | 0.075 |
| motor | 0.150 | bicycle | 0.029 |

**Vehicles are covered. Pedestrians are the weak spot.** A car from altitude is still a
large rigid object with a consistent silhouette; a person is a 10×20 px blob. Recall of
0.348 means roughly a third of ground-truth objects are found, so if the threat model is
"someone walks into the perimeter", expect misses until we retrain at higher resolution.

Training converged — train and validation loss both plateau, no overfitting. More epochs
will not help; `imgsz 960` or a larger backbone is the next step.

**Speed:** ~1.7 ms/frame end-to-end on the 4080 (0.5 ms inference + 1.0 ms postprocess),
against a pipeline target of 8 FPS. Not a constraint.

---

## Requirements

- **Ultralytics 8.x** — the checkpoints were trained with `8.4.212` and need the same major
  version to load. `requirements-vision.txt` gives you 8.x by default.
- **PyTorch** — `2.15.0+cu132` was used, but any recent build works. CPU-only is fine; it
  just runs 3–5× slower. The pipeline picks the device automatically, or force it with
  `DRONE_UI_VISION_DEVICE=cpu`.
- **Different filenames?** Point the pipeline at them explicitly:

  ```bash
  DRONE_UI_INTRUDER_MODEL=my-visdrone.pt
  DRONE_UI_MAINTENANCE_MODEL=my-mbdd2025.pt
  ```

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Maintenance still shows *unavailable* | Weights are in the wrong directory. They must be at `ground-station/models/`, not the repo root. |
| Still getting COCO detections | Backend wasn't restarted — models are cached at startup. |
| `UnpicklingError` or version warnings on load | Ultralytics major version mismatch. Reinstall from `requirements-vision.txt`. |
| Only need one model | You can extract just that file: `tar -xzf <bundle> -C ~/Drone-UI/ground-station models/yolov8n-visdrone.pt` |
| Want to check the numbers yourself | `cat runs/benchmarks/*.json` after extracting the bundle. |

---

## Re-validating in five minutes

Don't take the numbers on trust. Run the same frames through both models and look:

```bash
cd ~/Drone-UI/ground-station

# fine-tuned
.venv/bin/python -c "from ultralytics import YOLO; YOLO('models/yolov8n-visdrone.pt').predict('/home/YOU/datasets/VisDrone/images/val', save=True, conf=0.3, project='/tmp/cmp', name='trained')"

# stock COCO baseline
.venv/bin/python -c "from ultralytics import YOLO; YOLO('models/yolov8n.pt').predict('/home/YOU/datasets/VisDrone/images/val', save=True, conf=0.3, project='/tmp/cmp', name='coco')"
```

Then compare `/tmp/cmp/coco/` against `/tmp/cmp/trained/` on the same filenames. No VisDrone
dataset locally? Any aerial clip works — swap the path for a video file.

To measure accuracy instead of eyeballing it:

```bash
.venv/bin/python -m tools.benchmark accuracy intruder --data VisDrone.yaml
```

---

## Licensing

Ultralytics YOLOv8 is **AGPL-3.0**. These weights are derived from it, so receiving them
means you're taking on AGPL obligations if you redistribute or ship them inside a product.
VisDrone2019-DET is from Tianjin University (Zhu et al., IEEE TPAMI 2022); MBDD2025 is
CC BY 4.0 (Zha et al., *Scientific Data*, 2025).
