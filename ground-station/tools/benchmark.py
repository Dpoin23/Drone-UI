"""Benchmark the detectors and the live pipeline.

    # Accuracy on a dataset's validation split: mAP50, mAP50-95, precision, recall, per-image speed
    .venv/bin/python -m tools.benchmark accuracy intruder --data VisDrone.yaml
    .venv/bin/python -m tools.benchmark accuracy maintenance --data datasets/mbdd2025/mbdd2025.yaml

    # Raw detector speed on frames from a video or stream: inference latency and max FPS
    .venv/bin/python -m tools.benchmark speed intruder --source flight.mp4 --frames 200

    # The full pipeline as it runs in flight: capture, latest-frame buffer, both workers, tracking.
    # Reports achieved FPS vs target, end-to-end latency, skipped frames, and capture rate.
    .venv/bin/python -m tools.benchmark pipeline --source rtsp://drone.local:8554/cam --mode inspection --seconds 60

Add ``--json results.json`` to any command to save the numbers.
"""

import argparse
import json
import statistics
import tempfile
import time
from pathlib import Path

from app.config import load_settings
from app.vision.detectors import intruder_weights, load_detector, maintenance_weights


def _weights(stream: str, settings) -> Path:
    path = intruder_weights(settings) if stream == "intruder" else maintenance_weights(settings)
    if path is None:
        raise SystemExit("No maintenance model yet. Train one with tools/train.py maintenance.")
    return path


def accuracy(args, settings) -> dict:
    from ultralytics import YOLO

    weights = _weights(args.stream, settings)
    model = YOLO(str(weights))
    metrics = model.val(data=args.data, imgsz=settings.vision_imgsz, split=args.split, device=args.device or None,
                        plots=False, verbose=False)
    box = metrics.box
    return {
        "model": weights.name,
        "data": args.data,
        "split": args.split,
        "mAP50": round(float(box.map50), 4),
        "mAP50_95": round(float(box.map), 4),
        "precision": round(float(box.mp), 4),
        "recall": round(float(box.mr), 4),
        "per_class_mAP50_95": {name: round(float(box.maps[i]), 4) for i, name in metrics.names.items()},
        "speed_ms": {k: round(v, 2) for k, v in metrics.speed.items()},
    }


def speed(args, settings) -> dict:
    import cv2

    from app.vision.frames import LatestFrameBuffer

    detector = load_detector(args.stream, settings)
    cap = cv2.VideoCapture(args.source)
    if not cap.isOpened():
        raise SystemExit(f"Couldn't open {args.source}")
    buffer = LatestFrameBuffer()
    times = []
    while len(times) < args.frames:
        ok, image = cap.read()
        if not ok:
            break
        frame = buffer.put(ts=time.time(), epoch=1, image=image)
        started = time.perf_counter()
        detector.detect(frame)
        times.append((time.perf_counter() - started) * 1000)
    cap.release()
    if not times:
        raise SystemExit("No frames read")
    times.sort()
    return {
        "detector": detector.name,
        "device": detector.device,
        "imgsz": settings.vision_imgsz,
        "frames": len(times),
        "frame_size": [frame.width, frame.height],
        "latency_ms_mean": round(statistics.fmean(times), 1),
        "latency_ms_p50": round(times[len(times) // 2], 1),
        "latency_ms_p95": round(times[min(len(times) - 1, int(len(times) * 0.95))], 1),
        "max_fps": round(1000 / statistics.fmean(times), 1),
    }


def pipeline(args, settings) -> dict:
    from dataclasses import replace

    from app.storage.db import init_db
    from app.vision.modes import merged_rates
    from app.vision.session import SessionConfig, VisionManager
    from app.vision.sources import CaptureTarget

    with tempfile.TemporaryDirectory() as tmp:
        settings = replace(settings, db_path=Path(tmp) / "bench.db", uploads_dir=Path(tmp) / "uploads")
        init_db(settings.db_path)
        manager = VisionManager(settings)
        source = args.source
        kind = "file" if Path(source).is_file() else "stream"
        rates = merged_rates(None)
        if args.intruder_fps is not None:
            rates[args.mode]["intruder"] = args.intruder_fps
        if args.maintenance_fps is not None:
            rates[args.mode]["maintenance"] = args.maintenance_fps
        config = SessionConfig(
            mode=args.mode, rates=rates, auto_issues=False, follow_telemetry=False, frame_source="server",
            transport="benchmark", source_label=source, capture=CaptureTarget(kind, source, source),
        )
        session = manager.start(0, config)
        try:
            # Let the models load and the first frames arrive before measuring.
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline and session.buffer.frames_in == 0:
                time.sleep(0.2)
            time.sleep(5)
            session.stats()
            time.sleep(args.seconds)
            stats = session.stats()
        finally:
            manager.shutdown()
    return {
        "source": source,
        "mode": args.mode,
        "seconds": args.seconds,
        "frame_size": stats["frame_size"],
        "capture_fps": stats["capture_fps"],
        "frames_in": stats["frames_in"],
        "frames_overwritten": stats["frames_overwritten"],
        "workers": stats["workers"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", type=Path, help="Also write results to this file")
    sub = parser.add_subparsers(dest="command", required=True)

    acc = sub.add_parser("accuracy", help="mAP, precision, recall on a dataset split")
    acc.add_argument("stream", choices=("intruder", "maintenance"))
    acc.add_argument("--data", required=True)
    acc.add_argument("--split", default="val")
    acc.add_argument("--device")

    spd = sub.add_parser("speed", help="Detector latency on frames from a video or stream")
    spd.add_argument("stream", choices=("intruder", "maintenance"))
    spd.add_argument("--source", required=True)
    spd.add_argument("--frames", type=int, default=200)

    pipe = sub.add_parser("pipeline", help="Full live pipeline on a video file or stream URL")
    pipe.add_argument("--source", required=True)
    pipe.add_argument("--mode", default="inspection",
                      choices=("takeoff_landing", "transit", "patrol", "inspection", "return_to_base"))
    pipe.add_argument("--seconds", type=float, default=30)
    pipe.add_argument("--intruder-fps", type=float)
    pipe.add_argument("--maintenance-fps", type=float)

    args = parser.parse_args()
    settings = load_settings()
    result = {"accuracy": accuracy, "speed": speed, "pipeline": pipeline}[args.command](args, settings)
    text = json.dumps(result, indent=2)
    print(text)
    if args.json:
        args.json.write_text(text + "\n")


if __name__ == "__main__":
    main()
