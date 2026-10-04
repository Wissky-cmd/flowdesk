# 运行环境、性能与无障碍验收

## 本机证据（2026-10-05）

- PostgreSQL 回归：69 通过，真实 Redis 1 项在 Windows 未配置而跳过。`evidence/pytest-hardening.xml`。
- Chromium / Firefox / WebKit 功能矩阵首轮 29 通过、WebKit 键盘 1 失败；修复跳转链接 Tab 顺序并等待移动导航展现后，三引擎全部 6 项无障碍复验通过。原始矩阵 `evidence/cross-browser.json`，最终无障碍 `evidence/accessibility-final.json`；没有将首轮失败记录改写成成功。
- axe-core 4.13.0：登录、空间、工单列表、新建、详情、编辑、看板、任务、集成、成员、帮助弹窗、移动导航，三引擎 WCAG 2.0/2.1/2.2 A/AA 适用自动规则及最佳实践无违规。各页面报告在 `evidence/accessibility/`。
- 修复辅助文字对比度、主地标、区域命名、标题层级、页面标题、成员编辑焦点和跳转链接键盘顺序。保持纸白与森林绿风格、原有布局及减少动画支持。
- 自动化覆盖 Tab/Shift+Tab、主内容跳转、弹窗焦点限制/返回、移动菜单背景 inert/Escape、320px 无横向溢出。axe 的 incomplete 保留在报告中供人工核查；自动规则通过不是完整 WCAG 合规认证。真实 NVDA/VoiceOver 朗读、系统高对比与放大器仍需辅助技术人工验收，Playwright WebKit 也不等于真实 iOS Safari。

## 十万条数据实测

每次创建全新 `*_perf_test` PostgreSQL 库。100,003 条工单，80,002 条属于被测空间，正文每条合成数据 1 KiB；混合六种状态、四种优先级、负责人和创建人。通过独立真实 HTTP API，以 1 和 8 并发分别测量每种查询 40 次，包含鉴权、数据库读取、序列化与网络；测试在本机，不能外推生产吞吐或长期稳定性。

| 8 并发 P95 | 优化前 ms | 优化后 ms |
| --- | ---: | ---: |
| 首页 | 788.24 | 892.79 |
| 深分页（跳过 60,000 条） | 2349.71 | 271.20 |
| 模糊搜索 | 226.93 | 215.02 |
| 状态筛选 | 281.42 | 212.42 |
| 负责人筛选 | 379.32 | 194.53 |
| 看板汇总 | 348.64 | 399.46 |

前后测试时主机负载有波动，首页与汇总未显示提升。深分页优化为同一 SQL 快照中先对窄行计数/分页，仅加载该页正文；没有改为不精确总数。8 并发各项 P95 均在预设 1,000 ms 以内。8,001 条提交人 CSV 生成及 HTTP 下载约 920 ms、1,278,035 字节，逐行权限隔离通过；超过 10,000 条的管理员导出按预期拒绝。

原始证据：`evidence/performance-before.json`、`evidence/performance.json`，包含 EXPLAIN ANALYZE / BUFFERS、首请求、P50/P95/max/RPS。远程 CI 会独立生成其运行器上的同名报告，勿混淆机器。

运行 `scripts/performance_acceptance.py` 必须通过 PERF_DATABASE_URL 指定全新空白 `*_perf_test` 数据库；程序拒绝非空库，不清空开发/回归库，不自动删除测量库。默认测试 API 使用 18001 端口。

## 远程与容器验收流程

目标仓库 `https://github.com/Wissky-cmd/flowdesk`，独立 `codex/production-acceptance` 分支；不直接覆盖 main。实际远程运行结论与链接待 CI 执行后补录。

GitHub Actions 在 Ubuntu 24.04 执行真实 PostgreSQL/Redis、迁移往返、完整 pytest、Linux Celery 任务投递、十万条性能测试、三浏览器功能/无障碍矩阵，再启动生产 Compose 栈。失败即阻断任务，保留无秘密报告；不上传含 Cookie/令牌的浏览器 trace 或原始部署日志。

`scripts/compose_acceptance.py` 创建随机命名的隔离 Compose 项目及临时密码，验证 Nginx SPA/安全头、真实登录/工单/附件、Worker 缺席后恢复、Redis 重启后的队列处理、CSV 共享卷、服务重启后的会话及数据保留、Redis 停机登录 503 和实际 429/Retry-After。最终只移除其自建项目的容器/卷，保留本地日志，删除临时密码文件。它是一次性验收，不是生产部署入口；需要本地 8080 端口空闲。

复现：

```sh
# Linux，已配置隔离 TEST_DATABASE_URL / TEST_REDIS_URL / BROKER_URL
python scripts/queue_smoke.py
python scripts/compose_acceptance.py
# frontend；首次安装三个引擎
pnpm exec playwright install --with-deps chromium firefox webkit
CROSS_BROWSER=1 pnpm exec playwright test
```

生产公网域名、TLS 证书、真实组织数据、备份保留策略与长期压测不在一次性验收栈中配置。
