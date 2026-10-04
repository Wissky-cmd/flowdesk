# 环境预检证据

日期：2026-10-04（Asia/Shanghai）。当前预检已通过，下文阻塞记录作为历史保留。

## 本分支续接结果

通过正常审批流程，联网预检成功执行，此前 404/503 未再出现，没有绕过审批。

- Python 3.14.7 Windows 二进制解析通过：`dependency-preflight.json` 含 Celery/Redis；`backend-preflight.json` 为阶段一含 SQLAlchemy asyncio extra。Windows 可安装不代表 Linux Worker 已验证。
- 后端生成版本锁和 Windows wheel SHA256 锁，安装在 `.venv`；pip check 与关键包导入成功。前端生成 pnpm 锁文件、显式允许 esbuild 构建后安装成功，类型检查和生产构建通过。
- 从 EDB 下载 PostgreSQL 18.6 固定包：`https://sbp.enterprisedb.com/getfile.jsp?fileid=1260609`；384620317 字节，SHA256 `e2246ba91d22345bc3d017586c09ede52d9df180b1eeb480f050445f1cad84e2`。这是本次下载复现校验值，不是发布方签名。
- `.local` 保存二进制、数据和随机本机凭据，SCRAM 认证，127.0.0.1:55432，独立开发/测试库，不注册系统服务。
- 默认 ProactorEventLoop 无法运行 Psycopg 异步连接，项目内 `app/runtime.py` 改用 SelectorEventLoop；迁移、种子、服务器均实际验证。
- 数据库初次启动在沙箱报 restricted token 错误，正常审批后以桌面账户启动成功。改用认证连接检查就绪，避免跨账户进程检测误判。
- 后端 26 项测试、浏览器 2 项测试通过；详见 `../acceptance.md`。后续阶段未开始，性能未测量。

实现提交 `3ced4bd27424db2e4ac73586e185cd882ed363d6`。以下历史“无锁文件 / 未建项”不代表当前状态。

## 已执行的只读检查

工作目录：`E:\my_project\FlowDesk 团队工单与服务管理平台`。

```powershell
Get-Location
Get-ChildItem -Force
git status --short
& 'E:\Python\Python314\python.exe' --version
& 'E:\Python\Python314\python.exe' -m pip --version
& 'E:\Python\Python314\python.exe' -m pip list --format=json
node --version
Get-Command python,py,node,npm,docker,psql,git,uv -ErrorAction SilentlyContinue
Get-Service *postgres*,*docker* -ErrorAction SilentlyContinue
py -0p
```

结果：

- 目录初始为空；`git status` 返回不是 Git 仓库。
- 默认 Python：`E:\Python\Python314\python.exe`，实际版本 3.14.7。
- 该解释器只有 pip 26.2.1，尚无项目依赖。
- Node 实际版本：v24.19.0。运行时附带 pnpm，但 PATH 未发现 npm。
- PATH 未发现 docker、psql、uv；服务检查未返回 PostgreSQL/Docker 服务。该结果不等于全盘排除所有便携安装。
- `py -0p` 返回旧的 Python 3.13 注册路径 `E:\develop\Python\python.exe`，执行该路径失败；不能据此认为 3.13 可用。
- 应用自带的另一 Python 是 3.12.14，检查的后端包中只有 Pydantic 2.13.5，无法直接作为可用的 FlowDesk 后端环境。
- 未改变全局解释器、PATH、pip 设置或系统服务。

## 依赖兼容性预检阻塞

初次在默认沙箱执行 `python -m pip index versions fastapi`，连接 PyPI 返回 WinError 10013。因此其随后出现的“无匹配版本”不是依赖不兼容的证据。

随后申请执行以下联网只读安装预检：

```powershell
& 'E:\Python\Python314\python.exe' -m pip install --dry-run --ignore-installed --only-binary=:all: --report "$env:TEMP\flowdesk-compat.json" fastapi 'pydantic>=2,<3' 'sqlalchemy>=2,<3' alembic 'psycopg[binary]' pydantic-settings uvicorn httpx pytest pytest-asyncio celery redis
```

命令未执行。自动审批服务报错：

```text
Automatic approval review failed: unexpected status 404 Not Found
Model "codex-auto-review" is not supported by any configured account in this group
url: https://ai.xxcy.shop/responses
request id: 55572026-da5b-45ef-af0f-f2ddf20f2747
```

这是审批服务故障，不是依赖兼容性结论，也不是安全性否决。未绕过审批。随后为排障访问官方文档也因相同审批故障未执行。

只读检查配置确认当前 `model_provider = custom`，服务地址为 `https://ai.xxcy.shop`；配置文件中未显式设置 `approval_policy`、`approvals_reviewer` 或 `sandbox_mode`。没有读取或记录密钥。

## 服务商修复通知后的重试（2026-10-04）

用户告知服务商已修复后，通过原审批流程连续尝试两次相同的依赖兼容性预检。两次均在命令启动前失败，错误改为：

```text
Automatic approval review failed: unexpected status 503 Service Unavailable
Service temporarily unavailable
url: https://ai.xxcy.shop/responses
request id (first): fea2b2d8-2b15-463b-82ba-63d132023125
request id (retry): 19690b16-1d3a-49c9-9dfa-de08b56fa2db
```

该错误变化不能证明审批模型已经可用。未执行依赖安装、兼容性解析或应用测试；仍需服务商检查审批请求的服务可用性。

## 恢复后的待执行项

1. 由服务商/应用配置维护者修复审批模型支持，再重跑依赖预检。
2. 核验 Python 版本要求与二进制轮子可用性，同时检查 Celery 在目标 Linux 容器中的支持；Windows 上可安装不代表 Worker 受支持。
3. 项目内创建虚拟环境并锁定全部传递依赖；前端生成包管理器锁文件。执行安装、`pip check`、导入检查与前端构建。
4. 准备独立 PostgreSQL 开发库和测试库；不使用 SQLite 代替真实数据库验收。
5. 记录最终运行版本和实际输出；当前无兼容性报告或锁文件，不宣称已锁定。
