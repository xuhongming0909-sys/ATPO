#!/bin/bash
# AI-SUMMARY: 服务器端手动同步脚本——从 bare 仓库拉取最新 main 并刷新依赖（正常由 post-receive 钩子自动完成，本脚本兜底）
set -euo pipefail
APP=/home/ubuntu/auto-ipo
GIT_DIR=/home/ubuntu/git/auto-ipo.git
git --work-tree="$APP" --git-dir="$GIT_DIR" checkout -f main
cd "$APP"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q -r requirements.txt
echo "synced: $(git --git-dir="$GIT_DIR" log --oneline -1)"
