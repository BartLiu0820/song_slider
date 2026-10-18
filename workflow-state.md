# Workflow State

## Review Gates

| 阶段 | 状态 | 产物 | 备注 |
|---|---|---|---|
| Phase 1：可行性评估 | confirmed | 01-research.md | 2026-10-18 用户确认“按你说的来”，授权尝试验证 |
| 技术验证 | complete | 02-validation.md | 基础探针 7 项、两个真实上游项目 7 项检查通过；已清理测试容器 |

Target Surface: web-only。用户已授权继续部署实施，并完成 DNS、提供 DeepSeek Key。

当前工程：本机访问版 MVP 已验收。已安装 Coolify 4.4.6、独立 AI 工作台、登录与 SSH 访问入口。DeepSeek 已实际识别 Docker/Flask、Flaskr/SQLite 与 MDN 静态项目；静态与后端部署、资源健康及浏览器访问通过，并补测了空白新建流程。12 项针对性单元测试、6 项在线验收通过，详见 03-deployment.md。

公网阻塞：阿里云返回 Non-compliance ICP Filing；用户确认尚未备案。当前使用 SSH 通道与 localhost 子域名测试，不能宣称公网 HTTPS 已上线。

使用说明：deployment/README.md。完整范围仍不包含任意仓库全自动保证；数据库、密钥、私有仓库等需要后续适配。

2026-10-18 后续界面与权限优化已上线：卡片首页、独立新增页、部署详情和按账号授权。独立访问账号与后台管理员分离，代理入口强制校验；13 + 8 项单元检查和 12 项实际入口检查通过，另验证私有密码不传到应用。当前保持本机 SSH 预览；主域名路径也不能消除未备案阻塞。详见 deployment/README.md 新增章节。

2026-10-18 备案前发布准备已完成：公网工作台路由、Secure Cookie 与原卡片更新部署；移除底层引擎公网域名；发布脚本在 HTTP 来源校验未通过时停止，未申请新证书。静态示例实际更新成功，修复镜像源 502；构建日志已接入。34 项离线检查、12 项入口权限及 6 项在线验收通过；平台备份恢复 76 张表成功，已启用每日平台备份。详情见 deployment/04-release-readiness.md。公网证书和访问验收仍需备案真正放行后执行。
