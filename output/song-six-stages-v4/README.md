# 滑动变祖器 · 宋系强度校准器

拖动滑杆，观察宋系强度从「小宋」进化到「宋祖」。静态页面 + 连续形变视频 + BGM 节奏动效。

## 文件

| 文件 | 说明 |
|------|------|
| `index.html` | 页面本体（样式、脚本全部内联，无构建依赖） |
| `evolution.mp4` | 六阶段形变视频（密集关键帧，支持流畅拖动定位） |
| `bgm.m4a` | 背景音乐（循环播放） |
| `node_times.json` | 六个阶段节点对应的视频时间点（已内联进页面） |
| `bgm_energy.json` | BGM 能量包络（已内联进页面，驱动节奏动效） |
| `Caddyfile` / `docker-compose.yml` / `deploy.sh` | 部署配置与一键部署脚本 |

## 一键部署

```bash
git clone https://github.com/BartLiu0820/song_slider.git
cd song_slider/output/song-six-stages-v4
bash deploy.sh
```

脚本自动选择 Docker Compose（推荐）或本机 Caddy，部署后访问 `http://<服务器IP>/`。

## 部署要求

- 静态托管即可，但**必须支持 Range 请求**（视频拖动定位依赖它，Caddy/Nginx/对象存储/CDN 均支持）。
- 不要用 `python -m http.server`，它不支持 Range，视频会无法拖动。
- 有域名时编辑 `Caddyfile` 底部注释段，把域名填上即可自动启用 HTTPS。

## 验证

```bash
curl -sI -H "Range: bytes=0-1023" http://<服务器IP>/evolution.mp4
# 返回 HTTP 206 Partial Content 即正常
```
