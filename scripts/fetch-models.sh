#!/usr/bin/env bash
# Ensure trained vision weights are present in ground-station/models/.
# The fine-tuned checkpoints ship in the repo. This script is for replacing
# them from a models-* GitHub Release (newer training run), or for clones
# that somehow lost the files.
#
# Usage:
#   scripts/fetch-models.sh                 # no-op if both files already exist
#   scripts/fetch-models.sh --force         # re-download newest models-* release
#   scripts/fetch-models.sh models-YYYYMMDD-HHMM
set -euo pipefail

FORCE=0
TAG=""
for arg in "$@"; do
  case "$arg" in
    -h|--help)
      echo "Usage: scripts/fetch-models.sh [--force] [models-YYYYMMDD-HHMM]"
      exit 0
      ;;
    --force) FORCE=1 ;;
    *) TAG="$arg" ;;
  esac
done

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/ground-station/models"
REPO="${DRONE_UI_REPO:-$(git -C "$ROOT" remote get-url origin | sed -E 's#^(git@github\.com:|https://github\.com/)##; s#\.git$##')}"
mkdir -p "$DEST"

NAMES=(yolov8n-visdrone.pt yolov8n-mbdd2025.pt)
missing=()
for name in "${NAMES[@]}"; do
  if [[ ! -f "$DEST/$name" ]]; then
    missing+=("$name")
  fi
done

if [[ $FORCE -eq 0 && -z "$TAG" && ${#missing[@]} -eq 0 ]]; then
  echo "Trained weights already present in $DEST (shipped with the repo)."
  echo "Pass --force or a release tag to replace them from a GitHub Release."
  exit 0
fi

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
  if [[ ${#missing[@]} -eq 0 ]]; then
    echo "No models-* GitHub Release found on github.com/$REPO; keeping the in-repo weights in $DEST." >&2
    exit 0
  fi
  echo "No published weights found on github.com/$REPO${TAG:+ under $TAG}, and these files are missing: ${missing[*]}." >&2
  echo "Train with scripts/train-models.sh, or unpack a drone-ui-weights-*.tar.gz into ground-station/." >&2
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
