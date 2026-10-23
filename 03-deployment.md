# 部署实施与验收 · 2026-10-18

> 2026-10-21 更新：公网阻塞已解除，工作台此前因发布开关关闭返回 503，现已通过现有激活脚本开启。公网 HTTPS、真实登录、Secure Cookie 和两个示例预览验收通过。入口：<https://deploy.greatsong.online/>。以下为 10 月 18 日实施记录。

## 结论

个人 AI 部署工作台已安装并通过 SSH 通道运行。DeepSeek 已真实调用；静态网页和 Flask 后端已完成识别、构建、健康检查及浏览器访问。公网子域名发布尚未完成：阿里云返回备案拦截，用户确认域名未备案。

入口与操作步骤见 [使用说明](deployment/README.md)。账号密码保存在本机受限文件，未写入仓库或本文。

## 已交付

- 展示页顶栏增加低调的“管理”入口，当前指向本机工作台。
- 独立账号密码登录的中文工作台，仓库输入、默认分支识别、应用目录选择、AI 部署方案、缺失配置提示、部署和重试、项目状态及预览链接。
- Coolify 4.4.6 管理后台，应用构建、串行队列、日志和容器生命周期管理。
- DeepSeek Flash 常驻 API 执行器，以 systemd 非 root 服务运行。模型不接收密钥或服务器命令执行权限。
- GitHub 官方源码包 → 完整 Git tree SHA 校验 → 内网只读快照仓库 → 容器构建的发布链路。工作台保留上游提交；引擎使用对应的快照导入提交。
- Mac 双击启动/关闭 SSH 通道的脚本；`项目名.localhost:19180` 本机预览。
- 原展示页、Caddy 证书与视频 Range 支持保留；站点文件、入口配置、平台数据库与配置已备份。

## 真实项目结果

| 项目 | 识别结果 | 最终验证 |
|---|---|---|
| [MDN 静态示例](https://github.com/mdn/beginner-html-site-styled) | static；根目录；端口 80 | 引擎 finished，容器 running:healthy，HTML/CSS/PNG 请求通过，浏览器显示 Mozilla is cool |
| [Docker 官方 Flask 示例](https://github.com/docker/awesome-compose/tree/master/flask) | `/flask/app`；Dockerfile 的 builder 阶段；端口 8000 | 引擎 finished，容器 running:healthy，浏览器返回 Hello World! |
| [Flask 官方 Flaskr](https://github.com/pallets/flask/tree/3.1.2/examples/tutorial) | Python/Nixpacks；SQLite 文件持久化与首次 init-db | 正确停在 needs_configuration；尝试直接部署被接口拒绝。本轮未自动创建其数据库，前一轮手工部署与数据持久化验证见 02-validation.md |

预览地址（需先打开 SSH 通道）：

- <http://ai-static-example.localhost:19180/>
- <http://ai-flask-example.localhost:19180/>

源提交分别为 `6c7a360ddb4a0d75be06044bf8a914f260ff10c7` 与 `30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562`。源码包 SHA-256、上游 tree SHA、导入 commit 和部署 UUID 保存在 [验收证据](deployment/acceptance-20261018.json)。

最后一次 Flask 引擎部署记录从创建到完成约 23 秒，使用已下载源码与镜像缓存；静态部署记录约 105 秒，包含排队。这不代表任意新项目的首次耗时。

## 检查

- 12 项针对性单元测试通过：仓库地址限制、路径穿越、虚构 Dockerfile、数据库/密钥门槛、端口类型、登录/CSRF、源码包路径/链接/大小限制、Git tree 不一致、LFS 指针、重试旧任务状态隔离。
- 6 项在线验收通过：工作台登录、后端 HTTP 200、静态 HTML、CSS/PNG、数据库配置拦截、两个引擎部署完成且容器健康。
- Coolify 账号密码登录后进入 Dashboard。
- 原展示页服务器内 HTTPS 200；视频 Range 返回 206 和 1024 字节。
- 内置浏览器分别打开静态与后端实际预览地址验证内容；工作台登录页也已检查。
- 额外从空白项目新建了一次静态应用，完成 AI 识别、自动创建资源、部署及 HTTP 200 验证；该一次性应用已清理，记录见 `deployment/fresh-acceptance.json`。
- 验收时服务器约 2,238 MiB 可用内存、40GB 可用磁盘；两个示例应用合计约 35MiB 内存。此为当时运行状态，不是构建峰值。

## 已处理的问题

1. Docker Hub 直连不稳定：使用已验证镜像源及官方 GHCR/ECR，核对 nginx 官方摘要。
2. GitHub Git 连接多次超时：直连拉取曾成功，但重复 fetch 仍失败；最终采用官方源码包且核对完整文件树，避免依赖不稳定的 smart-HTTP 路径。
3. Python 包下载超时：构建使用可达的阿里云 HTTPS PyPI 镜像和更长超时。
4. Alpine 容器对 localhost 的 IPv6 解析使健康检查失败：固定检查 `127.0.0.1` 和识别出的服务端口。
5. 已有 Coolify 应用从 GitHub source 改为内网 Git URL 后保留旧 provider：本轮迁移的两个应用已清理旧 provider 关联；工作台新建流程直接创建内网快照来源。
6. Coolify 创建 API 的 URL 解析器不接受 git://：内部只读快照改用 HTTP Git 传输，关闭浅克隆；仅在 Docker 网桥监听，仍通过 Git tree 校验原始源码。

失败部署日志保留在 Deployment Lab / AI Deploy 中，未把中间失败计为成功。

## 尚未完成的范围

公网 HTTPS/域名入口受未备案阻塞，当前只交付 SSH 私人访问路径。私有仓库、数据库自动初始化、多服务编排、任意框架自动修复仍需后续实现；本版不能保证所有 Git 项目零配置部署。详细限制和恢复步骤见使用说明。
