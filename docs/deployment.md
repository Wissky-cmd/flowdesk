# 部署、验证与恢复

## 当前验证边界

Windows 已运行 PostgreSQL、API、Vue、pytest、Playwright、任务执行函数及独立恢复演练。此机器没有 Docker，WSL 未安装；没有 Git 远程和远程 CI 运行记录。下列容器、真实 Redis、Linux Celery 和 GitHub Actions 是可执行交付物，尚不能写成“已部署验收通过”。

## Linux / Docker Compose

依赖锁：Windows 和 Linux x86_64 / CPython 3.14 各有独立 SHA256 锁文件。Linux 锁已通过真实 pip 平台解析，尚未在 Linux 安装运行。固定镜像标签，不使用 latest；生产建议在首次构建验收后再锁定镜像 digest。

```sh
cp deploy/.env.example deploy/.env
# 编辑密码；应用账号和管理员密码分开，使用随机 URL-safe 字符串。
docker compose --env-file deploy/.env config --quiet
docker compose --env-file deploy/.env up -d --build
# 设置一个自己的随机演示密码，再初始化种子（不会覆盖已有账号）。
docker compose --env-file deploy/.env exec -e SEED_PASSWORD api python -m app.seed
```

需要在运行 seed 的 shell 中先 `export SEED_PASSWORD=...`，不要把真实值写入命令文档或提交。访问 `http://127.0.0.1:8080`。数据库、Redis、API 无宿主端口；仅 Nginx 绑定 loopback。首次空卷初始化创建非超级用户 flowdesk。现有卷不会重跑 init 脚本，不能通过随意改环境变量轮换现有数据库密码。

服务：postgres、redis（AOF）、一次性 migrate、api、Linux worker、独立 dispatcher、web/Nginx。迁移失败阻止业务启动，Worker 与 API 共享私有 exports 卷。Nginx 同源代理 `/api`、SPA 回退、请求体上限与安全头。

公网部署需可信 HTTPS 入口、精确 HTTPS `ALLOWED_ORIGINS`、`COOKIE_SECURE=true`。当前 Compose 为 loopback HTTP 演示，不附带域名或证书，也未自动对公网开放。固定镜像和依赖仍需定期安全更新。

```sh
docker compose --env-file deploy/.env logs --tail=100 api worker dispatcher
docker compose --env-file deploy/.env stop worker
# 创建导出任务，确认仍在数据库中。
docker compose --env-file deploy/.env start worker
# 在预算未耗尽时恢复处理；若耗尽，通过任务中心填写原因人工重试。
```

## 真实队列与 CI

`scripts/queue_smoke.py` 要求 Linux 和显式隔离的 `*_test` 数据库。它在没有 Worker 时先投递，启动真正的 Celery Worker 后等待完成，再重复投递并断言单一产物和一次执行。Windows 直接运行会拒绝，避免把本机函数测试冒充 Linux Worker 证据。

`.github/workflows/ci.yml` 使用 PostgreSQL/Redis 服务容器，执行迁移往返、后端测试、真实 Redis 原子计数与窗口恢复、Linux Worker 烟测、前端类型/构建/浏览器、Compose 配置/镜像构建。上传测试报告和截图；未配置自动部署。推送到用户选择的 GitHub 仓库后才会得到实际 CI 结果，目前没有远程运行记录。

本地 `./scripts/verify.ps1` 检查依赖、迁移、后端、类型、构建、浏览器。没有 TEST_REDIS_URL 时明确跳过真实 Redis 测试，不使用假 Redis 宣称通过。业务集成测试始终使用真正 PostgreSQL。

## 备份恢复

已交付 `scripts/backup_restore.py`，用于当前便携 PostgreSQL 的真实演练：

```powershell
& .venv/Scripts/python.exe scripts/backup_restore.py
```

只接受当前项目 loopback `flowdesk` 数据库；不会覆盖现有库。锁住业务表写入并导出 PostgreSQL snapshot；如果存在 running 任务就拒绝开始。快照期间备份数据库和 succeeded CSV 文件，恢复到新的 `flowdesk_restore_时间_test` 库，核对所有表计数、迁移版本、附件 SHA256 和导出 SHA256，再实际登录、查看工单、下载附件/导出。报告 `docs/evidence/backup-restore.json` 不含密码；备份与文件保存在 `.local/backups`，恢复库保留供检查。

数据库备份包含密码哈希、会话、令牌哈希和业务数据，不可提交 Git。当前不自动上传云端，不自动删除恢复库。生产应把备份放在受限、加密、离机存储，制定保留与销毁规则。

容器环境的基本步骤：暂停 api/worker/dispatcher 写入 → `pg_dump -Fc` → 备份 exports 卷 → 恢复写入；在独立空数据库和独立卷恢复 → 核对计数、附件/CSV 哈希 → 跑登录与下载测试。可重建的 Redis 队列不能替代 PostgreSQL jobs/outbox 权威记录。

## 故障排查

API 返回 request_id 和 X-Request-ID，访问日志记录同一 ID、方法、无查询参数的路径、HTTP 状态、耗时；不记录 Cookie、Bearer 或密码。任务事件保存 job_id、generation、投递/执行次数和错误码。用户输入、连接串和内部堆栈不放进响应。

本轮实际修复：Alembic 自动迁移把组合唯一键放在子表之后，真实 PostgreSQL 拒绝；把唯一键移到外键创建之前，downgrade 反向调整，最终完整升降级通过。Celery Redis extra 要求 redis<6.5，修正为 6.4.0 后 pip check 通过。旧浏览器测试提前读取路由，加入 URL 到达断言；中文版对话框测试改用 Escape，并验证关闭。
