# 宋 · 个人部署工作台

## 本机使用

1. 双击 `open-workbench.command`，建立 SSH 通道并打开工作台。
2. 工作台：<http://127.0.0.1:19100>；底层部署引擎：<http://127.0.0.1:18000>。
3. 账号 `admin@greatsong.online`。密码保存在本机 `~/.config/song-deploy/admin-credentials.json`，不要把该文件提交到 Git。
4. 输入公开 GitHub 仓库地址，分支留空会识别默认分支；单仓库多应用时填写应用目录。
5. 点击“识别项目”，查看 DeepSeek 给出的目录、端口、构建方式与缺失配置，再点击“按此方案部署”。
6. 部署成功后点击“打开本机预览”，地址形如 `http://项目名.localhost:19180`。这是 SSH 通道内的服务器应用，不是本机运行的应用。
7. 完成测试后可双击 `close-workbench.command` 关闭通道；服务器应用继续运行。

电脑重启、休眠或网络切换导致断开后，重新双击打开脚本即可。不需要把 DeepSeek Key 再填入网页。

## 当前范围

- 常驻 Python 执行器调用 DeepSeek API，不在 4GB 服务器内加载模型权重。
- AI 通过 GitHub API 读取固定提交的文件树和最多 12 个配置/入口文件；公开仓库的选定文件会发送到 DeepSeek。
- 支持生成 static、已有 Dockerfile、Nixpacks 三类方案。只提交经过字段与路径校验的部署设置，不把模型回复作为宿主机命令执行。
- 执行器通过 GitHub 官方 codeload 下载固定提交的源码包，重新计算 Git 文件树并与该提交的 tree SHA 核对。通过后导入服务器内部的只读 Git 快照仓库，Coolify 从这个仓库 clone 并构建。完整源文件树一致，但快照导入提交与上游历史提交不同；工作台始终显示上游提交，任务记录保留二者。
- Coolify 负责容器构建、健康检查、队列、日志和运行管理。构建并发为 1。
- 发现必需密钥、数据库或持久化需求时停在待配置状态。这些项目需在部署引擎补充配置；首版未实现全自动数据库初始化。
- 私有仓库、任意 Git 服务商、自动生成/修复 Dockerfile、多服务 Compose 自动编排不在本版自动流程内。
- 源码包上限 64MB，解压上限 256MB / 20,000 个文件；首版不支持 Git 子模块、LFS、符号链接。文件树校验不一致时停止，不悄悄换用其他代码。
- 本版一次识别固定一个提交；希望更新到新提交时重新识别并使用新项目名。已有任务“重新部署”仍部署原提交。
- GitHub 未认证 API 存在调用限额；当前没有保存 GitHub token。

## 公网状态

`deploy.greatsong.online` 和 `*.preview.greatsong.online` DNS 已解析到服务器。
但公网实测被阿里云返回的 `Non-compliance ICP Filing` 页面拦截；用户确认域名尚未备案。
因此公网入口与 HTTPS 证书未验收。当前工作台只监听 `127.0.0.1:9100`，通过 SSH 访问。
展示页顶部“管理”也指向本机工作台，需要先建立通道。

备案状态恢复后需要另做一次公网发布验收：确认 HTTP 请求到达服务器、配置工作台 HTTPS 反代与 Secure Cookie、将展示页入口切换到公网地址，再为应用启用 HTTPS。不能仅因为 DNS 正确就视为发布成功。

## 服务和文件

| 项目 | 位置 |
|---|---|
| SSH | `ssh songhuang-server` |
| AI 服务 | `systemctl status song-deploy-agent` |
| AI 代码 | `/opt/song-deploy/agent` |
| AI 配置与 Key | `/etc/song-deploy`，root / 专用服务组可读 |
| AI 任务记录 | `/var/lib/song-deploy` |
| 校验后的只读源码仓库 | `/var/lib/song-deploy/repos`，`song-deploy-git.service` 只监听 Docker 网桥 `172.21.0.1:9418` |
| Coolify Compose 与环境配置 | `/data/coolify/source` |
| 入口代理配置 | `/data/coolify/proxy/docker-compose.yml`，同时保存于 Coolify 数据库 |
| 展示页 | `/home/admin/song_slider/output/song-six-stages-v4` |
| 本机登录资料/API token | `~/.config/song-deploy` |
| 本机通道控制 socket | `~/.ssh/song-deploy-tunnel.sock` |

Coolify API token 本轮签发时设置了 90 天有效期。到期需在 Coolify 更新 token，并更新本机 `coolify-api-token` 与服务器 `agent.json`；不要把 token 填在仓库 URL 内。

## 网络适配

- Docker Hub 镜像通过已有服务器可用的 DaoCloud 公共镜像加速；对使用的 nginx 镜像核对了官方摘要。
- Coolify 主镜像来自官方 GHCR，数据库/Redis/Traefik 基础镜像来自官方 ECR。
- 构建辅助镜像 `song-deploy/coolify-helper:1.0.17` 基于官方镜像，增加 GitHub HTTPS 连接路线，并在固定提交已存在时跳过重复 fetch；仍校验 GitHub TLS 证书。固定节点 `140.82.114.3` 后续也出现不稳定，因此工作台已改用上面的官方源码包与内部快照链路。直接在 Coolify 新建 GitHub 项目仍可能受网络影响。
- Python 构建使用 `PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/` 和 120 秒下载超时。此设置是非敏感的构建变量。
- 直接 Git 拉取实测耗时数分钟且可能超时；工作台快照链路避开了该请求。首次镜像与依赖下载仍受网络影响，不能承诺所有项目秒级部署。

## 维护与恢复

- 登录失败先确认 SSH 通道是否仍连通，然后查看 `journalctl -u song-deploy-agent`。
- 应用失败在 Coolify 的项目部署日志查看；工作台不会把失败标为成功，也不自动反复修改仓库。
- 更新执行器可运行 `python3 deployment/install_agent.py`；会重启服务，应避开正在分析或提交的任务。
- 自动更新关闭，升级 Coolify 前应备份数据库、`/data/coolify/source/.env` 和 SSH key。数据库中的敏感配置依赖该 APP_KEY 解密。
- 展示页已保留 `index.before-deploy-20261018.html` 和 `docker-compose.before-deploy-20261018.yml`。入口代理保留 `docker-compose.before-public-20261018.yml`。
- 原 Caddy 仍持有展示页证书。Traefik 对主站 TLS 透传、对应用按域名路由；恢复旧 Compose 前必须先停止占用 80/443 的 `coolify-proxy`。
- 本轮数据库和配置备份位于 `/var/backups/song-deploy/20261018`，仅 root 可读。

实现依据：[Coolify 4.4.6 源码](https://github.com/coollabsio/coolify/tree/v4.4.6)、[DeepSeek 官方 API](https://api-docs.deepseek.com/)。

## 简化首页与项目访问权限（2026-10-18 更新）

登录后只显示项目卡片；右上角「添加新部署」进入独立表单。点击卡片查看状态、打开项目、设置访问权限，构建参数和日志入口收在「部署详情」中。

在项目详情选择「指定账号访问」，点击「管理访问账号」创建账号，关闭弹窗后勾选账号并保存。访问账号与后台管理员分离，仅能访问获授权的预览项目。浏览器访问受限项目时弹出账号密码框；删除账号会立即撤销权限。删除最后一个账号后项目仍保持受限，不会自动公开。当前示例保持公开，临时验收账号已删除。

权限由 `song-deploy-access.service` 在 `172.21.0.1:9101` 提供校验，通过 Traefik HTTP/HTTPS 入口的 `song-access@file` 中间件覆盖整个请求路径，包括静态资源、API 和 WebSocket 握手。工作台创建的新项目自动受入口校验覆盖。未登记的域名拒绝通过；现有主站和 Coolify 管理入口保留原认证行为。限制项目的 Basic 凭据在代理转发前移除，公开项目保留自身 Authorization 请求头。实现参考 [Traefik ForwardAuth](https://doc.traefik.io/traefik/reference/routing-configuration/http/middlewares/forwardauth/)。

账号盐及密码哈希、项目允许列表保存在 `/var/lib/song-deploy/security/access.json`，文件权限 0600。独立鉴权服务只读状态，不能读取 `/etc/song-deploy` 中的模型或部署引擎密钥。它故障时入口拒绝请求，不降级为公开。工作台更新任务状态不会覆盖权限。后台仅管理员可访问，不向访客开放部署 API。

当前私有预览仅通过 SSH 加密通道使用；公网可用后，应先启用 HTTPS 再分享受限项目，不能通过公网明文 HTTP 传输密码。浏览器 Basic 登录由浏览器缓存，切换账号可用新的隐私窗口。这版入口认证会占用受限项目的 Authorization 头，依赖自己 Bearer/Basic 头的 API 客户端需进一步适配；通常使用 Cookie 登录的网页不受这个头冲突影响。容器共享网络仍属于个人可信项目环境，不是用于运行敌对租户代码的隔离平台。

`greatsong.online/项目名` 不能解决当前未备案拦截。阿里云拦截的是未备案域名在内地服务器上的网站访问，主域名和其路径同样受影响。依据：[阿里云备案与域名常见问题](https://help.aliyun.com/zh/icp-filing/basic-icp-service/support/for-the-record-domain-faq/)。路径路由需另外适配应用 base path、资源和 Cookie，因此本次继续使用独立预览域名，没有宣称路径访问能绕过备案。

升级入口与界面执行 `python3 deployment/upgrade_workbench.py`，会先备份当前代码、权限及代理，再更新代理文件与 Coolify 中保存的代理配置。只更新工作台代码仍可使用 `install_agent.py`，已有鉴权服务由独立 systemd 单元运行。首次恢复整套服务需再运行升级脚本。

验收：13 项原边界及后台权限测试、8 项预览权限单元测试通过；`access-acceptance.json` 的 12 项真实入口检查通过。`verify_header_boundary.py` 实测私有预览密码不会进入项目，公开项目的应用认证头正常保留。旧主站、两个运行中的示例容器保持可用。
