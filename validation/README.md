# 服务器部署验证

`server_probe.py` 是一次性基础设施探针，不是完整部署平台或常驻 AI Agent。

`real_repo_probe.py` 进一步验证两个真实上游仓库：Docker 的 awesome-compose/Flask 示例，以及 Pallets 的 Flaskr 教程项目（固定 Flask 3.1.2 标签）。上游源码保持原样，构建适配文件放在独立副本中。数据库项目使用 SQLite；独立 PostgreSQL 的容器持久化由基础探针覆盖。

## 范围

- 从 GitHub 克隆真实展示页仓库，验证 HTML 和视频 Range 响应。
- 创建本地 Git 样例仓库，构建 Python HTTP 服务及 PostgreSQL 连接样例。
- 验证三个 Host 路由、数据库容器重建后的数据保留、Git 更新、失败候选阻断和应用版本回退。
- 真实项目额外验证 Flaskr 注册、登录、创建文章、容器重建后文章和会话保留。初始化数据库仅在全新测试卷上执行一次。
- 应用和数据库在内部网络；入口代理另接入口网络，仅绑定服务器 `127.0.0.1:18080`。
- 保存运行证据，结束后删除本次容器、网络、样例数据库卷和测试密码；保留代码、日志及镜像缓存。

## 执行

在本目录运行：

```sh
ssh -o BatchMode=yes songhuang-server 'python3 -u -' < server_probe.py
```

依赖服务器已有 Docker、Compose、Git、Python，以及下面的已下载镜像：

- `caddy:2-alpine`
- `public.ecr.aws/docker/library/python:3.12-slim`
- `public.ecr.aws/docker/library/postgres:16-alpine`

每次在 `/home/admin/deploy-validation/<UTC运行时间>/` 留下 `results.json` 和 `commands.log`。运行时间目录使用 UTC，用户报告使用北京时间。

Python 样例安装固定版本 `pg8000==1.31.5`，需要构建时能访问 PyPI。首次构建和有缓存构建应分别计时，不能混用。

## 尚未验证

- Coolify / Dokploy 的安装、API 适配和实际资源开销。
- Node、SSR、monorepo、私有仓库等其他类型项目的自动识别与部署。
- 公网子域名解析与对应 HTTPS 证书签发。
- 登录后台、持久任务队列、无中断切流和并发部署。
- DeepSeek 模型鉴权、工具调用、配置修复效果与费用。
- 数据库 schema 回退、备份恢复、压力测试。

## 下一阶段输入

DNS 计划（尚未写入）：

| 类型 | 主机记录 | 值 |
|---|---|---|
| A | deploy | 47.116.108.184 |
| A | *.preview | 47.116.108.184 |

DeepSeek 采用服务器执行器调用 API 的方式，无需在此服务器加载模型权重。`https://api.deepseek.com/models` 已在无凭据条件下返回 401，只证明网络和 HTTP 接口可达。接入时需由用户提供 Key，并通过受限配置文件或后台密钥表单写入；不提交 Git，不写入部署日志。模型名称在鉴权后查询确认，不硬编码未知可用模型。

接入的执行器应限制可用工具和任务范围，先分析仓库再输出结构化配置，由固定部署流程执行，记录尝试次数和费用预算。

参考：[DeepSeek 工具调用](https://api-docs.deepseek.com/guides/tool_calls/)、[Docker 官方镜像的 ECR 发布说明](https://www.docker.com/blog/news-from-aws-reinvent-docker-official-images-on-amazon-ecr-public/)。
