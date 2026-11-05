"""Convert MBDD2025 into an Ultralytics dataset with a 70/20/10 train/val/test split.

MBDD2025 (https://zenodo.org/records/15622584) ships ``JPEGImages/`` with Pascal VOC XML in
``Annotations/``. Labels are converted from the XML rather than taken from its ``Labels/`` folder
so the class order is explicit.

    .venv/bin/python -m tools.prepare_mbdd2025 /path/to/MBDD2025 --out datasets/mbdd2025
"""

import argparse
import random
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CLASSES = ["crack", "leakage", "abscission", "corrosion", "bulge"]
ALIASES = {"bulging": "bulge", "leak": "leakage", "cracks": "crack", "rust": "corrosion"}
SPLITS = (("train", 0.7), ("val", 0.2), ("test", 0.1))
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def _find_dir(root: Path, name: str) -> Path:
    matches = [p for p in root.rglob(name) if p.is_dir()]
    if not matches:
        sys.exit(f"No {name}/ folder under {root}")
    return matches[0]


def voc_to_yolo(xml_path: Path) -> tuple[list[str], set[str]]:
    root = ET.parse(xml_path).getroot()
    size = root.find("size")
    w = float(size.findtext("width", "0"))
    h = float(size.findtext("height", "0"))
    lines, unknown = [], set()
    if w <= 0 or h <= 0:
        return lines, unknown
    for obj in root.iter("object"):
        name = (obj.findtext("name") or "").strip().lower()
        name = ALIASES.get(name, name)
        if name not in CLASSES:
            unknown.add(name)
            continue
        box = obj.find("bndbox")
        x1, y1, x2, y2 = (float(box.findtext(k, "0")) for k in ("xmin", "ymin", "xmax", "ymax"))
        x1, x2 = max(0.0, min(x1, x2)), min(w, max(x1, x2))
        y1, y2 = max(0.0, min(y1, y2)), min(h, max(y1, y2))
        if x2 - x1 < 1 or y2 - y1 < 1:
            continue
        cx, cy, bw, bh = (x1 + x2) / 2 / w, (y1 + y2) / 2 / h, (x2 - x1) / w, (y2 - y1) / h
        lines.append(f"{CLASSES.index(name)} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
    return lines, unknown


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("source", type=Path, help="Extracted MBDD2025 folder")
    parser.add_argument("--out", type=Path, default=Path("datasets/mbdd2025"))
    parser.add_argument("--seed", type=int, default=2025)
    parser.add_argument("--link", action="store_true", help="Symlink images instead of copying them")
    args = parser.parse_args()

    images_dir = _find_dir(args.source, "JPEGImages")
    annotations_dir = _find_dir(args.source, "Annotations")
    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    random.Random(args.seed).shuffle(images)

    unknown: set[str] = set()
    counts: dict[str, int] = {}
    start = 0
    for i, (split, fraction) in enumerate(SPLITS):
        end = len(images) if i == len(SPLITS) - 1 else start + round(len(images) * fraction)
        img_out, lbl_out = args.out / "images" / split, args.out / "labels" / split
        img_out.mkdir(parents=True, exist_ok=True)
        lbl_out.mkdir(parents=True, exist_ok=True)
        for image in images[start:end]:
            xml = annotations_dir / f"{image.stem}.xml"
            lines, bad = voc_to_yolo(xml) if xml.is_file() else ([], set())
            unknown |= bad
            dest = img_out / image.name
            if not dest.exists():
                if args.link:
                    dest.symlink_to(image.resolve())
                else:
                    shutil.copy2(image, dest)
            (lbl_out / f"{image.stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
        counts[split] = end - start
        start = end

    yaml_path = args.out / "mbdd2025.yaml"
    names = "\n".join(f"  {i}: {n}" for i, n in enumerate(CLASSES))
    yaml_path.write_text(
        f"# MBDD2025 building defects, converted by tools/prepare_mbdd2025.py\n"
        f"path: {args.out.resolve()}\ntrain: images/train\nval: images/val\ntest: images/test\n"
        f"names:\n{names}\n"
    )
    print(f"Wrote {yaml_path}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    if unknown:
        print(f"Skipped unknown classes: {', '.join(sorted(unknown))}")


if __name__ == "__main__":
    main()
