#!/bin/bash
# A videós és hangos futtatókörnyezet elkészítése (Clip Farm, Élő adás figyelő, Shorts): Python 3.12, yt-dlp, MLX-Whisper,
# arcfelismerés, ffmpeg, Node és a feliratozó (Remotion). Egyszer kell, utána az ORBIT használja. Újrafuttatható: ami kész, azt kihagyja.
# Apple Silicon (M-sorozatú) Mac kell, kb. 6 GB hely és internet; 10-20 perc.
set -euo pipefail
cd "$(dirname "$0")"
DATA="$HOME/Library/Application Support/Orbit"
RT="$DATA/media-runtime"
DEPS="$DATA/remotion-deps"
NODE_VERSION="v24.22.3"

if [ "$(uname -m)" != "arm64" ]; then echo "A videógyártáshoz Apple Silicon (M-sorozatú) Mac kell. A többi ORBIT-funkció így is működik."; exit 2; fi

WANT="$(shasum -a 256 media-requirements.txt | cut -d' ' -f1)"
ready() {
  [ "$(cat "$DATA/media-requirements.sha" 2>/dev/null)" = "$WANT" ] && \
  [ -x "$RT/bin/python" ] && "$RT/bin/python" -c "import yt_dlp, mlx_whisper, cv2, imageio_ffmpeg" 2>/dev/null \
    && [ -x "$RT/bin/node" ] && [ -f "$DATA/models/whisper-large-v3-turbo/weights.safetensors" ] \
    && [ -f "$DATA/models/face_detection_yunet_2023mar.onnx" ] && [ -d "$DEPS/node_modules" ]
}
if ready && [ "${1:-}" != "--force" ]; then echo "✓ A videós futtatókörnyezet már kész."; exit 0; fi

mkdir -p "$DATA/tools" "$DATA/models"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

echo "▸ 1/6 uv (Python-kezelő) letöltése…"
if [ ! -x "$DATA/tools/uv" ]; then
  curl -fsSL "https://github.com/astral-sh/uv/releases/latest/download/uv-aarch64-apple-darwin.tar.gz" -o "$TMP/uv.tgz"
  tar -xzf "$TMP/uv.tgz" -C "$TMP"
  cp "$TMP"/uv-*/uv "$DATA/tools/uv"; chmod 755 "$DATA/tools/uv"
fi
UV="$DATA/tools/uv"

echo "▸ 2/6 Python 3.12 és a csomagok (ez a leghosszabb lépés)…"
"$UV" venv --python 3.12 --seed "$RT"
"$UV" pip install --python "$RT/bin/python" -r media-requirements.txt

echo "▸ 3/6 Node $NODE_VERSION…"
if [ ! -x "$DATA/node-runtime/bin/node" ]; then
  curl -fsSL "https://nodejs.org/dist/$NODE_VERSION/node-$NODE_VERSION-darwin-arm64.tar.gz" -o "$TMP/node.tgz"
  mkdir -p "$DATA/node-runtime"; tar -xzf "$TMP/node.tgz" -C "$DATA/node-runtime" --strip-components=1
fi
ln -sfn "$DATA/node-runtime/bin/node" "$RT/bin/node"

echo "▸ 4/6 ffmpeg…"
FF="$("$RT/bin/python" -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
ln -sfn "$FF" "$RT/bin/ffmpeg"

echo "▸ 5/6 Beszéd- és arcfelismerő modellek (kb. 1,7 GB)…"
"$RT/bin/python" orbit_app/download_media_models.py >/dev/null

echo "▸ 6/6 Feliratozó (Remotion)…"
# The Remotion packages live in the data folder, shared by every copy of the installer (also the update folders), and are renewed only when package.json changes.
mkdir -p "$DEPS"
PKG="$(shasum -a 256 orbit_app/remotion/package.json | cut -d' ' -f1)"
if [ "$(cat "$DEPS/package.sha" 2>/dev/null)" != "$PKG" ] || [ ! -d "$DEPS/node_modules" ]; then
  cp orbit_app/remotion/package.json "$DEPS/package.json"
  ( cd "$DEPS" && PATH="$DATA/node-runtime/bin:$PATH" npm install --no-audit --no-fund ) && echo "$PKG" > "$DEPS/package.sha" \
    || echo "ℹ︎ A feliratozó csomagjai nem települtek; az ORBIT ilyenkor egyszerűbb (ffmpeg) feliratozással dolgozik."
fi
ln -sfn "$DEPS/node_modules" orbit_app/remotion/node_modules
( cd orbit_app/remotion && PATH="$DATA/node-runtime/bin:$PATH" node build.cjs ) || echo "ℹ︎ A feliratozó nem készült el; az ORBIT ilyenkor egyszerűbb (ffmpeg) feliratozással dolgozik."

echo "$WANT" > "$DATA/media-requirements.sha"
echo "✓ Kész: a videós futtatókörnyezet használható."
