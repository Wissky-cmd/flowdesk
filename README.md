# FlowDesk 团队工单与服务管理平台

面向学习与作品展示的模块化单体。已实现登录、空间权限、工单全流程、筛选、评论附件、看板、任务中心、有限重试与集成授权。交付 Compose/Nginx/CI 和备份恢复脚本。实际验证边界见 [验收记录](docs/acceptance.md)：Windows 本机功能通过，真实 Redis、Linux Worker、容器部署与远程 CI 尚待运行环境验收。

## 当前环境

已实测 Windows、Python **3.14.7**、Node **24.19.0**、pnpm **11.25.0**、PostgreSQL **18.6**。后端完整版本见 `backend/requirements.lock`；Windows 3.14 二进制包 SHA256 见 `backend/requirements-win.lock`；前端完整版本由 `frontend/pnpm-lock.yaml` 锁定。

Psycopg 在 Windows 上需要 Selector 事件循环，入口 `backend/run.py` 与迁移、种子入口统一使用 `app/runtime.py`。未修改全局 Python。Celery 5.6.3 / Kombu 5.6.2 的 Redis 扩展要求 redis<6.5，客户端锁为 6.4.0。Linux x86_64 哈希锁文件已完成平台解析，Linux 实际运行尚未验收。

## 本机直接使用

在项目根目录的 PowerShell 执行：

```powershell
./scripts/start.ps1
```

访问 <http://127.0.0.1:5173>。当前本机依赖与数据库已准备好。此 Windows 环境无 Redis/Linux Worker，`.env` 明确关闭登录限流；任务中心可以入库排队，但自动消费需要下面的 Linux 部署。浏览器测试会直接运行真实任务函数来验收 CSV 页面，这不等于队列验收。

| 邮箱 | 空间 | 角色 |
| --- | --- | --- |
| admin@flowdesk.example | 产品与研发 | 管理员 |
| agent@flowdesk.example | 产品与研发 | 处理人员 |
| alice@flowdesk.example | 产品与研发 | 提交人 |
| bob@flowdesk.example | 产品与研发 | 另一提交人 |
| other@flowdesk.example | 客户支持 | 管理员 |

本机演示密码随机生成，保存在 `.local/credentials.json` 的 `seed` 字段。在终端查看：

```powershell
(Get-Content .local/credentials.json -Raw | ConvertFrom-Json).seed
```

种子数据重复执行不会改密码、重置权限或覆盖工单；更换 `SEED_PASSWORD` 只影响尚未创建的账户。

## 新环境安装

```powershell
& 'E:\Python\Python314\python.exe' -m venv .venv
& .venv/Scripts/python.exe -m pip install --require-hashes -r backend/requirements-win.lock
Set-Location frontend
../scripts/pnpm.ps1 install --frozen-lockfile
Set-Location ..
```

`scripts/pnpm.ps1` 优先使用本机 pnpm，否则使用此机器已有的 Codex 捆绑运行时；其他机器请自行准备 Node 24 和 pnpm 11.25.0。只锁版本的 `requirements.lock` 不代表其他平台已经通过安装测试，Windows 哈希锁不用于 Linux。

数据库可以使用现有 PostgreSQL，为本项目单独创建 `flowdesk` 和 `flowdesk_test`，复制 `.env.example` 为 `.env` 并替换连接信息。应用数据库用户无需超级用户权限。

本项目另提供 Windows 便携数据库方案：从 [EDB 固定下载链接](https://sbp.enterprisedb.com/getfile.jsp?fileid=1260609) 下载 PostgreSQL 18.6 包到 `.local/postgresql.zip`，执行 `python scripts/local_db.py`。脚本校验下载包 SHA256，在项目内初始化集群，以 SCRAM 密码认证，仅监听 `127.0.0.1:55432`，不注册服务。该下载包的本次 SHA256 记录在脚本和预检证据中；它不是发布方数字签名。

```powershell
& .venv/Scripts/python.exe scripts/local_db.py
& .venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
./scripts/seed.ps1
```

手动启动，分别在两个终端执行：

```powershell
# 后端，项目根目录
& .venv/Scripts/python.exe backend/run.py
# 前端，另一个终端
Set-Location frontend
../scripts/pnpm.ps1 dev
```

OpenAPI 文档：<http://127.0.0.1:8000/docs>。页面通过 Vite 将 `/api` 代理至 FastAPI。Cookie 写操作要求允许的 Origin 与 `X-CSRF-Token`；Swagger UI 不代替正常页面登录流程。

`.env`、`.local`、`.venv` 均被 Git 忽略。仅本机 HTTP 开发设置 `COOKIE_SECURE=false`；HTTPS 部署应设为 true，并配置精确的 `ALLOWED_ORIGINS`。

## 验证

先启动前后端与 PostgreSQL，然后执行：

```powershell
./scripts/verify.ps1
```

独立命令与证据见 [docs/acceptance.md](docs/acceptance.md)。pytest **会清空 TEST_DATABASE_URL 指定测试库的业务表**，只允许名称以 `_test` 结尾且与开发库不同的数据库。不要使用存放重要数据的库。测试用 Alembic 建表，不使用 SQLite 或 `create_all`。

Playwright 优先使用本机 Chrome / Edge；没有时在 frontend 运行 `../scripts/pnpm.ps1 exec playwright install chromium`。浏览器测试向开发库创建一条标题以“浏览器验收”开头的工单，便于直接查看。性能未测量。

停止数据库：`& .venv/Scripts/python.exe scripts/local_db.py stop`。手动启动的前后端用 Ctrl+C 停止；脚本后台启动的进程编号见 `.local/processes.json`，日志见 `.local/*log`。

## 代码导航与学习

- `backend/app/models.py`：12 张业务表与组合外键；`backend/alembic/versions`：独立、可回滚迁移。
- `backend/app/security.py`、`auth.py`：密码散列、随机会话、过期 / 撤销、CSRF。
- `backend/app/workspaces.py`：每次请求查询成员关系、角色管理、最后一位管理员保护。
- `backend/app/tickets.py`：状态机、全量筛选、乐观锁、幂等创建、审计、附件；`integrations.py`：有限 scope 令牌。
- `backend/app/jobs.py`、`job_runtime.py`：任务入口、outbox、预算、租约、原子文件发布与权限复验；`worker.py` / `dispatcher.py`：Celery 与独立投递器。
- `frontend/src/api.ts`、`store.ts`：接口错误、会话状态；`views`：业务页面。
- `backend/tests`、`frontend/tests`：真实 PostgreSQL 与浏览器验收。

正常链路：创建页 → `api.ts` 携带 Cookie / CSRF → `current_user` → `require_member` → `TicketInput` → 插入事务 → 数据库约束 → 201 → 详情页。

失败链路：另一空间用户即使知道工单 UUID，成员检查仍返回 404；同空间提交人访问他人工单，也会被包含 `creator_id` 的查询条件过滤。前端路由守卫用于交互，后端才是权限边界。

完整状态矩阵、事务边界、失败路径和学习练习见 [业务与可靠性说明](docs/workflow-and-reliability.md)。Linux Compose、真实队列测试、GitHub Actions、日志和备份恢复见 [部署说明](docs/deployment.md)。
