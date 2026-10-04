# FlowDesk 验收记录（当前结果）

**阶段一通过（2026-10-04，Asia/Shanghai）。完整 F01—F04 尚未完成。**

实现提交：`3ced4bd27424db2e4ac73586e185cd882ed363d6`；本地独立仓库，未推送远程。以下本次结果取代文末保留的早期阻塞记录。

## 本次环境与结果

Windows；Python 3.14.7，项目 `.venv`；Node 24.19.0；pnpm 11.25.0；真实 PostgreSQL 18.6，本机 55432 端口，独立 `flowdesk` / `flowdesk_test`。应用用户不是超级用户。数据库通过 SCRAM 认证，仅监听 127.0.0.1。

后端：FastAPI 0.142.2、Pydantic 2.13.5、SQLAlchemy 2.1.3、Alembic 1.20.0、Psycopg 3.3.6。前端：Vue 3.5.43、Vue Router 4.6.4、Pinia 3.0.4、Element Plus 2.14.7、TypeScript 5.9.3、Vite 7.3.6、Playwright 1.63.0。完整依赖版本与 Windows wheel SHA256 已锁定。

| 编号 | 完整职责状态 | 本次实现与验证 | 证据 |
| --- | --- | --- | --- |
| F01 | 进行中，阶段一通过 | 登录/退出、空间切换、成员权限、工单创建/分页列表/详情；浏览器建单刷新可见，独立会话跨空间读取 404；提交人仅查看本人工单 | `evidence/pytest.xml`、`evidence/playwright.json`、`permissions.md`、截图 |
| F02 | 进行中，基础约束通过 | 5 表模型与迁移；唯一、检查、组合外键；PostgreSQL 拒绝 8 类违反约束的写入；迁移升降级、模型一致性和种子幂等通过 | `evidence/database-roundtrip.txt`、`evidence/migration-check.txt`、后端测试 |
| F03 | 未开始 | 仅完成 Celery / Redis 的 Windows 依赖解析；没有 Worker 运行证据 | `evidence/dependency-preflight.json` 不是任务验收证据 |
| F04 | 进行中，本机阶段一通过 | 虚拟环境、锁文件、随机密码种子、配置示例、启动脚本、26 项后端测试和 2 项浏览器测试通过，类型检查和构建通过 | 锁文件、README、scripts、测试报告 |

## 实际执行命令

```powershell
# 根目录：依赖与迁移
& .venv/Scripts/python.exe -m pip install --require-hashes -r backend/requirements-win.lock
& .venv/Scripts/python.exe -m pip check
& .venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
& .venv/Scripts/python.exe -m alembic -c backend/alembic.ini check
& .venv/Scripts/python.exe scripts/check_database.py
./scripts/start.ps1

# backend 目录
& ../.venv/Scripts/python.exe -m pytest --junitxml=../docs/evidence/pytest.xml -q

# frontend 目录
node node_modules/vue-tsc/bin/vue-tsc.js --noEmit
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test
```

- `pip check`：No broken requirements found，见 `evidence/pip-check.txt`。
- Alembic：No new upgrade operations detected，修订 `d766290986c1`。测试库 `downgrade base → upgrade head → check` 成功。
- 种子重复执行前后均为 users=5、workspaces=2、memberships=5、tickets=3，见 `evidence/database-roundtrip.txt`。
- pytest：**26 passed, 1 warning in 16.02s**。覆盖三角色正常建单、未登录、跨空间读写及伪造空间、同空间他人工单、成员管理权限、最后管理员保护、非法负责人、角色与撤权即时生效、过期/停用/退出/轮换会话、Origin、CSRF、分页、输入错误和数据库约束。
- Playwright：**2 passed (4.8s)**。真实页面、真实后端、真实数据库；独立浏览器上下文越权 404；390px 登录页无横向溢出。
- TypeScript 类型检查通过；Vite 构建通过（1636 modules transformed，7.01s）。主 JS 约 1.05 MB，仍有 chunk size 提示，尚未优化按需加载。构建耗时不是性能基准。
- 一键启动在桌面账户下成功复用已有服务并执行迁移、种子；后台新进程分支尚未单独验收。

截图均已打开检查：`evidence/ticket-list.png`、`ticket-detail.png`、`permission-denied.png`、`login-mobile.png`。实际 OpenAPI：`evidence/openapi.json`。错误包含 code、message、request_id，不返回数据库堆栈。密码与 Cookie 明文不进入版本库。

## 已修复、限制与下一阶段

已修复 Windows Python 3.14 异步驱动事件循环、含空格路径的 Alembic 分隔符、pnpm esbuild 构建许可和跨账户数据库状态检测。Git 元数据的所有权已修复，`git fsck` 通过；原元数据备份保留在被忽略的 `.local/git-sandbox-backup`。未修改全局 Python、系统服务或全局 Git 配置。

pytest 的 1 条警告来自 Starlette 对 HTTPX TestClient 集成的弃用提示；当前测试通过，后续需关注 httpx2 迁移。

未实现 / 未验证：筛选、评论附件、看板、状态机、审计同事务、乐观锁、请求幂等；Redis 限流、CSV 导出、outbox 扫描、有限重试与人工恢复；集成令牌；Nginx、Compose、Linux Worker、远程 CI、备份恢复演练。真实并发和审计回滚测试属于下一阶段，当前未验证。未测吞吐、延迟或容量，无性能结论。

下一阶段先完成 F01 / F02，并验收真实 PostgreSQL 并发和回滚，再进入 F03。当前没有把基础阶段的成功当作完整 F01—F04 通过。

学习入口：`backend/app/security.py`（会话和 CSRF）、`workspaces.py`（成员权限）、`tickets.py`（可见性和创建事务）、`models.py`（组合外键）、`frontend/src/api.ts`（请求错误）、`views/CreateTicket.vue`（表单）。正常 / 失败链路和三项练习见 README。

---

# 以下为早期预检历史（已被上述结果取代）

记录日期：2026-10-04（Asia/Shanghai）。本文件记录真实执行状态，不代表功能已完成。

## 当前阶段与关卡

当前处于阶段一的环境预检。项目目录初始为空，不是 Git 仓库；未覆盖任何已有项目文件。用户要求先核验 Python 与依赖兼容性并锁定版本，再建项。因此暂未初始化仓库、安装依赖、生成应用或锁文件；仅保存预检记录与实施清单。

提交版本：无，尚未初始化 Git。

| 编号 | 当前状态 | 阶段一实现范围 | 验收要求 | 实际结果与证据 |
| --- | --- | --- | --- | --- |
| F01 全栈业务 | 未开始 | 会话登录/退出、工作空间成员角色、工单创建/分页列表/详情及 Vue 页面 | 浏览器登录建单；刷新后可见；另一空间用户无法读取；提交人仅查看自己工单 | 未验证；应用尚未建立 |
| F02 数据一致性 | 未开始 | SQLAlchemy 模型、Alembic 初始迁移、唯一/检查/组合外键约束 | 在真实 PostgreSQL 验证成员唯一、角色合法、工单创建人与负责人属于当前空间 | 未验证；数据库尚未就绪 |
| F03 可靠任务 | 未开始 | 后续任务阶段实现 | jobs/outbox 同事务、扫描补发、有限重试、失败终态与人工恢复 | 未验证；本阶段不提前加入 Celery Worker |
| F04 工程交付 | 进行中（环境预检受阻） | 隔离环境、锁定依赖、种子数据、配置示例、启动说明、pytest 与 Playwright | 可复现启动、真实 PostgreSQL 测试及浏览器流程 | 仅完成本机检查；见 [环境预检](evidence/environment-preflight.md) |

## 阶段推进规则

1. 解除依赖预检阻塞，确定兼容 Python 和依赖版本，生成真实解析的锁文件；不修改全局 Python。
2. 完成阶段一并实际执行 PostgreSQL 与浏览器验收，保存命令、环境、提交版本、结果和证据。
3. 阶段一通过后，补齐筛选、评论附件、看板、状态机、审计事务、乐观锁、请求幂等，以及真实事务并发和回滚测试。
4. 上一阶段通过后，再实现 Redis 限流、CSV 导出、outbox、Linux 容器 Worker、有限重试和人工恢复、限范围集成令牌。
5. 完成 Nginx、Compose、CI 和独立环境备份恢复演练；CI 文件存在不等于 CI 已运行通过。

目前没有执行任何应用测试、数据库测试、浏览器流程或性能测试。所有性能数字均未测量。
