# 部署链路验证报告

> 后续实施更新：2026-10-18 已安装后台并接入 DeepSeek；本文件保留当时验证结论，最新状态见 [部署记录](03-deployment.md) 和 [使用说明](deployment/README.md)。
> 日期：2026-10-18，北京时间 | 结论：基础设施及两个真实仓库验证通过；完整部署平台和 AI Agent 尚未上线

## 结论

现有服务器可以承担个人轻量 Web 项目的部署测试。已验证真实 Git 拉取、静态页面、Python 后端、SQLite 业务数据、独立 PostgreSQL 持久化、应用更新及回退。

本轮共完成两组成功验证，各包含 7 项检查。前两次基础探针失败分别由 sudo 环境变量继承和入口网络配置造成，已修复并完成全流程重跑，失败记录和成功证据均保留。

这些结果支持继续开发个人部署后台；不代表已经验证所有框架、项目自动识别、模型工具调用、成熟部署平台的安装或公网预览域名。

## 真实仓库

| 项目 | 来源与固定版本 | 实测结果 |
|---|---|---|
| 现有展示页 | https://github.com/BartLiu0820/song_slider ，commit `0e43cefff6f63f0331f1d5506886741f923a4969` | 服务器从 GitHub 重新克隆；HTML 字节一致；视频 Range 请求返回 206 与正确的 1024 字节 |
| Docker 官方 Flask 示例 | https://github.com/docker/awesome-compose/tree/30f4b7f6a6c3b0c0ecf4d4efb0de203c48d11562/flask ，入口子目录 `flask/app` | 安装依赖、构建镜像，Gunicorn 启动，HTTP 200，返回 Hello World! |
| Flask 官方 Flaskr 博客 | https://github.com/pallets/flask/tree/2c1b30d0503cfb064f1cb252e6614a06915a362a/examples/tutorial ，Flask 3.1.2 标签 | 构建、首次初始化 SQLite、注册、登录、创建文章均通过；重建容器后文章与会话保留 |

两个上游仓库的 Git 工作区均保持干净。部署适配文件在独立测试副本中生成：改用已验证可达的官方 ECR Python 3.12 镜像、Gunicorn、明确端口、非 root 用户、资源限制和持久卷。测试不等于原仓库 Dockerfile 原封不动运行。

## 基础探针

| 检查 | 结果 |
|---|---|
| 真实静态仓库克隆与静态服务 | 通过 |
| Python HTTP 服务 | 通过 |
| PostgreSQL 插入记录、重建数据库与应用容器 | 记录保留，读取成功 |
| Git v1 → v2、构建新镜像并更新应用 | 返回 v2 |
| 故意创建健康检查返回 503 的候选版本 | 验证流程拒绝发布，原 v2 仍可访问 |
| 从 v2 回退到 v1 镜像 | 返回 v1，数据库记录仍在 |
| 原站点核验 | HTTPS 200，HTML SHA-256 未变化 |

更新/回退使用受控测试脚本执行；不是已上线任务队列中的自动功能，也不是无中断发布证明。未测试数据库 schema 回退。

## 实测时间与资源

| 项目 | 结果 |
|---|---|
| 静态仓库浅克隆 | 约 2.1 秒 |
| 基础 Python 样例首次构建 | 40.72 秒；后续复用缓存约 0.75 秒 |
| 基础样例 v2 增量构建 | 0.98 秒 |
| Docker 官方 Flask 示例首次构建 | 75.91 秒 |
| Flaskr 首次构建 | 92.25 秒 |
| 两个真实应用加测试代理的运行内存快照 | 约 71.12 MiB |
| 真实应用运行时整机可用内存 | 2715 MiB |

以上为轻量示例、少量请求下的单次测量。运行内存是 Docker stats 快照，不是峰值或完整系统开销；未包含 Coolify/Dokploy、AI worker、大型前端构建和并发压力，不能据此推算可同时运行项目数量。

## 网络与 DeepSeek

- GitHub 拉取成功。
- Docker Hub 直接连接超时。
- Docker 官方 Amazon ECR 镜像拉取成功：Python 约 22.4 秒，PostgreSQL 约 65.6 秒。后续构建可显式使用该路径；这不代表任意第三方镜像都有对应 ECR 副本。
- Python 依赖从 PyPI 安装成功；首次下载仍是耗时组成部分。
- 服务器访问 `https://api.deepseek.com/models` 返回 401，证明无凭据条件下接口可达；未验证鉴权、模型列表、额度、工具调用或推理效果。
- DeepSeek 接入方式确定为“服务器常驻执行器调用模型 API”，无需在此机加载 DeepSeek 模型权重。用户已说明 Key 后续提供，本轮未创建伪连接或消耗模型额度。

参考：[Docker 官方 ECR 镜像说明](https://www.docker.com/blog/news-from-aws-reinvent-docker-official-images-on-amazon-ecr-public/)、[DeepSeek 工具调用](https://api-docs.deepseek.com/guides/tool_calls/)。

## 自动部署必须保存的配置

1. 仓库 URL、分支/固定 commit、实际应用子目录。
2. 构建环境、依赖版本、构建命令、启动命令和服务端口。
3. 健康检查路径及通过条件。
4. 数据卷目录、应用密钥、运行资源上限。
5. 首次初始化与后续更新的区别：Flaskr 的 `init-db` 会删除旧表，不能加入每次启动命令。
6. 上一可用版本的镜像与配置；应用回退和数据库恢复分开管理。

这些是下一阶段规则识别和 AI 配置助手的输出对象。样例适配目前由 Codex完成，尚未证明未来服务器 Agent 能独立完成同样工作。

## 公网访问前置条件

服务器 DNS 检查确认 `greatsong.online` 指向 `47.116.108.184`；以下计划域名当前未解析：

| 类型 | 主机记录 | 值 |
|---|---|---|
| A | deploy | 47.116.108.184 |
| A | *.preview | 47.116.108.184 |

本轮使用隔离测试代理及 Host 请求验证路由，端口仅绑定 `127.0.0.1:18080`，没有发布公网测试域名，也没有申请相应证书。

## 清理和保留内容

- 所有本轮测试容器、网络、测试数据库卷和临时密码已清理。
- 最终运行容器仍只有原 `song-slider`，原域名、代理配置和展示页未修改。
- 服务器保留基础镜像、测试镜像缓存、源码与日志，便于复现；未安装 Coolify/Dokploy。
- 本地脚本：`validation/server_probe.py`、`validation/real_repo_probe.py`。
- 本地汇总证据：`validation/evidence-2026-10-18.json`。
- 基础成功记录：服务器 `/home/admin/deploy-validation/20261018-071457/results.json`。
- 真实仓库成功记录：服务器 `/home/admin/deploy-validation/real-20261018-071855/results.json`。

## 下一阶段

建议进入成熟部署引擎兼容性验证与后台设计：保留现有展示页，确定公网入口代理归属，再接入登录、项目配置、持久队列、日志及版本管理。模型 Key 到位后再验证 DeepSeek 的项目识别和受控工具调用。

本轮仍未覆盖 Node/SSR、私有仓库、多服务真实业务项目及 monorepo；首次支持这些类型时需要各补一个代表性项目验证。
