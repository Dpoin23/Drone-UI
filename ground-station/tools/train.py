"""Train the YOLOv8n detectors and install the weights where the ground station looks for them.

    # Intruder detection on VisDrone (Ultralytics downloads and converts it, about 2.3 GB)
    .venv/bin/python -m tools.train intruder --epochs 100 --device 0

    # Maintenance detection on MBDD2025 (run tools/prepare_mbdd2025.py first)
    .venv/bin/python -m tools.train maintenance --data datasets/mbdd2025/mbdd2025.yaml --device 0

    # Continue an interrupted run from runs/<name>/weights/last.pt
    .venv/bin/python -m tools.train intruder --resume --device 0

Training needs a GPU to finish in reasonable time; ``--device cpu`` works for a smoke test with
``--epochs 1 --fraction 0.01 --name smoke-intruder --no-install``.
"""

import argparse
import shutil
from pathlib import Path

from app.config import GROUND_STATION_DIR, MODELS_DIR

TASKS = {
    "intruder": {"data": "VisDrone.yaml", "output": "yolov8n-visdrone.pt"},
    "maintenance": {"data": "datasets/mbdd2025/mbdd2025.yaml", "output": "yolov8n-mbdd2025.pt"},
}
RUNS_DIR = GROUND_STATION_DIR / "runs"


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
    parser.add_argument("--name", help="Run folder under runs/ (defaults to the task name)")
    parser.add_argument("--resume", action="store_true",
                        help="Continue runs/<name>/weights/last.pt if it exists, otherwise start a new run")
    parser.add_argument("--no-install", action="store_true", help="Don't copy the best weights into models/")
    args = parser.parse_args()

    from ultralytics import YOLO

    task = TASKS[args.task]
    name = args.name or args.task
    weights_dir = RUNS_DIR / name / "weights"
    last = weights_dir / "last.pt"
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    if args.resume and last.is_file():
        model = YOLO(str(last))
        ckpt = model.ckpt or {}
        if ckpt.get("epoch", -1) >= 0 and ckpt.get("optimizer") is not None:
            print(f"Resuming {last} after epoch {ckpt['epoch'] + 1}")
            # On resume Ultralytics keeps the checkpoint's epochs/imgsz/data; only these can change.
            overrides = {"device": args.device, "workers": args.workers}
            model.train(resume=True, **{k: v for k, v in overrides.items() if v is not None})
            best = Path(model.trainer.best)
        else:
            # A finished run's last.pt has no optimizer state; resuming it would silently start over.
            print(f"{RUNS_DIR / name} already finished training; using its best weights")
            best = weights_dir / "best.pt"
    else:
        if args.resume:
            print(f"No checkpoint at {last}; starting a new run")
        model = YOLO(args.base)
        model.train(
            data=args.data or task["data"],
            epochs=args.epochs,
            imgsz=args.imgsz,
            batch=args.batch,
            device=args.device,
            fraction=args.fraction,
            workers=args.workers,
            project=str(RUNS_DIR),
            name=name,
            exist_ok=True,
        )
        best = Path(model.trainer.best)

    if not best.is_file():
        raise SystemExit(f"No best weights at {best}")
    if args.no_install:
        print(f"Trained {best} (not installed)")
        return
    dest = MODELS_DIR / task["output"]
    shutil.copy2(best, dest)
    print(f"Installed {best} as {dest}. Restart processing in the UI to use it.")


if __name__ == "__main__":
    main()
