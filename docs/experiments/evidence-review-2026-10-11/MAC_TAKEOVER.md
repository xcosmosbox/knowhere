# Knowhere Mac 接手与新实验断点

本文记录 2026-10-11 的实际恢复和验证，不代替历史收益报告，也不把开发集作为确认集。所有运行记录当前位于仓库外的 `runs/mac-takeover-20261011-2r2hML`；最终归档另附 manifest。真实失败、未知和新的协议分目录保留。

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
- 新版远端 CI、CodeQL 和 live Cursor 尚未执行，不声称历史 961 全 CI 证明本次新版通过。

## 新开发运行与确认边界

完整新语料为 RFC 2119、8259、7493、9000、9001 的原始全文。Gold SHA 为 `2204af014e546eb13a748376efc325ccbac92a5301b7a89c97660a44335e7d67`，corpus digest 为 `4fa168c54d37d8345ccd8ea6f7568acd75d6d0a0b36622235f7be229d1e1ab6f`。机械切分不使用 gold，索引 200 units、37,274 token rows。开发 6 题×1×2；确认 24 题×3×2=144 episodes，48 个冻结要求，含 4 道部分缺失事实题。

原 `provider-max-thinking` 开发已自然完成 12/12。缺失事实 review 得到第一次有效不足判定后继续搜索，最后输出非真实工具调用文字，最终 `unverified`：29 次调用、597,677 tokens、约 35 分钟。baseline 自然 finish：20 次调用、399,926 tokens、约 23 分钟。均不是被本地 step/time/费用预算中断。

另一个独立协议、独立 worktree 的 `provider-max-scoped-thinking` 增加闭合文档范围和真实 full-read receipts，双方同样得到该反馈。缺失事实配对已完成：review 12 调用、183,908 tokens、636 秒、两次有效审查、最终 `insufficient`；baseline 5 调用、37,721 tokens、78 秒。全部运行检查通过、完整 source receipts 可核对。不能从这一个开发配对声称因果收益或稳定加速。

后一个协议冻结于 `94728f6e33aa8620ab6c6fecc533bdfbef792aa6`，已在同目录完成 12/12，未补发已开始或已完成 ID。15 个去重盲包和 3 次真实语义负控制均有效；controls 全部拒绝不蕴含断言的相关引文。两组最终证据均 5/6 充分、0 未知；review 有 5 个 sufficient 和 1 个 insufficient，无 unverified，独立评分中无 false-sufficient/false-insufficient。题目简单且只有一个文档族，不能作为确认收益结论。每次真实请求 max_tokens=393216、thinking enabled、reasoning_effort max；HTTP 等待、episode 步数/时间、输入/输出字节和费用不设本地限额。两次审查/一次纠正是流程边界，400 字符 reason 等 schema 是输出契约，不是成本预算。

只有完成开发集独立盲评、三次真实语义负控制和来源校验后，才进入新冻结的留出日程。正式确认中不调整 prompt、源码、gold、判断标准或模型参数。最终必须报告全部冻结分母、未知、有效审查率、错误声明、纠正尝试和收益，并分开检索与盲评用量、cache、延迟、按 UTC 日期的估算费用；无净收益也是有效结论。
