#!/bin/bash
# 把 /app/ 中转页同步进 nginx 的静态根目录。
#
# deploy/frontend 在前端发版时会被整目录替换（旁边那些 frontend.previous-* 就是历史），
# 中转页放在里面会被一起冲掉。所以源文件常驻在 deploy/app-relay/，
# 每次前端发版之后跑一次这个脚本补回去即可。
#
#   bash /opt/avalin/riji-backend/deploy/app-relay/sync.sh
#
# 只是拷文件，不需要 reload nginx（location ^~ /app/ 的规则在 default.conf 里）。
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/opt/avalin/riji-backend/deploy/frontend/app

mkdir -p "$DEST"
cp -f "$SRC"/*.html "$DEST"/
ls -1 "$DEST"
echo "SYNC_OK -> $DEST"
