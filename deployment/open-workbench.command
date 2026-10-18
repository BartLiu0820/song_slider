#!/bin/zsh
set -eu
task_socket="$HOME/.ssh/song-deploy-tunnel.sock"
if ! ssh -S "$task_socket" -O check songhuang-server >/dev/null 2>&1; then
  ssh -M -S "$task_socket" -fN -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
    -L 127.0.0.1:18000:127.0.0.1:8000 \
    -L 127.0.0.1:19100:127.0.0.1:9100 \
    -L 127.0.0.1:19180:127.0.0.1:80 songhuang-server
fi
open http://127.0.0.1:19100
