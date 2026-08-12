#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$APP_DIR/.runtime"
VENV_DIR="$RUNTIME_DIR/venv"

command -v python3 >/dev/null 2>&1 || { echo "请先安装 Python 3.12 或更高版本。"; exit 1; }
mkdir -p "$RUNTIME_DIR" "$APP_DIR/data"

if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install -q -r "$APP_DIR/backend/requirements.txt"

export FOF_DATA_DIR="$APP_DIR/data"
export PUBLIC_FRONTEND_URL="${PUBLIC_FRONTEND_URL:-http://127.0.0.1:8000}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:8000,http://localhost:8000}"
export FOF_HOST="${FOF_HOST:-127.0.0.1}"

echo "FOF 系统即将启动：$PUBLIC_FRONTEND_URL"
echo "按 Ctrl+C 停止系统。"
cd "$APP_DIR/backend"
exec "$VENV_DIR/bin/python" -m uvicorn app.main:app --host "$FOF_HOST" --port 8000
