# 正式证书与临时 IP 后台

2026-10-18：临时后台为 `https://47.116.108.184/`。Certbot 5.8.0 已完成 IP 地址验证并安装 Let's Encrypt 正式证书。域名证书申请使用 DNS-01，覆盖 `deploy.greatsong.online` 和 `*.preview.greatsong.online`；两条 TXT 已在权威 DNS 验证通过，正式证书已签发并自动安装，域名公网发布开关保持关闭。域名证书到期时间为 2027-01-16 17:52:36（北京时间）。

## 入口范围

- IP 入口独立使用 `publication.json` 的 `ip_enabled`，管理员认证、CSRF、Secure/HttpOnly Cookie 均保留；HTTP 先跳转 HTTPS。
- 项目预览继续使用 SSH 本机别名。部署项目与管理后台不能共享同一浏览器源，因此没有增加 `IP/项目路径` 代理。
- 主站管理按钮仍指向域名后台。原站点 HTTPS 和 SSH 通道保留。

## IP 证书

证书目录：`/etc/letsencrypt/song-ip/live/song-ip/`。首次正式证书到期时间为 2026-10-25 01:42:58 UTC。

`song-ip-certificate.timer` 每天两次检查续期；Certbot 的短期证书自动决定续期窗口。续期后的 `install_certificate.py` 把证书复制到 `/data/coolify/proxy/certificates/`，更新 Traefik 动态配置；IP 证书同时作为无 SNI 请求的默认证书。私钥目录仅 root 可读，密钥不进入仓库。

HTTP-01 文件仅从 `/var/lib/song-acme-http/.well-known/acme-challenge/` 读取。Traefik 的 `allowACMEByPass` 仅用于容纳外部 Certbot；域名验证路径通过高优先级路由交回 `acme-http@internal`，保留未来域名自动签发能力。代理配置同时保存在 Coolify。

检查或关闭临时入口（通过 SSH 在服务器执行）：

```sh
sudo python3 /opt/song-deploy/admin/ip_admin.py status
sudo python3 /opt/song-deploy/admin/ip_admin.py disable
```

重新启用用 `enable`，会先校验 IP 证书的信任链、地址和有效期。关闭入口不影响域名发布及 SSH。

## 域名 DNS 验证

手动验证程序 `dns_auth.py` 把 TXT 记录写到 `/var/lib/song-acme/dns-challenges.json`，等所有权威 DNS 返回匹配值后继续。每次等待最多一小时；超时后需重新申请并提供新的验证值。

`/etc/letsencrypt/song-domain/renewal-hooks/deploy/10-song-install` 会在签发后自动安装证书并准备 HTTPS 路由，域名公网发布仍关闭。证书状态可查看 `/etc/letsencrypt/song-domain/live/song-domains/fullchain.pem`。

当前没有 DNS API 凭据，通配符证书尚不具备无人值守续期能力。后续可以用最小权限 DNS 凭据自动续期；备案后也可以为各实际使用的子域名单独使用 HTTP-01 自动签发。不能把 IP 证书的自动续期误认为域名通配符也已自动续期。

Certbot 账户、私钥、续期配置和相关 systemd 单元已经纳入服务器备份。

参考：[Let's Encrypt IP 证书与 Certbot](https://letsencrypt.org/2026/03/11/shorter-certs-certbot)、[DNS-01 验证](https://letsencrypt.org/docs/challenge-types/)。

## 验证结果

IP 公网 HTTPS 信任链、管理员登录、Secure/HttpOnly Cookie、CSRF、退出均通过；IP 证书续期 dry-run（包含安装钩子）成功。39 项离线检查、12 项项目访问权限验收通过。原展示页源站 HTTPS 返回 200。域名证书已安装：后台和预览源站的 TLS 信任链校验通过，业务返回预期的 503（公网发布关闭）。外部域名 TLS 连接仍被中断，公网域名尚未验收；直接 IP 的外部 HTTPS 为 200，证书校验通过。
