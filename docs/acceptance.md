# FlowDesk 验收记录（当前结果）

## 后续阶段交付（2026-10-05；优先于下方历史）

用户授权连续推进全部阶段。F01/F02 业务闭环与本机验收完成；F03 可靠任务和 F04 部署交付代码完成，但 **真实 Redis、Linux Celery、Compose/Nginx 实际运行与远程 CI 仍未验收**。本机没有 Docker，WSL 未安装，仓库没有远程。

| 编号 | 实现与结果 | 证据 |
| --- | --- | --- |
| F01 | 工单创建至验收关闭、全量搜索/筛选/稳定分页、编辑分派、评论附件、历史、状态/优先级/负责人看板、任务中心、集成授权 | `evidence/playwright.json`、`evidence/phase-two`、`evidence/phase-three` |
| F02 | 12 张业务表、组合外键；审计同事务、乐观锁、幂等；独立 PostgreSQL 连接并发恰好一胜一冲突；五类审计失败回滚；完整迁移往返通过 | `evidence/pytest-all.xml`、`evidence/migration-roundtrip-all.txt` |
| F03 | jobs/outbox 同事务、有限投递/执行预算、持久化退避、租约与旧 Worker 防覆盖、权限复验、CSV 安全、过期与人工恢复；真实 PostgreSQL + 故障注入通过 | `test_phase_three.py`；真实传输脚本 `scripts/queue_smoke.py` **未运行** |
| F04 | Windows/Linux 平台哈希锁、Compose、Nginx、GitHub Actions、请求日志；Windows 类型/构建/测试通过；独立恢复库登录与附件/CSV 下载通过 | `evidence/backup-restore.json`、`requirements-*.lock`；远程 CI **未运行** |

后端全量：**63 passed、1 skipped**，1 条 Starlette HTTPX 弃用警告。跳过项为真实 Redis 专用测试（无 TEST_REDIS_URL），没有用 mock 冒充 Redis 成功。任务函数与数据库恢复测试不等于 Linux Celery 验收。

浏览器全量：**6 passed**；新增页面视觉修正后再跑 2 项操作页回归通过，报告 `evidence/playwright-operations.json`。覆盖跨空间读取、创建到关闭、评论、附件下载、全量筛选、看板、409 草稿保留、CSV 内容、一次性令牌与撤销。工单/详情/看板在 1440/1024/768/390/320px 无横向溢出，任务中心390px、集成页320px另检。截图不保存令牌明文。

备份恢复：创建独立 `flowdesk_restore_时间_test`，备份 PostgreSQL 一致快照与私有 CSV，核对所有业务表计数、迁移版本、附件与 CSV SHA256；恢复库真实登录、工单读取、附件和 CSV 下载成功。源库未覆盖，备份与恢复库保留本地。最新时间、数量以 JSON 报告为准。

当前迁移 `9d85bcfd0217`。前端主 JS 338.03KB、CSS122.70KB，无大包告警；构建体积不是页面性能或获奖认证。`evidence/query-plans.json` 保存真实14条空间工单上的3份 EXPLAIN ANALYZE/BUFFERS，仅说明小数据查询计划。未测吞吐和容量。

### 验收命令

```powershell
# 根目录
& .venv/Scripts/python.exe -m pip check
& .venv/Scripts/python.exe -m alembic -c backend/alembic.ini upgrade head
& .venv/Scripts/python.exe scripts/check_database.py
& .venv/Scripts/python.exe scripts/backup_restore.py
# backend 目录
& ../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --junitxml=../docs/evidence/pytest-all.xml
# frontend 目录
node node_modules/vue-tsc/bin/vue-tsc.js --noEmit
node node_modules/vite/bin/vite.js build
node node_modules/@playwright/test/cli.js test
```

### 环境待验收项

1. Linux + Docker 启动 Compose/Nginx，执行真实 Redis/Celery 烟测。
2. 配置独立 TEST_REDIS_URL，执行 Lua 并发限流、窗口恢复、HTTP429；Redis 故障关闭登录已通过故障注入测试。
3. 选择 GitHub 远程并推送后运行 Actions，目前没有远程执行记录。

Windows `.env` 明确 `RATE_LIMIT_ENABLED=false`；自动消费者未运行，新导出会排队。Compose 默认启用 Redis 限流与 Linux Worker。CSV 本机执行/下载验证不代表队列已启动。

设计取舍与学习说明：[业务与可靠性](workflow-and-reliability.md)、[部署与恢复](deployment.md)。附件采用限量数据库二进制，评论复用不可变活动表，CSV 放私有持久卷，与草案的差异均已记录。

---

## 以下为阶段一与视觉重构历史

界面升级（2026-10-04）：已完成品牌视觉、响应式和微交互迭代，并通过浏览器流程、类型检查与构建。完整结果及范围见 [设计自检](design-review.md)。此轮不是 F02/F03 后续业务验收。

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
