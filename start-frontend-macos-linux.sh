#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$APP_DIR/frontend"

command -v npm >/dev/null 2>&1 || { echo "请先安装 Node.js 20 或更高版本。"; exit 1; }
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  cd "$FRONTEND_DIR"
  npm ci
fi

echo "前端即将启动：http://127.0.0.1:5173"
echo "请同时启动后端；按 Ctrl+C 停止前端。"
cd "$FRONTEND_DIR"
exec npm run dev -- --host 127.0.0.1
