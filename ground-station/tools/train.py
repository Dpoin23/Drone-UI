"""Train the YOLOv8n detectors and install the weights where the ground station looks for them.

    # Intruder detection on VisDrone (Ultralytics downloads and converts it, about 2.3 GB)
    .venv/bin/python -m tools.train intruder --epochs 100 --device 0

    # Maintenance detection on MBDD2025 (run tools/prepare_mbdd2025.py first)
    .venv/bin/python -m tools.train maintenance --data datasets/mbdd2025/mbdd2025.yaml --device 0

Training needs a GPU to finish in reasonable time; ``--device cpu`` works for a smoke test with
``--epochs 1 --fraction 0.01``.
"""

import argparse
import shutil
from pathlib import Path

from app.config import GROUND_STATION_DIR, MODELS_DIR

TASKS = {
    "intruder": {"data": "VisDrone.yaml", "output": "yolov8n-visdrone.pt"},
    "maintenance": {"data": "datasets/mbdd2025/mbdd2025.yaml", "output": "yolov8n-mbdd2025.pt"},
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("task", choices=TASKS)
    parser.add_argument("--data", help="Dataset YAML (defaults per task)")
    parser.add_argument("--base", default=str(MODELS_DIR / "yolov8n.pt"), help="Starting weights")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=16)
    parser.add_argument("--device", default=None, help="e.g. 0, cpu, mps")
    parser.add_argument("--fraction", type=float, default=1.0, help="Train on a fraction of the dataset")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    from ultralytics import YOLO

    task = TASKS[args.task]
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    model = YOLO(args.base)
    model.train(
        data=args.data or task["data"],
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        fraction=args.fraction,
        workers=args.workers,
        project=str(GROUND_STATION_DIR / "runs"),
        name=args.task,
        exist_ok=True,
    )
    best = Path(model.trainer.best)
    dest = MODELS_DIR / task["output"]
    shutil.copy2(best, dest)
    print(f"Installed {best} as {dest}. Restart processing in the UI to use it.")


if __name__ == "__main__":
    main()
