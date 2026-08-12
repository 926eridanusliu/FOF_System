#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_DIR="$APP_DIR/.runtime-backend"
VENV_DIR="$RUNTIME_DIR/venv"

command -v python3 >/dev/null 2>&1 || { echo "请先安装 Python 3.12 或更高版本。"; exit 1; }
mkdir -p "$RUNTIME_DIR" "$APP_DIR/data"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install -q -r "$APP_DIR/backend/requirements.txt"

export FOF_DATA_DIR="$APP_DIR/data"
export PUBLIC_FRONTEND_URL="${PUBLIC_FRONTEND_URL:-http://127.0.0.1:5173}"
export CORS_ORIGINS="${CORS_ORIGINS:-http://127.0.0.1:5173,http://localhost:5173}"

echo "后端即将启动：http://127.0.0.1:8000"
echo "接口文档：http://127.0.0.1:8000/docs；按 Ctrl+C 停止后端。"
cd "$APP_DIR/backend"
exec "$VENV_DIR/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
