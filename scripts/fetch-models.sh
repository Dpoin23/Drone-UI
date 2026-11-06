#!/usr/bin/env bash
# Download the trained vision weights published by scripts/train-models.sh into ground-station/models/.
# Takes the newest models-* GitHub Release that has each file, or the release named as the argument.
set -euo pipefail

if [[ "${1:-}" == -h || "${1:-}" == --help ]]; then
  echo "Usage: scripts/fetch-models.sh [models-YYYYMMDD-HHMM]"
  exit 0
fi
TAG="${1:-}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/ground-station/models"
REPO="${DRONE_UI_REPO:-$(git -C "$ROOT" remote get-url origin | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')}"
mkdir -p "$DEST"

# gh works for private repos too; plain curl is enough while the repo is public.
use_gh=0
if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  use_gh=1
  releases=$(gh api "repos/$REPO/releases?per_page=100")
else
  releases=$(curl -fsSL "https://api.github.com/repos/$REPO/releases?per_page=100")
fi

picks=$(python3 -c '
import json, sys
tag = sys.argv[1]
releases = [r for r in json.load(sys.stdin) if (r["tag_name"] == tag if tag else r["tag_name"].startswith("models-"))]
releases.sort(key=lambda r: r["created_at"], reverse=True)
for name in ("yolov8n-visdrone.pt", "yolov8n-mbdd2025.pt"):
    for r in releases:
        asset = next((a for a in r["assets"] if a["name"] == name), None)
        if asset:
            print(name, r["tag_name"], asset["browser_download_url"])
            break
' "$TAG" <<<"$releases")

if [[ -z "$picks" ]]; then
  echo "No published weights found on github.com/$REPO${TAG:+ under $TAG}. Train them with scripts/train-models.sh." >&2
  exit 1
fi

while read -r name tag url; do
  echo "Downloading $name from $tag"
  part="$DEST/.$name.part"
  if [[ $use_gh == 1 ]]; then
    gh release download "$tag" --repo "$REPO" --pattern "$name" --output "$part" --clobber
  else
    curl -fL --progress-bar -o "$part" "$url"
  fi
  mv "$part" "$DEST/$name"
done <<<"$picks"

echo "Installed into $DEST. Restart image processing in the UI (or the backend) to use them."
