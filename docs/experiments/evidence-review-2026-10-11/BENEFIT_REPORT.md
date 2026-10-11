# Knowhere Mac 真实 DeepSeek 确认实验：最终收益报告

结论：本次冻结样本不能确认 `review_evidence` 提高充分交付率。两组均确认充分交付 52/72；含未知状态的配对差异范围为 0 至 +2.78 个百分点，包含零。Review 的已知用量更大、记录延迟更长、连接失败更多，但费用缺失与主机/网络干扰使它们不能作为完整成本或干净的生产因果比较。

状态：144 个原始回合、真实盲评、三次新鲜负控制、汇总、来源审计和主 agent 审阅已完成；不重发失败 ID、不重试评分到通过。归档与发布回执见 `RELEASE_VERIFICATION.md`。原始 `RESULTS.md`、summary、独立算术草稿和失败记录均保留，不用本报告覆盖它们。

## 题集来源、协议和比较范围

这是我们自行构建并冻结的检索题集，不是官方 benchmark。规范原文来自官方 RFC：完整语料为 RFC 2119、8259、7493、9000、9001，题目和要求由项目构建。确认集 24 题，20 道可回答、4 道含缺失 operational measurement 的部分不可回答题；48 个冻结 requirements，JSON/QUIC 两个文档族。每题 3 次、两组，共 144 回合（每组 72）。开发 6 题×1×2 与确认题分开；实验留出不意味着模型预训练未见公开 RFC。

机械切分完整原文，不按 gold 选段。Gold SHA-256 为 `2204af014e546eb13a748376efc325ccbac92a5301b7a89c97660a44335e7d67`。被测 revision 为 `6c12e6971cffe900aec98805a78e35d55aca9239`，402 个 runtime source fingerprints 在所有回合和盲评结束后核对无变化；后续文档提交不是测量 revision。

双方共享真实 retrieval core、PGlite、scope 和 exact full-read receipts；唯一组间开关是 `review_evidence`。每次真实请求均 `deepseek-flash`、thinking enabled、reasoning_effort max、max_tokens=393216；HTTP timeouts null、retries=0，无本地 DeepSeek 步数/时间/金额/输入输出字节预算。两次审查、一次纠正和 schema/source/fingerprint 检查仍是流程边界。生产默认限制和 default-off 没有更改。

## 全分母质量结果

先在每题内平均三次重复，再对两组配对；以下范围是未知状态的保守算术界，不是置信区间或显著性检验。

| 指标 | baseline | review |
|---|---:|---:|
| 冻结回合数 | 72 | 72 |
| 确认充分交付 | 52/72 | 52/72 |
| 交付失败（APIConnectionError） | 2 | 5 |
| 语义评分未知（含交付失败） | 2 | 7 |
| 充分交付状态未知 | 0 | 2 |
| 充分交付率保守范围 | 72.22% | 72.22–75.00% |
| 仅可回答题确认充分交付 | 52/60 | 52/60 |
| 语义 requirement coverage 题内宏平均范围 | 79.17–81.94% | 76.39–86.11% |
| Literal gold-span recall 题内宏平均 | 79.17% | 79.17% |

充分交付的 review−baseline 配对界为 **0 至 +2.78 个百分点**；语义覆盖差异界为 −5.56 至 +6.94 个百分点。原 summary 因未知评分把完整点差报告为 unknown，独立算术补充界不替换原 unknown。交付失败不自动证明潜在证据语义不足，但实际没有充分交付；未知不是零，也不是通过。Literal recall 只验证字面跨度，不能代替语义蕴含。

JSON 的确认充分交付 baseline 25/36、review 26/36；QUIC 27/36、26/36。只有两个文档族，不能声称生产总体、跨领域或 thinking 单因素收益。部分缺失题保留在主分母，相关规范文字不支持不存在的实测数据。

## 审查声明与纠正的真实分母

公开 review 状态为 sufficient 51、insufficient 4、unverified 12、公开响应缺失 5；有效最终公开审查 55/72（76.39%）。12 个 unverified 的原始原因均为 `Exploration ended before final evidence was verified.`。

- False-sufficient：0/49 个独立可评分的 sufficient 声明，另外 2 个声明评分未知。不能写成全部 51 个都正确。
- False-insufficient：0/4 个独立可评分的 insufficient 声明。原 summary 的“0 among 52 independently sufficient delivered packets”采用另一分母，不能与 0/4 混写。
- 有完整公开计数的回合合计 4 次纠正；5 个失败 review 回合的公开尝试/纠正计数缺失，保留 null。55 个可评首次快照中，51 初始充分、4 初始不足、0 未知；这 4 个独立初始不足且有公开纠正计数的回合最终救回 0，救回且改变证据 0。
- **4 不是所有纠正活动的完整总数。** 失败的 `rfc-held-023:1:review` 与 `rfc-held-024:2:review` 各有一次已返回、schema-valid 的 reviewer 不足判定，并继续 explorer 纠正请求；两者无最终公开计数、无 eligible blind first-packet。保留这两次额外活动与未知，不能把 reviewer 自报不足当独立标签，也不能并入四次完整配对的救回率。

共观察到 61 次 reviewer 调用：59 次位于有返回响应的回合、2 次位于上述失败回合。没有把失败回合的 reviewer 用量剔除。有效审查、精确引文、真实 full-read receipts 都不等于语义充分性真值。

## 用量、cache 和日期费用

| 角色 | calls | 已观察 tokens 小计 | cached input | uncached input | completion（含 thinking） | 已知日期费用小计 USD | 缺失用量 calls |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline retrieval / explorer | 539 | 16,328,346 | 2,317,440 | 3,126,692 | 10,884,214 | 7.006484520 | 2 |
| review retrieval | 705 | 24,279,001 | 4,242,176 | 5,709,284 | 14,327,541 | 9.465643728 | 5 |
| review explorer | 644 | 23,232,383 | 4,117,632 | 5,038,033 | 14,076,718 | 9.214088646 | 5 |
| review reviewer | 61 | 1,046,618 | 124,544 | 671,251 | 250,823 | 0.251555082 | 0 |
| 另计盲评（含 controls） | 155 | 2,148,709 | 614,396 | 1,399,569 | 134,744 | 0.292624938 | 0 |

**两组完整检索费用和用量均未知。** 以上是已观察的小计，不是全部费用或账单；不以两组小计计算“完整成本增幅”或每额外充分回合的成本。已捕获 reviewer calls 的用量完整，但失败 episode 的完整角色核算仍保守未知；盲评用量完整且与检索开销分开。

所有可核算调用的 UTC 起止日期同为 2026-10-11（Sunday）。该版本价格每百万 cached/uncached/output tokens 为 USD 0.003/0.15/0.6，只用于匹配日期；缺失响应/usage 的七次调用和 provider-side billing 仍未知。Reasoning token metadata 是 completion 的子集，不重复计入总量或费用。

## 两个计时口径与系统级失败

| 口径（秒，mean / p50 / p95） | baseline | review |
|---|---:|---:|
| 原 recorded `time.perf_counter()` | 716.907 / 279.651 / 2799.529 | 966.764 / 294.459 / 3971.227 |
| 独立 UTC 起止差 | 729.685 / 279.652 / 2799.532 | 992.319 / 294.459 / 3971.231 |
| UTC−recorded 大于 1 秒的回合 | 1 | 2 |

两口径均保留全部 72 个回合且无缺失时长。分位数用线性插值；不改写原 duration。Mac 于 2026-10-11 12:28:11 +08:00 Clamshell Sleep 922 秒，12:43:33 DarkWake。三个在途失败与其重叠，UTC 比 recorded 多约 920 秒；更早和后来的失败不都与睡眠重叠。没有记录底层异常，重叠不能证明唯一因果。进程绑定的防空闲睡眠断言不能阻止合盖；未修改全局电源配置。

用户在两次 13:29 UTC 失败后报告刚切换网络。这是可能的共用传输干扰，切换时刻未独立验证，也不能作为所有失败的唯一原因。保留七个 APIConnectionError、缺失用量和原分母，不把连接异常直接归罪于模型质量。

另外，`rfc-held-024:2:review` 从 10:09:50 至 13:29:47 UTC，约 **3 小时 20 分钟、76 次调用**，最终因连接错误结束。它已完整读完全部 183 个允许范围 units，12:14:28 起收到 source-exhaustion hint，仍反复搜索/选择约 75 分钟。HTTP 成功只证明请求活着，不证明证据持续进展；这是冻结工作流的实际长时未收敛/未交付、系统级可用性和终止设计失败，独立于最后可能的网络切换。

该反馈只在 prompt 中提示，不强制终止；无本地上限不能保证收敛。不追设三小时 timeout、不篡改冻结评分；有限时间未收敛不证明永远不可能结束，也不能隔离归因于 thinking、DeepSeek 或 reviewer。Baseline 也观察到长时回合。另一个 `rfc-held-023:1:review` 约 16.6 分钟，在十次成功响应（含 reviewer）后下一 explorer 请求失败，不能与三小时案例混为一谈。

Stop reasons：baseline finished 56 / no_tool_call 14 / no_response 2；review 55 / 12 / 5。No_tool_call 保留为真实流程终止，不解析伪工具文字补救，不改标为 token 截断；来源审计未观察到 provider length finish。

## 盲评、审计及解释局限

152 个去重 arm-blind 包加 3 次新鲜真实语义负控制，共 155 次评估调用。三次控制均辨识：pilot 日志保留 30 天有支持；production approval 完成日期和同比吞吐增长没有支持。两份真实输出因 `invalid_source_span_range` 无效，保留原输出和未知，不重试。Gold 固定且 judge 不见组别/公开审查 verdict，但 judge 与 explorer/reviewer 同属 DeepSeek 家族，存在相关错误；负控制通过不保证全面可靠。

独立算术核对完整日程、唯一启动 ID、input hashes、盲映射、claims、corrections、literal ownership、provider 参数/cache/日期费用和两个时钟。Deterministic source audit 144 记录、402 指纹、61 schema-valid reviewer 输出、零 audit errors，只验证出处和契约，不构成语义真值。没有人类全量裁决、p-value 或总体显著性结论。

Explorer 每动作重建 fresh system/user prompt，并非原生 assistant/tool/reasoning 会话；上一动作私有 reasoning 不传下去。两组共享该架构。实验包含真实检索核心/公共 projection/PGlite，不包含 HTTP 鉴权、计费、上传解析 workers、live Cursor、native PostgreSQL 并发或生产流量。

历史 300 回合（121/150 对 118/150，另存事后敏感性两组 124/150）、两个新开发协议、环境 smoke 和本次确认分别保留。跨历史轮次同时变更 thinking、资源、lossless spans 和 scope feedback，不能把差异归于一个因素；开发 5/6 对 5/6 和生产 CI/CodeQL success 不证明本次检索收益。生产 feature 仍为 `d4d32ad74091b4040e1a1e8d7dae10f6a5b222c1`，实验代码未合入生产。

## 归档与失败保留

五份 Mac 阶段归档共 123 个成员，size/hash、每成员 hash、安全相对路径及私有字段检查通过。Heldout 31 成员归档 SHA-256 `2d41a923707a48e5a0b66115f0af4b72de61a6b16a3941874fee15ba62507f5b`。原 scanner 退出 1 的 132 条候选逐项证明为 protocol 中对应历史 revision 的 source SHA-256；原失败仍失败，未改 allowlist/config/history。

原 archive helper 因自身源码的引号内 PEM 检测字符串而误报，dependent report helper 同时失败。保留原 exception/exit 和 source hash；模型工作结束后仅离线修复 export guard，不做路径豁免。18 guard + 18 accounting tests 通过、Ruff 通过；首次 pytest 的无关 PostgreSQL/libpq 插件启动失败另存摘要，未伪称其原终端 traceback 已归档。修复后新建 heldout archive，不覆盖原四份 immutable archives。

补充 release archive 保存原 helper 失败/修复、scanner 原始结果和逐项分类、五归档验证、独立 accounting/tools/tests、睡眠/网络观察和最终两个 PR 响应。完整补充归档再经全成员核验与扫描；最终自验证回执以归档外 sidecars 保存，避免声称归档能包含自己最终 hash。发布只修改实验分支文档/证据，正常提交/推送，不 merge、force-push 或改 main。
