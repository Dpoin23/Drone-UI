"""Ground-side computer vision: latest-frame buffer, YOLO workers, tracking, and detection reporting.

Heavy dependencies (OpenCV, NumPy, Ultralytics/PyTorch) come from ``requirements-vision.txt`` and
are imported lazily, so the rest of the ground station runs without them.
"""
