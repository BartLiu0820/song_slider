# 宋 · 个人部署工作台

## Helper 自动准备（2026-10-23）

Coolify 的 helper 版本检查独立于平台自动升级开关：即使 `AUTOUPDATE=false`，它仍会从官方版本清单更新数据库中的 `helper_version`。本地定制仓库名 `song-deploy/coolify-helper` 不存在于公共镜像源；当要求的标签未在服务器构建时，Docker 会尝试远端拉取，进而出现“这镜像不在白名单”。仅修改数据库版本会被后续版本检查覆盖。

**现已自动处理，无需部署前手动同步。** 新建项目、“部署当前版本”、“更新并部署”和自动修复都在提交引擎前检查实际要求的 helper。存在且与已验证记录、构建源摘要一致时直接复用；缺失或版本变化时，服务器自动下载对应官方镜像，保留 Git、nginx、Nix 网络适配，验证工具和包装器后才激活标签并继续部署。若在排队期间又切换了 helper 版本，平台识别准备阶段的缺失错误并自动补齐重试一次，保留原项目方案。

普通 GHCR 拉取超时后，自动选择官方 CDN 当前 DNS 答案中测速较快的线路，再分块下载；保留原域名 TLS 验证，并核对官方清单、配置、每个压缩层、解压 diff ID 和导入后的文件系统。服务器独立执行，不依赖用户电脑在线。下载与重试有上限；网络完全不可用、磁盘不足或校验失败时保留旧应用，显示“部署环境未就绪”，点击重试会继续准备环境，不交给 AI 修改仓库方案。

实现为 `song-deploy-helper.service` 和 `admin/helper_manager.py`：独立 root 服务只接收固定的 ensure/status 请求，不接受镜像名、版本、命令或路径参数；仅 root 与 `song-deploy` 用户可连接 Unix socket。Web 服务没有 Docker/sudo 权限。构建源在 `/opt/song-deploy/helper-build`，必须 root 所有且其他用户不可写；已验证镜像记录在 `/var/lib/song-deploy-helper`。与部署共用维护锁，避免清理并发删除镜像。服务器启动时先启动准备服务；在准备阶段重启可恢复，在提交结果不明时不重复提交。

安装或更新：`python3 deployment/install_helper_preflight.py`，拒绝打断在途任务，备份后更新服务并保留账号和现有方案。`sync_helper.py` 保留为手动恢复命令，日常无需执行。没有新增定时轮询。官方行为依据：[helper 版本检查](https://github.com/coollabsio/coolify/blob/v4.4.7/app/Jobs/CheckHelperImageJob.php)、[运行版本选择](https://github.com/coollabsio/coolify/blob/v4.4.7/bootstrap/helpers/shared.php)。

自动处理验收：保留原镜像备份后，主动移除 `1.0.18` 使用标签，通过正常部署入口触发；平台自动重建并验证 helper，greencircle 成功发布同一提交 `6531ae6`，部署 ID `50xqmhetouvvcygn7qgzucgp`。再次检查复用了已验证镜像。服务器端从官方源完整下载约 185 MB、校验及归档用时 74.33 秒。原有 108 项后端检查与新增 24 项专项检查通过，覆盖缺失/损坏镜像记录、下载超时回退、摘要不一致不激活、版本竞态、权限边界、TLS 域名验证、暂停与重启恢复。主站、工作台和两个预览均 HTTP 200，管理页脚本与当前源码一致。证据：[真实自动部署](helper-auto-deploy-acceptance-20261023.json)、[镜像复用](helper-auto-cache-acceptance-20261023.json)、[安装备份](helper-preflight-install-20261023.json)、[最终服务与服务器下载验证](helper-auto-final-20261023.json)。

本次已基于官方 `1.0.18` 重建并完成真实部署。由于服务器直连 GHCR 的分层下载停滞，通过本机下载官方 linux/amd64 镜像，核对清单、配置、压缩层及解压 diff ID 后经 SSH 导入；Docker load 重新生成的清单摘要与上游不同，导入后的配置摘要及全部文件系统层再次验证一致。定制镜像为 `sha256:637388b8d2bf6cc49e058edabb90503097d09145dc12bf805d6027143ee33c29`，备份为 `/var/backups/song-deploy/helper-sync-20261023T122726Z`。没有修改镜像仓库白名单。

2026-10-23 20:29（北京时间）greencircle 成功发布 `6531ae61df1738973aeb458070ea79edaed3f4e5`，部署 ID `cnposdsedd9y6mwcef81jlgj`，保持 `static` + `/h5`。新容器健康检查通过，旧容器由引擎正常移除；线上 9 个核心文件 SHA-256 均与固定提交的源码一致。浏览器已显示新版“输入玩家名称”入口；主站、工作台、bluey 均 HTTP 200。本次没有进行完整游戏通关验证。证据：[镜像来源](helper-image-provenance-20261023.json)、[helper 工具验证](helper-sync-20261023.json)、[部署记录](helper-deploy-acceptance-20261023.json)、[线上文件核验](helper-http-acceptance-20261023.json)。

## PHP2Shell 安全修复（2026-10-22）

已备份并完成数据库恢复验证，将线上 Coolify 从 4.4.6 升级至 4.4.7；实际运行的 PHP CLI/FPM 均为 8.4.27。真实重新部署 greencircle 当前提交成功，主站、工作台、bluey、greencircle 及 48 项静态资源检查通过。端口限制、自定义 helper 和原有配置保留。备份位置、镜像来源及完整验收见 [修复记录](security/php2shell-repair-20261022.md)。下文早期记录中的 4.4.6 为历史版本。

## 当前状态（2026-10-21）

公网工作台已启用：<https://deploy.greatsong.online/>，使用原管理员账号登录，无需 SSH 通道。两个已部署示例的 HTTPS 预览也已通过验收。

本次排障确认域名请求已到达源站，503 的原因是此前等待备案而保留的 `publication.enabled=false`。执行 `python3 deployment/activate_public.py` 后，三个域名的 HTTP 来源校验、可信 HTTPS、真实管理员登录、Secure Cookie、项目访问策略检查及退出登录均通过；浏览器已显示正常登录表单。既有 DNS 验证证书继续使用。下文 2026-10-18 的备案阻塞与仅本机访问描述为历史记录，以本节为准。

## 本机使用

临时 IP 后台已启用：<https://47.116.108.184/>，使用相同管理员账号。IP 入口使用受信任的 Let's Encrypt 证书，自动续期；可以操作项目、触发识别和部署、查看日志及设置权限。项目预览仍需下面的 SSH 通道，页面会明确标注。域名公网发布开关与 IP 入口独立。

1. 双击 `open-workbench.command`，建立 SSH 通道并打开工作台。
2. 工作台：<http://127.0.0.1:19100>；底层部署引擎：<http://127.0.0.1:18000>。
3. 账号 `liuxiaobai`。密码保存在本机 `~/.config/song-deploy/admin-credentials.json`，不要把该文件提交到 Git。
4. 输入公开 GitHub 仓库地址，分支留空会识别默认分支；单仓库多应用时填写应用目录。
5. 点击“创建并自动部署”，在右侧 AI 对话中查看识别、构建、验证和自动修复进度；以后可直接说“更新部署”或“修复问题”。
6. 部署成功后点击“打开项目”，地址形如 `http://项目名.localhost:19180`。这是 SSH 通道内的服务器应用，不是本机运行的应用。
7. 完成测试后可双击 `close-workbench.command` 关闭通道；服务器应用继续运行。

电脑重启、休眠或网络切换导致断开后，重新双击打开脚本即可。不需要把 DeepSeek Key 再填入网页。

## 当前范围

- 常驻 Python 执行器调用 DeepSeek API，不在 4GB 服务器内加载模型权重。
- AI 通过 GitHub API 读取固定提交的文件树、最多 12 个配置/说明文件与 8 个应用目录下的 JS/TS 模块（共享 55,000 字符预算）；公开仓库的选定文件会发送到 DeepSeek。
- 支持 static、Dockerfile、Nixpacks 三类方案；必要时生成独立构建快照中的 Dockerfile 和启动脚本。只提交经过字段与路径校验的部署设置，不把模型回复作为宿主机命令执行。
- 执行器通过 GitHub 官方 codeload 下载固定提交的源码包，重新计算 Git 文件树并与该提交的 tree SHA 核对。通过后导入服务器内部的只读 Git 快照仓库，Coolify 从这个仓库 clone 并构建。完整源文件树一致，但快照导入提交与上游历史提交不同；工作台始终显示上游提交，任务记录保留二者。
- Coolify 负责容器构建、健康检查、队列、日志和运行管理。构建并发为 1。
- 发现必需密钥、数据库或持久化需求时停在待配置状态。这些项目需在部署引擎补充配置；首版未实现全自动数据库初始化。
- 私有仓库、任意 Git 服务商、自动生成/修复 Dockerfile、多服务 Compose 自动编排不在本版自动流程内。
- 源码包按流下载、哈希和解压，不再设 64MB 压缩包、256MB 解压量或 20,000 文件的固定上限。根据实时可用磁盘空间检查下载、解压与 Git 快照所需容量，至少保留 512MiB 或总磁盘 5%（取较大值）给系统；空间不足时明确报错。仍不支持 Git 子模块、LFS、符号链接；保留解压路径与完整 Git 文件树校验。
- 每次识别固定一个提交；“更新并部署”重新识别当前分支，保留同一卡片、应用和访问权限，方案通过校验后自动更新部署。失败自动进入 DeepSeek 修复；旧容器继续运行直到新版本健康检查通过。源码快照按项目与提交分开缓存。
- GitHub 未认证 API 存在调用限额；当前没有保存 GitHub token。

## 公网状态

`deploy.greatsong.online` 和 `*.preview.greatsong.online` DNS 已解析到服务器。
但公网实测被阿里云返回的 `Non-compliance ICP Filing` 页面拦截；用户确认域名尚未备案。
因此域名公网入口尚未验收。工作台监听本机回环与 Docker 网桥的 9100 端口，公网域名入口已指向工作台；域名发布开关关闭时拒绝该域名的公网登录。临时 IP HTTPS 后台已独立启用并完成登录验收，也可通过 SSH 使用。
展示页顶部“管理”固定指向 `https://deploy.greatsong.online`，发布或回退不会改成访客的本机地址。备案放行并完成公网启用前，通过本地启动脚本使用 SSH 工作台。

后台域名及 `*.preview.greatsong.online` 的正式证书已通过 DNS 验证签发、安装，源站证书校验通过，有效期到 2027-01-16；域名公网连接仍未验收。IP 证书自动续期已验证；域名通配符续期仍需 DNS 验证或后续配置 DNS API。

HTTPS 反代、Secure Cookie 和应用 HTTPS 配置已准备。备案放行后运行 `python3 deployment/activate_public.py`，脚本依次验证公网来源、可信证书、后台登录及预览权限，通过后开放入口。尚未放行时自动停止，不申请新证书；`--check` 只检测，`--rollback` 恢复本机模式。

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
- 应用失败会在工作台显示日志并交给 DeepSeek 修复，每次最多 4 轮；GitHub 源仓库保持不变，生成的部署配置进入独立构建提交。
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


## 备案前上线准备（2026-10-18 后续更新）

- `deploy.greatsong.online` 由工作台独占，Coolify 的公网 FQDN 已清空，底层引擎只从 SSH 通道管理。公网预检路由只返回来源校验值；业务发布开关默认关闭。
- 公网 HTTPS 登录签发带 Secure 的 Cookie；本机 SSH 访问保留本机 Cookie。只信任服务器 Docker 网桥代理提供的转发头。
- 公网预览 HTTP 在发布开启后先转 HTTPS，再验证账号；未开启前返回 503。本机 `.localhost` 预览别名只接受 SSH 回环路径，外部客户端伪造 Host 或 X-Forwarded-For 无法通过。
- 原卡片可以检查最新提交、重试识别与更新部署；构建日志在详情内读取。后台集成 token 增加 `read:sensitive` 以读取 Coolify 的构建日志，页面仅管理员可用，平台密钥会做遮盖；日志仍应视为项目的私有运维数据。
- 静态站点更新实测遇到 Docker Hub 加速源 502。Coolify 4.4.6 限定静态镜像名为 `nginx:alpine`，因此 helper 中仅对这一个精确 pull 命令改用官方 ECR 拉取，再映射到引擎要求的本地标签。其余 Docker 命令不改写。
- 每天北京时间 03:30 自动备份平台数据库、配置、账号权限、项目状态与源码快照，保留最近 7 份成功快照。备份目录 `/var/backups/song-deploy` 仅 root 可读；`latest-success.txt` 指向最近成功结果。应用业务数据库卷不在这套平台备份内，含业务数据库的项目需另外配置数据备份。
- 恢复探针会将配置解包到临时目录，将数据库导入独立临时库，验证表结构后清理。已实际恢复 76 张表。执行：`sudo python3 /opt/song-deploy/admin/verify_backup.py`。
- 完整准备脚本：`python3 deployment/prepare_release.py`。它会备份当前状态、安装执行器/鉴权服务/备份定时器、构建适配后的 helper、配置待发布路由。应避开正在分析或构建的任务。

当前“备案以外已准备”的范围是这版工作台及已支持的部署链路，不等于任意项目零配置成功。需要私有仓库授权、业务密钥、数据库和复杂多服务编排的项目仍需各自配置；Flaskr 数据库示例继续保留为待配置，不冒充已部署。


## Chrome 旧安全状态排查（2026-10-21）

本机普通 Chrome 的 Security 面板报告 `Resources - active content with certificate errors`，同时确认 `Certificate - valid and trusted` 和 TLS 1.3；无痕窗口对同一 HTTPS 地址显示「连接是安全的」。普通窗口关闭并重开本站标签页仍保留告警。原因是浏览器上下文内存中的旧证书错误内容标记，需保存未提交内容后完整退出 Chrome 并重开；本次未代用户重启整个浏览器。服务器无需因此重签证书或关闭证书校验。

验证截图：`https-secure-20261021.png`。Chromium 实现中的 `ran_content_with_cert_errors_hosts_` 按浏览器上下文保存该状态：https://raw.githubusercontent.com/chromium/chromium/main/components/security_interstitials/content/stateful_ssl_host_state_delegate.cc 。


## 对话式部署工作台（2026-10-21）

左侧部署列表支持搜索与切换，右侧保留当前项目的 AI 对话。新项目只需填写一次仓库、名称、分支/目录与访问权限，之后识别方案、部署状态、构建日志和更新操作都在对话中进行。窄屏时列表变为顶部横向切换。每个项目的输入草稿在切换时保留（当前页面内），历史消息保存在服务器 `conversations/<job-id>.json`；重新登录仍可查看。旧项目首次打开时会记录当前状态，不补造历史事件。

对话调用现有 DeepSeek 服务，传入当前项目状态、方案、权限与最近对话（包括主动读取到对话中的构建日志）。不传入平台凭据。当前版本可根据用户明确指令直接提交部署、更新或修复，执行仍走经验证的后台接口；不执行任意宿主机命令，不直接修改 GitHub 仓库。更新重新识别后自动部署；删除和权限变更仍保留明确操作入口。构建参数与权限放在「项目设置」。

「项目设置 → 删除部署」需输入项目名称确认。执行中的项目需等待完成；删除失败保留记录以便重试。删除调用 Coolify 应用删除 API，移除工作台记录、该项目的只读源码快照和权限配置，并立即撤销预览访问；容器清理由引擎异步处理。GitHub 源仓库、访问账号本身、持久化数据卷、其他项目与共享网络保留。尚未创建应用的失败/测试记录也可删除。

验证：41 项后台回归检查通过，覆盖对话保存、AI 仅建议不执行、身份/CSRF、删除失败重试、删除范围、磁盘不足与超过旧上限的大包（压缩后 >64MiB、解压后 265MiB）。桌面和手机布局截图保存在 `screenshots/conversation-desktop.png` 与 `screenshots/conversation-mobile.png`。

线上验收：真实 HTTPS 管理员登录、新布局、项目设置与删除入口通过；真实 DeepSeek 回复已正确识别旧 64MB 限制已取消。创建独立临时应用后，通过工作台删除接口移除，并向 Coolify 查询确认返回 404；原有 4 个项目保留。上线前代码与状态备份位于 `/var/backups/song-deploy/conversation-ui-20261021-152244`（首次升级前）与 `conversation-ui-20261021-152504`（窄屏及提示修正前）。

## 部署动态、构建日志与静态目录修复（2026-10-21）

- toast 在 4.5 秒后自动关闭；提交操作期间立即禁用对应操作，避免重复点击。对话底部只保留「部署当前版本」「检查更新」，访问权限在「项目设置」管理。
- 识别与部署自动显示真实阶段：GitHub 文件读取、AI 方案生成、源码下载/解压（含已处理 MB）、Git 树校验、应用配置、提交构建。构建日志直接展开在对话中，每两秒读取缓存；服务器每三秒向引擎同步，即使关闭浏览器也会继续更新结果。上游请求不再占用全局状态锁；同步失败会保留已有日志并显示重试提示。AI 回答也会读取当前阶段和最新构建日志。
- Coolify 4.4.6 的 static 构建使用 `base_directory` 作为构建上下文，忽略 `publish_directory`。工作台现将两者合并为静态构建目录，向引擎传入发布目录 `/`；识别时检查对应 `index.html`，提交前再次检查固定源码快照。显式重建避免复用同一提交下的旧错误镜像。
- 引擎 finished 后再通过真实本机预览路由检查首页，nginx 默认欢迎页、HTTP 错误不会标为成功。路由切换允许 30 秒重试；受限项目只验证账号保护入口，明确提示内容需登录确认，不绕过访问权限。
- greencircle 保留原项目、源提交和访问策略，改用 `/h5` 构建并重新部署。升级前备份：`/var/backups/song-deploy/deployment-progress-20261021-154133`。

验证：50 项后端回归检查通过，另有浏览器交互验证覆盖 toast 自动关闭、快捷入口、设置内权限、重复点击拦截、日志自动变化、草稿保留及手机宽度。真实上线验收记录见 `deployment-progress-acceptance.json`，截图见 `screenshots/deployment-progress-live.png`、`screenshots/deployment-complete-live.png` 和 `screenshots/greencircle-preview-fixed.png`。

实际浏览器验收：首页返回 HTTP 200，标题为「绿色循环圈外传 H5」，工作台与游戏均无未捕获 JS 异常；构建期间观察到 3 个不同日志版本。当前源提交未包含 `h5/assets/w3/**/*.mdx` 模型，浏览器存在相关 404（另有一个缺失图标），这是仓库素材缺失，部署未补造这些文件。游戏提供预生成精灵素材作为显示回退。最终代码备份为 `deployment-progress-20261021-154414`，线上三个修改文件的 SHA-256 与本地一致。

补充交互验收：经 SSH 通道访问同一线上容器，成功进入演示模式，加载 228 个资源（含 10 个精灵资源），无未捕获 JS 异常。公网 HTTPS 再次请求返回 200（2.4 秒）；独立无头浏览器复测曾出现两次导航超时，演示交互验证使用通道完成，未把该通道结果写成公网交互结果。游戏演示截图：`screenshots/greencircle-game-running.png`。

## 首屏加载与缓存排查（2026-10-21）

实测本机开启 Clash Verge 系统代理（本机 7897 端口），工作台与预览域名解析为代理虚拟地址。首页经现有网络耗时约 2.1–10.5 秒，固定源站 IP 且保留域名/TLS 校验的请求约 0.17 秒；同一个已压缩 JS 为 219 KB，固定源站约 0.40 秒，现有域名路径约 4.04 秒。源站负载 0.4 左右，约 2 GB 内存可用，没有发现 CPU/内存饱和。浏览器冷加载还有大量游戏素材和缺失 MDX 请求：本次采样 355 个请求，128 个 404；不应把首页耗时等同于整个游戏加载耗时。网络对照数据保存在 `loading-performance.json`，浏览器显式直连参数下仍约 22 秒才显示菜单，不能承诺仅调整代理就秒开游戏。

工作台现在先用内嵌关键样式显示加载壳，再并行读取主脚本与样式；内嵌样式使用 CSP 精确 SHA-256，不放宽成 unsafe-inline。加载超过 8 秒显示慢连接提示，资源超过 25 秒或 API 超过 20 秒显示失败与重新加载入口。登录按钮有执行中状态，认证后显示读取项目的阶段；项目与访问设置并行请求。只有 401 才回到登录表单，网络/服务器错误不会伪装成退出登录。

“打开项目”链接附带部署 UUID，避开先前无查询参数地址缓存的 nginx 欢迎页。平台默认静态应用配置为首页 HTML `Cache-Control: no-store`、其他文件 `private, no-cache` 配合 ETag 重验，并开启文本压缩。已有用户自定义 nginx 配置保留。`apply_preview_cache.py` 将默认配置保存到引擎并对当前容器执行 `nginx -t` 与平滑重载；greencircle 已应用，未中断重建。先前已存入浏览器的旧地址缓存无法靠服务器响应头追溯清除；从平台新入口进入，或对旧地址强制刷新一次。

验证：52 项后端检查（包括部署版本链接和保留自定义 nginx），原浏览器交互检查及 6 项加载场景检查通过；真实 HTTPS 登录、新版本预览链接和无 CSP/JS 异常通过。截图 `screenshots/workbench-loading.png` 展示主脚本延迟时的加载壳；线上验收 `loading-acceptance.json`。工作台备份：`/var/backups/song-deploy/loading-cache-20261021-160529`；预览 nginx 配置备份：`/var/backups/song-deploy/preview-cache-20261021-160610`。

### 本机域名直连已启用（2026-10-21，用户确认后）

已在 Clash Verge 的全局扩展脚本中增加 `DOMAIN-SUFFIX,greatsong.online,DIRECT`，并重新加载当前规则。规则仅覆盖该根域及其子域；其他代理选择、端口、运行模式和 TUN 设置经前后对比保持一致。只关闭了 1 条目标域名旧连接，让其按新规则重连。控制器实时连接确认 `deploy.greatsong.online` 命中 `DomainSuffix / greatsong.online / DIRECT`。原始配置备份保存在本机受限目录 `~/.config/song-deploy/network-backups/20261021-161839`，没有将代理凭据写入项目。

变更后通过正常域名复测：工作台首页 0.30 秒，游戏首页 0.30 秒，模型查看器 JS 0.51 秒。默认浏览器冷启动下游戏菜单 0.92 秒可见（DOM ready 0.87 秒），之前同样的当前网络路径 25 秒超时。菜单可用不代表所有素材下载完成；随后继续加载素材，仓库原有 128 个缺失资源响应仍单独保留。浏览器原始数据：`loading-performance-after-direct.json`。配置热加载接口依据 [Mihomo 官方 API](https://wiki.metacubex.one/en/api/)。


## AI 方案纠错与非 index 首页（2026-10-21）

- static 直接发布、Nixpacks 依赖安装/构建后发布（`is_static=true`）、Nixpacks 服务端、已有 Dockerfile 分别处理。服务端项目不要求存在 `index.html`；构建输出目录也不要求预先存在于源码中。
- AI 读取 README、启动脚本及应用目录的 JS/TS 模块，依据证据选择 `static_entry`，支持中文 HTML 文件名。只有真正直接复制源码的 static 路径检查源文件入口；构建后发布通过 nginx 和最终预览检查验证。
- 识别时把字段、路径、入口及缺失浏览器依赖的校验错误反馈给 DeepSeek，最多自动修正两次，保留每轮校验结果；仍不通过才显示失败。必要密钥/数据库仍保持待配置。
- 直接静态方案若引用未入库的 `node_modules`，引导改用 Nixpacks 安装依赖后发布。平台生成的 nginx 配置支持 `.mjs` MIME 和实际首页；再次部署可更新平台管理的配置，用户手写配置保留。
- 构建方式切换时显式更新引擎 `is_static`，避免服务端项目沿用旧静态设置。构建命令仍只由容器构建引擎执行，AI 不能执行宿主机命令。

实现核对：[Coolify 4.4.6 API 与 is_static 设置](https://github.com/coollabsio/coolify/blob/v4.4.6/app/Http/Controllers/Api/ApplicationsController.php)、[Nixpacks 构建后静态发布](https://github.com/coollabsio/coolify/blob/v4.4.6/app/Jobs/ApplicationDeploymentJob.php)。

验证：64 项后端测试通过，涵盖静态误判自动改为服务端、中文入口与配置注入边界、构建产物不在源仓库、浏览器依赖安装、重试上限、待配置状态保留、静态与服务端切换。工作台浏览器交互与加载回归通过。线上 DeepSeek 已为 bluey_hgr 识别出 `npm ci --omit=dev` + Nixpacks 静态发布方案，真实结果记录于 `plan-repair-acceptance.json`。

上线备份：`/var/backups/song-deploy/ai-plan-repair-20261021-170558`（入口与纠错），`ai-plan-repair-20261021-170946`（依赖识别与构建后发布）。首次 Nixpacks 构建遇到 GHCR 两个分层下载停滞，已从官方源按字节范围下载并逐层 SHA-256 验证，将同一 amd64 镜像导入服务器缓存后重试；版本 `ghcr.io/railwayapp/nixpacks:ubuntu-1745885067`，上游清单摘要 `sha256:d45c89d80e13d7ad0fd555b5130f22a866d9dd10e861f589932303ef2314c7de`。临时传输包已删除。

Nix 构建初始化随后确认官方二进制缓存下载过慢。helper 的 Docker 包装器现在只对 Nixpacks 生成路径中的固定 `RUN nix-env -if .nixpacks/` 指令补充 SJTUG 镜像（priority=10）和官方回退源，Nix 默认签名验证继续生效；普通仓库 Dockerfile 不改写。已验证重复执行不会重复插入，旧 helper 摘要保存在 `/var/backups/song-deploy/nixpacks-network-20261021/helper-image-id`。参考：[NixOS 官方镜像配置](https://wiki.nixos.org/wiki/China)。TUNA 对本次固定版本的包返回 404，最终使用实测能返回原始签名包的 SJTUG；6.5MB glibc 包下载实测约 0.3 秒。

最终线上验收：bluey 新版本在 2026-10-21 17:42（北京时间）完成滚动更新，容器健康检查与真实首页检查通过。浏览器验证 `gesture-recognizer-runtime.mjs`、`wire-loop-renderer.mjs`、`wire-loop-runtime.mjs` 及 npm 依赖均能加载，按键准备 → 角色选择 → 火线冲击入口（WL-01）通过，未捕获脚本异常 0、HTTP 失败资源 0。未进行真人摄像头手势效果评测。结果见 `plan-repair-acceptance.json`，截图见 `screenshots/bluey-plan-repair.png`。旧包装器源码保存在 `/var/backups/song-deploy/nixpacks-network-20261021/docker-wrapper`；旧镜像已被引擎清理，回退时需用备份源码重建。服务器 helper 构建源已同步。


## 2026-10-21 平台自动修复升级

新项目与更新现在默认自动部署，失败后由 DeepSeek 读取诊断、修正方案并重试。支持为非标准项目生成独立构建快照中的 Dockerfile 和启动脚本。详细执行范围、重试机制与真实限制见 [autonomous-deployment.md](autonomous-deployment.md)。

## 部署状态遮挡排查与服务器空间（2026-10-22）

本次用户反馈“更新并部署卡住、询问 AI 也无回复”。服务器与引擎记录一致：greencircle 在北京时间 16:42:47 完成部署和真实预览检查；16:43:30 收到询问，16:43:31 已保存 AI 回复。浏览器 DOM 包含完成事件与回复，但截图显示整个对话视区被末尾构建日志占据，日志内部仍停留在镜像下载段落。已确认的缺陷是日志/对话排布与滚动导致结果不可见，未发现该次部署停止或磁盘耗尽。

修复：
- 当前部署状态固定在项目标题下，区分尚未完成、完成、失败/待配置；显示本次操作耗时、当前阶段与状态同步时间。
- 根据引擎日志的实际里程碑显示拉取镜像、构建、镜像输出、启动、健康检查及最终验证。日志变化时间与引擎检查时间独立记录，90 秒无新输出会提示等待，不伪装完成。成功仍须通过引擎与真实预览检查。
- 构建日志移出对话滚动区，可折叠、限制高度；完成后收起。滚动查看历史时有新消息提示，发送消息后定位最新回复，回到标签页/网络恢复会重新同步。连接问题保持显示，不再依赖短暂 toast。
- 常见“部署完了吗”查询直接读取任务状态，避免等待模型；其他 AI 回复显示等待时间，服务重启中断的回复明确记录并允许重发。
- 顶部“服务器空间”进入磁盘/内存总量、实际占用分布、各项目源码缓存、容器内存使用与上限、容器可写层和 CPU 页面。明确所有项目共享磁盘，没有项目磁盘配额；内存上限不等于预分配/当前用量。

采集器：`admin/resources.py` 由 `song-deploy-resources.timer` 每次采集结束 60 秒后运行，单次最多 240 秒。独立 root 服务只执行固定只读查询，原 Web 服务不增加 Docker/管理员权限。只发布白名单字段到 `/run/song-deploy-metrics/resources.json`，API 要求管理员登录；异常显示未知或过期，不置零。`du -x` 排除挂载的容器根目录，避免将共享镜像重复计入 Docker 数据；空间按实际块占用估算。

部署脚本：`python3 deployment/install_status_resources.py`，拒绝打断正在执行的部署；保留凭据与应用。此次备份：`/var/backups/song-deploy/status-resources-20261022-165622`。回退可恢复其中 `agent/`，重启 `song-deploy-agent`；如需停用采集，停止并禁用 `song-deploy-resources.timer`。

验证：91 项后端检查通过；Chrome 隔离场景验证长日志、进行中/完成状态、新回复提示与定位、390px 窄屏，无脚本错误；真实管理页与两个应用 HTTPS 均检查通过，未登录空间 API 返回 401。采集器识别 2 个项目、8 个容器，数据无采集错误。首次采样磁盘总量 48.85 GiB、已用 12.62 GiB、可用 34.03 GiB、文件系统保留 2.20 GiB。截图：`screenshots/server-resources-live.jpg`、`screenshots/status-reply-live.jpg`。

## 空间清理、版本一致性与 AI 回复格式（2026-10-22）

管理页 → 服务器空间 → 清理空间：先只读扫描，逐项列出旧项目镜像、构建缓存和预计释放量；默认不选中，勾选后还需单独确认。预览绑定当前登录会话，10 分钟有效；确认后重新核验引用、最近使用时间和构建队列，再按精确 ID 清理。运行中及已停止容器引用的镜像、基础镜像、共享缓存、近期资源均保留；不删除容器、数据卷、源码或备份。部署与清理使用跨进程互斥锁。

`admin/cleanup.py` 是独立 root Unix socket 服务，Web 进程仍没有 Docker/sudo 权限。确认与结果持久化到 `/var/lib/song-deploy-cleanup`；服务重启不会自动重放删除。镜像使用 `force=false&noprune=true` 删除，缓存使用锚定 ID、1 小时保留期、`private=""` 筛选。BuildKit 保护在用记录。当前引擎的布尔筛选是空值存在标志，`private=true` / `inuse=false` 并不匹配预期；已用 `buildx du` 对同一缓存 ID 只读验证最终表达式。参考 [Docker buildx prune](https://docs.docker.com/reference/cli/docker/buildx/prune/) 和 [BuildKit 过滤字段实现](https://github.com/moby/buildkit/blob/master/cache/manager.go)。

真实扫描：7 项可清理，预计约 2.11 GiB；54 项受保护。估算不等同最终释放量，结果显示逐项结果和文件系统可用空间变化。线上仅扫描，没有确认或执行删除；完整确认/结果交互在本地模拟环境完成。

游戏页面未更新的根因：服务器与 GitHub main 都是 `bc89e7c`，本机 greencircle 的 10 个新提交尚未推送。用户明确确认后，已推送这 10 个现有提交到 main，并部署 `28c4703cbc6a9bc10a59e2aa9540821685073035`，部署 ID `5skwibblnfxkwxvjoypyifwh`。原带旧 deployment 参数的链接也已显示新开局菜单，单人推荐入口可进入游戏。

历史 AI 错误来自回复 JSON 解析失败；未留存原始上游回复，无法进一步断言具体格式错误。现在检查完整 JSON、字段类型、动作白名单和截断情况；失败自动纠正一次，仍失败时提供可读提示，不执行未通过校验的动作。有关更新/版本的问题会读取当前远端提交，不能再用旧部署记录推断 main 一致；线上询问已正常返回 `28c4703` 一致且没有执行部署。

验证：108 项后端测试通过，覆盖引用保护、状态变更中止、精确选择、重复确认、会话与 CSRF、共享/独占锁及格式纠错。线上扫描、空间估算、未确认时按钮禁用、AI 真实回复通过；未登录清理 API 401、缺少 CSRF 的确认请求 403。备份 `/var/backups/song-deploy/cleanup-chat-20261022-182559`。验收记录见 `cleanup-chat-acceptance.json`，截图见 `screenshots/cleanup-preview-live.jpg`、`screenshots/greencircle-updated-menu.jpg`。
