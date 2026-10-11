# Knowhere Mac 接手与确认实验收尾

本文记录 2026-10-11 至 12 日的实际恢复、验证和收尾，不代替历史收益报告，也不把开发集作为确认集。144 个正式回合和盲评已结束；结论见 `BENEFIT_REPORT.md`，发布回执见 `RELEASE_VERIFICATION.md`。运行原件位于仓库外的 `runs/mac-takeover-20261011-2r2hML`，阶段归档附 manifest；真实失败、未知和不同协议分目录保留。

## 已恢复的历史证据

恢复提交为 `69166a4db13d82e2396e8e3cb66784c6fff90080`。五个原归档和 146 个 manifest entry 校验通过，398 个源码指纹通过，300 个正式 episode 已全部恢复。原主评分仍为 baseline 121/150、review 118/150，未知分别 9/10；另存的事后敏感性分析仍为两组各 124/150，不覆盖原评分。新动态汇总工具也在原 300 回合上重算，与本机原汇总输出一致。

旧 review 的 84/150 `unverified`：48 非精确引用、5 超长说明、27 探索耗尽步骤、4 纠正后缺少有效二审。123 次 reviewer 调用均正常 stop，输出 176–911 tokens，未触及 1,024 输出上限。因此，旧记录不能支持“已发生输出截断导致未核验”的解释；thinking 的独立因果效果也尚未被测出。

## Mac 环境 ready 的证据

- 原生 arm64，macOS 26.2，Python 3.12.14，Node 22.23.1，依赖锁未修改。
- 保留旧 x86_64 BlingFire 库和失败索引；在仓库外从 Microsoft 同版 v0.1.8 源码编译 arm64 库，只用于本次新建实验环境。
- 原语料重新发布得到 765 chunks/map units、123,307 lexical token rows，索引报告与历史相同。
- PGlite 使用锁定 0.5.8 / socket 0.2.11 及原 SSL/Terminate 修复。一 worker 一库，库内串行；不是 native PostgreSQL 性能测量。
- 第一次 provider-max thinking 冒烟遇到 named `tool_choice` HTTP 400，原失败保留。明确改为 sole-pick-tool `auto` 后，新目录的两个真实回合成功，模型均为 `deepseek-flash`，usage 完整、所有运行检查通过。
- 成功 smoke：baseline 4 次调用、23,901 tokens；review 5 次调用、31,174 tokens、有效 `sufficient`，最终来源的两处引用均精确。该结果证明调用链可用，不证明收益。

## 生产修复与独立审查

生产分支从功能 head `f68cee2d2793dc4d6fa5cb9281f3d6d357826b1b` 出发，不包含实验 fixtures、raw data 或真实模型运行器：

1. `079012f8`：v2 lossless source spans，长行按 256 Python Unicode code points 分区，模型选连续片段 ID，服务端从不可变原文还原 quote；公开 citation 字段不变。legacy quote 仍必须精确，未加 fuzzy 匹配。明确 reason≤400，目标≤200；普通 cache 不变，reviewed cache 使用 v2 盐。
2. `b8fdc7a1`：修复独立审查发现的 canonical quote 放大。一个小 locator JSON 曾真实展开为 7,684,608 引用字节；生产现在在 join 前核算 UTF-8 字节，跨 facets/citations 累计≤16,384，超出则 fail closed，不截引文、不放宽语义。
3. `d4d32ad7`：适配现有 CI 的脚本化 reviewer 输入审计，使其重组真实收到的 lossless spans。预设 verdict、legacy 引用、gold 和模拟用量不变；新增删表格列仍被审计拒绝的回归。

首次独立审查确实发现上述 P3，不能写成“审查无问题”。改后在全新 DeepSeek 上下文另做一次 guard follow-up，没有建立可行动的新缺陷。两次均为同模型家族、静态代码审查，不是人类真值或 CodeQL。follow-up 的 cache 局限须明确：没有 guard 的 `079012f8` 独立版本从未推送/部署；实验绕过 application response cache，不存在从这个临时未发布版本重放已部署 v2 大报告的证据。最终含 guard 和 CI adapter 的 `d4d32ad7` 已正常快进推送到原 feature branch；没有 force-push、改写 main 或合并 PR。

## 本机回归及已知失败

- Shared evidence-review/harness/projection：161 通过（包含 adapter 回归）。
- API：最初与 worker 同时运行为 485 通过、3 失败；两者的契约工具共用 `/tmp/knowhere-api-tests`，不应并发运行。隔离复核两个存储失败均通过。完整串行 API 为 487 通过、1 失败。
- 剩余失败是 private-redirect 测试依赖真实 `example.com` DNS，当前 Mac 在 HTTP mock 前无法解析该域名；同一失败已在原功能 head 的独立干净 checkout 复现。未修改 DNS、断言或应用安全检查来变绿。
- Worker contract：342 通过。
- 受控 14 场景×3×2：首次因旧输入审计读取被替换的 `text` 字段失败，记录保留；适配后 84 回合运行检查通过。预设 false-sufficiency 负例展示“引用存在不保证语义正确”，不是 live 语义负控制。
- 生产 Makefile 范围的 pyright：0 errors；ruff `apps packages` 和 controlled script 通过。无参数的更广 pyright 另有 14 个测试文件类型问题，不等同于生产 `make typecheck` 范围，不将其隐去。
- 新 benchmark 工具和闭合范围反馈：136 tests 通过；dynamic summary self-test 通过。
- 新版生产 head `d4d32ad74091b4040e1a1e8d7dae10f6a5b222c1` 的上游 Test、Lint、Typecheck、Analyze、CodeQL、Gitleaks 均 success；CodeQL 无新增 changed-code alerts。这是本次精确 head 的新检查，不是借用历史 961 项结果。live Cursor 尚未执行。
- Fork 同 head 的前五项也 success，Gitleaks 的 current-tree scan 通过，但 all-refs Git history scan 失败：66 个候选全部来自历史三份 protocol 的 `runtime_source_sha256`。逐条按对应历史 commit 的源码字节验证均为 SHA-256 指纹，不是凭据；涉及的 `2ccb9e80`/`69166a4d` 均不是本次生产 head 或 synced main 的祖先。原远端 failure 保留，未改 scanner、allowlist 或 Git history。诊断和检查元数据已归入 `mac-validation-records`。
- 新 benchmark 的正确离线配置下四个模块再次验证为 136 passed；先前缺 libpq 的启动失败和缺 AppConfig 环境变量的 subset 89 passed/1 failed 单独保留，不改冻结测试来掩盖错误调用。

## 新开发运行与确认边界

完整新语料为 RFC 2119、8259、7493、9000、9001 的原始全文。Gold SHA 为 `2204af014e546eb13a748376efc325ccbac92a5301b7a89c97660a44335e7d67`，corpus digest 为 `4fa168c54d37d8345ccd8ea6f7568acd75d6d0a0b36622235f7be229d1e1ab6f`。机械切分不使用 gold，索引 200 units、37,274 token rows。开发 6 题×1×2；确认 24 题×3×2=144 episodes，48 个冻结要求，含 4 道部分缺失事实题。

原 `provider-max-thinking` 开发已自然完成 12/12。缺失事实 review 得到第一次有效不足判定后继续搜索，最后输出非真实工具调用文字，最终 `unverified`：29 次调用、597,677 tokens、约 35 分钟。baseline 自然 finish：20 次调用、399,926 tokens、约 23 分钟。均不是被本地 step/time/费用预算中断。

另一个独立协议、独立 worktree 的 `provider-max-scoped-thinking` 增加闭合文档范围和真实 full-read receipts，双方同样得到该反馈。缺失事实配对已完成：review 12 调用、183,908 tokens、636 秒、两次有效审查、最终 `insufficient`；baseline 5 调用、37,721 tokens、78 秒。全部运行检查通过、完整 source receipts 可核对。不能从这一个开发配对声称因果收益或稳定加速。

后一个协议冻结于 `94728f6e33aa8620ab6c6fecc533bdfbef792aa6`，已在同目录完成 12/12，未补发已开始或已完成 ID。15 个去重盲包和 3 次真实语义负控制均有效；controls 全部拒绝不蕴含断言的相关引文。两组最终证据均 5/6 充分、0 未知；review 有 5 个 sufficient 和 1 个 insufficient，无 unverified，独立评分中无 false-sufficient/false-insufficient。题目简单且只有一个文档族，不能作为确认收益结论。每次真实请求 max_tokens=393216、thinking enabled、reasoning_effort max；HTTP 等待、episode 步数/时间、输入/输出字节和费用不设本地限额。两次审查/一次纠正是流程边界，400 字符 reason 等 schema 是输出契约，不是成本预算。

开发集独立盲评、三次真实语义负控制和来源校验完成后，在 `6c12e6971cffe900aec98805a78e35d55aca9239` 冻结并执行 24 题×3×2 的留出日程，三个独立数据库 worker 库内串行。现已全数完成 144/144、每组 72、每 shard 48。152 个去重盲包加三次新鲜真实语义负控制完成，controls 全部通过；两份 `invalid_source_span_range` 输出无效并保留未知，未重试。所有原 worker/finalizer 已退出，随后才允许文档/证据提交改变 HEAD；测量仍是原 revision，402 个 runtime source 指纹全部通过。

题集是项目自行构建并冻结的 inventory，不是官方 benchmark；只有规范原文来自官方 RFC。确认含 JSON/QUIC 两文档族、20 道可回答和 4 道部分缺失题。正式确认中未调整 prompt、源码、gold、判断标准、预算或模型参数，也未补发失败 ID。

两组确认充分交付均 52/72，配对未知界 0 至 +2.78 个百分点包含零，不能确认净收益。连接失败 baseline 2/review 5；语义未知 2/7，充分交付状态未知 0/2。Review 公开 sufficient/insufficient/unverified/missing 为 51/4/12/5，false-sufficient 0/49 可评分声明（另 2 未知），false-insufficient 0/4 可评分不足声明。四次公开计数纠正救回零；另两次失败回合进入纠正、无公开计数，不当作零或独立评分样本。

已观察 tokens baseline 16,328,346、review 24,279,001；已知日期费用小计 USD 7.006484520/9.465643728，完整费用均未知。独立盲评另计 155 calls、2,148,709 tokens、USD 0.292624938 列表估算。原 recorded duration 与 UTC elapsed 均报告，不能从主机干扰下的延迟作生产因果推断。生产默认预算和 default-off 不变，实验代码未合入生产，PR 不合并。

## 确认期间的主机睡眠干扰

2026-10-11 上海时间 12:28:11，Mac 电源日志记录 `Clamshell Sleep`，922 秒后在 12:43:33 DarkWake。当时 worker/finalizer 的 `caffeinate -i` 断言存在，但防空闲睡眠不能阻止合盖睡眠。三个在途失败回合 `rfc-held-001:1:review`、`rfc-held-014:0:baseline`、`rfc-held-024:0:review` 与此区间重叠，随后记录 `APIConnectionError`；更早的 `rfc-held-003:0:baseline` 连接失败不与此区间重叠。

原失败和用量未知全部保留，未补发或剔除。没有保存底层连接异常及 provider 账单，不能宣称睡眠是唯一原因。上述三回合的 UTC 起止差比原 `time.perf_counter()` duration 大约多 920 秒；原计时数据不重写，最终报告须同时列出 UTC elapsed 和 recorded monotonic duration，并说明这不是干净的生产延迟比较。继续运行需要保持 Mac 开盖、联网；本任务未修改全局电源配置。

## 后续网络观察与长时未收敛

用户在两次 13:29 UTC 失败后报告刚切换网络；时刻和唯一因果未独立验证。后续三次失败未发现重叠的新睡眠，两个时钟差仅毫秒。七次连接失败全部保留，可能的网络/host/provider 干扰不等同于模型质量差，也不抹去之前的工作流问题。

`rfc-held-024:2:review` 用时约 3 小时 20 分钟、76 calls，完整读取 183/183 scope units，收到 exhaustion hint 后仍搜索/选择约 75 分钟，最后连接失败。这是实际系统级长时未收敛/未交付和 prompt-only 终止提示的设计局限；不追设三小时预算，不断言永远不会完成，也不单因素归因于 thinking 或 reviewer。另一个 `rfc-held-023:1:review` 约 16.6 分钟、十次响应成功后下一 explorer 失败，分开记录。两个 late-connection observations 和 failed-review-activity observation 保存在补充归档。

## 离线收尾与归档助手失败

原 source audit 完成 144 记录/402 指纹/61 schema-valid reviewer outputs，零错误。原 archive companion 在建档前被 export guard 的自身引号内 PEM detector 字符串误报拦截，退出 1；dependent report companion 也退出 1。原 traceback、source hash 和 report event 不被覆盖；没有声称存在完整旧 archiver backup。

模型工作全结束后，仅在 RUN 离线修复通用材料检测，保留 actual credential/PEM/private-field/private-directory 拒绝规则，无路径豁免或 scanner allowlist/history 改动。18 guard 和 18 accounting tests 共 36 通过，Ruff 通过；初次无关 pytest-postgresql/libpq 插件启动失败另保留摘要。纯离线 accounting 与原 summary 核对通过，不是第二位语义 judge。

原四份阶段归档不覆盖；新增 heldout 31 成员后，五归档合计 123 成员逐项验证通过，未包含 key、数据库、依赖 checkout 或 private reasoning。Recursive scanner 退出 1 的 132 findings 全部逐项核实为对应 revision 的 source SHA-256，原失败仍失败。Final supplemental release archive 另外保存辅助失败/修复、accounting、测试、审计、原扫描/分类、睡眠/网络观察和最终两 PR 响应；其自验证 sidecars 不塞入自身归档。正常文档/证据提交和推送均仅在原实验分支，San_Check 身份，不 force-push、改 main 或合并 PR。
