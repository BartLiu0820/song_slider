#!/usr/bin/env bash
# 滑动变祖器 一键部署
# 用法：git clone <repo> && cd song_slider/output/song-six-stages-v4 && bash deploy.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "==> 检查部署方式…"

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "==> 使用 Docker Compose 部署（Caddy）"
  docker compose up -d
  echo "==> 完成，访问 http://<服务器IP>/ 即可"

elif command -v caddy >/dev/null 2>&1; then
  echo "==> 使用本机 Caddy 部署"
  # 后台运行；停止方式：pkill -f 'caddy run'
  nohup caddy run --config ./Caddyfile --adapter caddyfile >/var/log/song-slider.log 2>&1 &
  echo "==> 完成，访问 http://<服务器IP>/ 即可"

else
  cat <<'EOF'
未找到 docker 或 caddy，请先安装其一：

  Docker（推荐）：
    curl -fsSL https://get.docker.com | bash
    然后重新运行 ./deploy.sh

  或 Caddy（单二进制）：
    apt install -y caddy        # Debian/Ubuntu
    yum install -y caddy         # CentOS（需 copr）
    然后重新运行 ./deploy.sh

注意：不要用 python -m http.server 部署，它不支持 Range 请求，
视频拖动定位会失效。
EOF
  exit 1
fi

# 验证 Range 支持（视频拖动依赖它）
sleep 2
if curl -sI -H "Range: bytes=0-1023" http://127.0.0.1/evolution.mp4 | grep -q "206"; then
  echo "==> Range 请求验证通过（HTTP 206）"
else
  echo "!!  Range 请求验证失败，视频拖动可能不工作，请检查服务日志"
fi
