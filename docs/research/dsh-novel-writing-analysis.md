# dsh-novel-writing v0.5.3 静态分析笔记

分析方式：仅用 read/grep 只读分析，未安装、未修改仓库、未执行仓库内任何脚本（含 install.ps1 / install.sh / *.mjs）。本机 `~/.dsh` 下**不存在** `.agent-presets` 目录，即该插件在当前环境**未安装**；本文全部结论为源码静态事实，**未做实机运行验证**。

---

## A 块｜宿主插件工程结构

### A1 双面包声明：bundle 行 + client 面
- `package.json` L17-29 的 `"dsh"` 字段是全部扩展面入口：`dsh.bundle.patch = "./cordis.patch.yml"`（服务端 bundle patch）、`dsh.client.platform = "web"`、`dsh.client.inject = ["@deepseek-ai/dsh-client-ui-settings","@deepseek-ai/dsh-client-locale","@deepseek-ai/dsh-api-remotes"]`（客户端宿主模块注入白名单）。`exports` L11-16 暴露 `.`→`lib/index.js`、`./tools`→`lib/tools.js`、`./client`→`lib/client.js` 三个入口。`peerDependencies` L39-45 全为 `*`（cordis/schemastery/dsh-settings/dsh-home-paths/dsh-tools）——契约 item 6.1 自评为 `improvable`（"* = 不设限=不设防"）。
- `cordis.patch.yml` 全文 12 行，补丁体只有一处 `- insert:` 后跟 `- id: novel-writing` / `name: dsh-novel-writing`。即：**bundle 行 = 一个双面行，同时承载服务端服务与客户端 bundle**；同文件注释自述该行还会"把包内 agent 预设拷贝到 `$DSH_HOME/.agent-presets/novel-writing/`"。第二个 bundle 行不在此文件——工具行走**预设组合**：`agent.cordis.yml` L94-95 `- id: tool-novel / name: dsh-novel-writing/tools`。

### A2 服务端：服务注册 / 设置 / 工具 / HTTP
- **服务注册**：`lib/index.js` L87 `class NovelWritingService extends Service`，构造器 L89 `super(ctx, SERVICE_NAME)`；`SERVICE_NAME = 'novel-writing'` 定义在 `lib/host-boundary.js` L45。插件行导出 L34 `export const name = 'dsh-novel-writing'`、L37 `export const inject = [...hostInject]`（`hostInject = ['settings']`，边界层 L51），L1453-1472 `apply(ctx)` 内 new 服务、`registerSettings(ctx, NS, Config)`、`ensurePreset()`、取 `webServer`、`onLifecycle(... registerHttp)`、最后 `selfCheckHost(ctx)`。注意 L37 特意写了 `[...hostInject]` **副本**：注释说明是为了让消费方就地改写不污染边界层探测判据（契约 1.5 的输入）。
- **设置节**：`NS='novel-writing'`（L40，须匹配 dsh-settings 的 `/^[a-z][a-z0-9-]*$/`），schema `Config = z.object({...})`（L41-68）字段为 `enabled / workspaceRoot / pollMs / apiPublic / presetAutoSync / platforms(z.dict) / bindings(z.dict)`；`platforms` 每项 `{enabled, mode: union(['export','command','manual']), command, fetchCommand}`，默认预置番茄/起点/晋江/七猫四家。读取走 `readSettings(ctx, NS)`，缺席时 `Config({})` 补默认（L94-97），且注释明确"不在构造器里 ensurePreset"（因设置节在 apply 才注册）。
- **工具注册**：`lib/tools.js` L17 `import { defineTool } from '@deepseek-ai/dsh-tools'`，L19 `name = 'dsh-novel-writing/tools'`，**L22 `inject = ['tools']` 只声明硬依赖**；novel-writing 服务用 `ctx.get('novel-writing')` 探测（L29），未装 bundle 时 L31 仅 warn 并注册 0 个工具——注释 L21 明确写了"不得加入 inject，加入会使未装 bundle 的预设无法挂载"。共注册 11 个工具：`novel_list / novel_status / novel_state_update / novel_chapter_read / novel_chapter_write / novel_gate_check / novel_review_submit / novel_data_ingest / novel_publish / novel_requests / novel_request_done`，每个都用 `defineTool({name, description, parameters, output:{schema,render}, execute})`，`output.schema` 一律 `additionalProperties:false`（execute 内手工裁剪 null 字段以严格对齐 schema，见 L80-88、L132-135）。
- **HTTP 路由**：`registerHttp(webServer)`（L1236-1396）用内部 `api(path, handler)` 闭包批量注册 `kind:'exact'` 路由到 `/novel-writing/api/<path>`，共 13 条：`overview / novel / chapter / gate / request / novel-create / novel-delete / file / request-done / publish / data / preset-sync / compat`。中间件统一做四件事：`enabled=false → 503`；`isLocalRequest(req) || apiPublic` 否则 403（回环判定以 `socket.remoteAddress` 为准，Host 头仅兜底，L1406-1411）；POST 走 `sameOriginPost`（Origin/Referer 必须匹配 Host 且 content-type 含 application/json，L1418-1434）防 CSRF；body 4MB 上限（超限 413）。
- **门禁下沉服务层**：`saveChapter`（L856-886）先跑 `gateCheck` 落盘，`gate.available && gate.passed===false && !force` 直接 throw；`recordReview`（L889-922）强制 `findings.length>=2`、**verdict=pass 当且仅当 score===100 且 hardGates 为空**，并写 `10-reviews/quality-reports/chapter-XXX-review.json`；`publish`（L1029-1098）第一件事就是校验 `guardrails.release_allowed===true`。注释明确指出"release_allowed 校验已下沉服务层（与 HTTP 工作台同一收口）"——工具与 HTTP 两条入口共用同一约束。
- 其它工程细节：`atomicWrite`（L108-117）tmp+rename 原子写；`pushVersion` 递增 `this.version` 并 `emitChanged(ctx,{version,detail})`（事件名 `novel-writing/changed`）；`ensurePreset`（L163-191）以 `.dsh-bundle-version` 标记比对版本，用 staging 目录整目录原子换入，避免升级一半留下半套预设。

### A3 宿主边界层与 host-contract：解决了什么问题
- `lib/host-boundary.js` 的职责是**把 `lib/index.js` 对宿主的一切调用收口成命名包装**：导出 `z / Service / SERVICE_NAME / EVENT_CHANGED / hostInject / registerSettings / readSettings / getWebServer / registerRoute / onLifecycle / loggerOf / logWarn / emitChanged / presetRoot / presetDir`，另有 `detectHostCapabilities / contractProjection / warnCompatReport / selfCheckHost`。它还导出一张**收口映射表** `BOUNDARY_MAP`（L32-42），键 = 契约 item 编号（1.1/1.2/1.3/1.5~1.10），值 = 本文件导出符号名，供 smoke 断言"键集 ≡ 契约面 1 收口项、值全是真实导出且被 index.js 消费"。范围口径写在文件末尾 L107-110：**只覆盖 `lib/index.js` 的宿主调用 100% 收口，`lib/tools.js` 不在边界层内**（契约 item 1.11 标 `out-of-boundary-scope`）。
- `lib/host-contract.mjs` 是**纯数据机读契约**（自述"零 import、零运行时逻辑"，并诚实声明守卫"不能拦 class 声明 / export * / 非行首动态 import / 顶层副作用"）。结构：`schemaVersion:1`、`task`、`revisions[]`（修订史）、`faces[]`（6 个面）、`kindEnum[]`（31 个 kind 封闭枚举）、`items[]`（48 项宿主耦合清点，每项 `{face,item,kind,symbol,file,line,necessity,note,incident}`，`necessity` 九值枚举 required/consolidatable/adapted/optional/improvable/own/eliminated/adapted-drift/awareness）、`regionLiterals`、`presetRowConfig[]`、`ctxGetSemantics`、`clientProbes[]`、`hostSurface`。六面为：1 服务端 API、2 客户端 API、3 宿主 DOM/前端约定、4 安装注册、5 预设与 manifest、6 版本与环境。
- **双向对账**是本文最值得抄的做法，落地为两条互补口径（契约 L10-12、L183-189 自述）：
  1. `items[]` = 声明式依赖清点（人读 + 诊断消费）。每项带 `file`/`line`，且契约明确"行号以本项 `line` 字段为唯一事实源，note 不内嵌副本"——它们被"内嵌副本重基后残留成 stale"坑过（多处 note 记录该事故，如 item 1.4/1.10）。
  2. `regionLiterals` = **可机检字面量对账面**，`slotNames / serviceNames{inject,ctxGet,svcDomains,events} / cssTokens / domSelectors` 四组，由 smoke 做**双向 ⊆** 断言：源码提取面 ≡ 清单，任一侧增删必红。提取口径也写进契约自述（仅单引号字面量、DOM selector 只取 querySelector(All) 首个实参、自有 `.nv-` 前缀排除、CSS 只收 `--dsw-alias-*`/`--dsw-shadow-*`、提取前剥注释）。
- **它解决的具体问题**：宿主升级导致插件静默失效。契约 L8 与 L11 直接点名两起真实事故——`settingsNamespace` 从 dsh-settings 导出面消失（ESM 具名导入 SyntaxError 致宿主启动崩溃）、`dsh-client-connection` 的 `.api` 域对象消失（44 处 `api.<domain>` 调用面落空）。`hostSurface.versionFacts`（L320-325）把这两个断点固化成三版本标记（`settingsNamespaceExported` / `connectionApiDomainField` / `remoteNamespaceServicePackages`），并配 `versionFactOrigins` 区分"静态提取"与"注册表元数据"，明确"防注入值伪装成实测"。
- 契约还把**自身的不确定性**入册：`ctxGetSemantics.status = 'unverified'`（L255），理由是"本环境无宿主 cordis 源码可及"，并写下转 verified 的判据与 `recheck` 留痕。这是把"未确认"当一等公民处理的范例。

### A4 能力探测、版本兼容与降级
- 服务端 `detectHostCapabilities(ctx)`（host-boundary L184-219）把契约 face 1 逐项投影成运行时判据：`FACE1_PROBES`（L132-153）为每项给同步判据，返回 `{item,face,kind,sync,ok,mode,domain,service,method,detail}`；`ok=null` 进 `unprobed` 并带**枚举码**原因（`FACE1_UNPROBED_CODES`：1.4 `retired`、1.11 `out-of-boundary-scope`）；面 2~6 在 apply 期不可见，如实列进 `notCovered`（`client-api-surface / host-dom-surface / install-registration / preset-manifest / version-environment`）。函数自述硬约束：**零 await、零 import()、零网络、零 DOM 读取**，apply 期可直接调用。
- `warnCompatReport`（L251-267）：缺面时**单次** `console.warn('[nv-compat]', JSON.stringify(summary))`，摘要只含布尔/名称/版本，不含路径与 token；无缺面不输出。
- 客户端侧是另一套机制：`lib/client.js` L92-94 `window.__ModuleLoader__.load({ id:'dsh-novel-writing', factory: (require) => {...} })`（宿主单 id 注册约定，`require('react')` 只能在 factory 内），L5137 `const inject = ['slots']`——**硬依赖只有 slots**；`connection` / `locale` / `sessions` 全部降级为 apply 期 `ctx.get` 惰性探测。注释 L5130-5136 说明：旧版三服务硬声明会让插件在缺这两个服务的宿主上根本不挂载；而 `ctx.<service>` 属性访问才抛 "cannot get property ... without inject"。
- `makeHostApi(svcGet, connection)`（L772-880）是全文件**唯一特性检测点**（`.api` 回退引用恰 1 处）：返回惰性 facade，域属性每次访问重解析，**新表面优先**（`remote.settings` / `remote.session` / `remote.workspace`+`workspaces` 快照 / `remote.directoryPicker` / `remote.agentPresets`），**旧表面回退**（`connection.api.*`），皆无则 undefined；对外把新形状包成旧的 `{result:{ok,value|error}}` 约定，从而 44 处调用点零改动。`awaitWorkspacesReady`（L741-766）用 `getSnapshot/subscribe` 事件驱动等 `phase` 离开 `pending`，零轮询。
- 能力判定与降级三件套：`apiHas(domain, method)`（L1592-1595）先守卫再调用（如 `agentPresets.select` 缺失则整步跳过、`sessions.cancel` 缺失则提示 `sessionsMissing`）；`useSyncExternalStore` 型会话镜像 hook `makeSessionsHookReactive`（L1449 起）配合 `ctx.on('internal/service', ...)`（L5167-5174，**单一监听器三消费**：locale 重快照 + launcher 重 setup + hook.refresh）实现"服务后到/撤离自愈"，避免"服务后到 ⇒ 永久降级"。
- 客户端诊断面板 `lib/client.js` L2535 `D_PROBE_ITEM`、L2551 `CLIENT_PROBES`、L2610 `buildDiagReport`、L2708 `DiagnosticsPanel`，与服务端 `/novel-writing/api/compat` 单一出口对接。**注意口径**：服务端报告内所有原因字段已枚举化（`probes[].code`/`unprobed[].code`/`notCovered[].code`、`host.version=null + versionCode:'tp4-unprobed'`），人类可读文案只在客户端 i18n——目的是"报告内无自由文本"成为可机检事实，且仓内相对路径不出网关（契约 L155-163、L206-211）。
- 客户端 UI 挂载点（L5204-5236）共 6 处 `ctx.slots.inject(name, () => ctx.slots.register({name,id,order,label}, renderFn))`：`settings.section#novel-writing(order20)`、`sidebar.footer.action#novel-drawer(9)`、`shell.overlay#nv-console(25)`、`shell.overlay#novel-workspace-dialog(20)`、`shell.overlay#novel-split(25)`、`shell.overlay#novel-bind-dialog(40)`。样式为单个 `<style id="novel-writing-style">`（`NV_STYLE` + `ensureStyle()` 幂等注入、清理函数返回移除），颜色全部 `var(--dsw-alias-*, 兜底值)`（`TK` 表 L928-941）。轮询用自写 `usePoll(fn, ms, deps, enabled)`（L896-924）：in-flight 去重、deps 变更清旧数据、出错清数据留 message、enabled=false 停表，`overview` 2~2.5s、`novel` 详情按 `pollMs` 下限 500ms。
- apply 返回**清理函数**（L5239-5256）：复位控制台状态、关分栏、移除 `dsh:split-claim` claim 监听、移除 focusin 追踪器、退订 `internal/service`、移除 style——可逆性完整；另用 `window.addEventListener('dsh:split-claim')` 与其他分栏引擎互斥让位。
- 一点值得留意：契约 item 2.13 的 note 自己标注了一个**未证实前提**——宿主槽位 `label()` 的刷新依赖"宿主在 locale 变化后重渲染自身 shell"，而"宿主会重渲染"在本仓无证据。

---

## B 块｜29 个 SKILL 的商业流程

### B1 阶段流水线（输入/产出/门禁）
阶段定义在 `using-writing-workflow/SKILL.md` L261-283，共 19 个阶段（含 4 个可选/发布后阶段）。状态存 `novel-project/workflow-state.json`，字段 `current_stage / completed_stages / project_info / files / guardrails{continuity_mode,latest_passed_chapter,latest_ai_path,release_allowed,monetization_allowed,latest_drift_score,...} / statistics`（L230-258）。依赖链 L1210-1232：`work_type_selection → platform_research →（competitor_analysis / genre_selection）→ novel_confirmation → creation_planning → outline_writing → chapter_outline → content_generation →{human_ai_collaboration, quality_review, opening_optimization, novel_style_learning}`，发布运营另起 `launch_strategy → monetization_strategy / data_monitoring / reader_interaction`。

| 阶段 | 主要输入 | 产出文件 | 门禁要点（F4） |
|---|---|---|---|
| 0 work_type_selection | 用户意向 | `00-work-type.md` | 无 F4（非关键） |
| 1 platform_research | web_search 实时 | `01-platform-research.md` | ≥2 个数据来源 URL |
| 1.5 competitor_analysis | 公开信息搜索 | `16-competitor-analysis.md` | 无 F4 |
| 2 genre_selection | 平台数据 | `02-genre-analysis.md` | 无 F4 |
| 3 novel_confirmation | 题材结论 | `03-novel-info.md`（主选+备选5个） | 无 F4 |
| 4 creation_planning | 情感签名/篇幅/频率 | `04-creation-plan.md` | 无 F4；`project_info.target_words/target_chapters` 必设 |
| 5 outline_writing | 全部地基输入 | `05-outline.md`+人设+世界观+`story-bible.md` | outline-review 报告生成，Bible 不可变更事实 ≥3 项 |
| 5.5 outline_review | 大纲组 | 大纲审查报告（17 子项） | **总分须 = 100，<100 必改重审** |
| 6 chapter_outline | 大纲+Bible | `06-chapter-outlines/chapter-XXX.md`+`17-continuity/chapter-XXX-context.md` | 每章须含章节概要/详细情节/**爽点设计**/**章末钩子**；前 5 章≥4 章强钩子 |
| 6.5 chapter_outline_review | 细纲 | 细纲审查报告（11 子项） | **总分须 = 100** |
| 7 content_generation | 看护包 | `07-content/chapter-XXX.md` | 字数≥目标 80%；ledger 已更新；AI 路径非 C；6 份审查汇总=100 |
| 7.5 human_ai_collaboration | 正文 | `13-creation-logs/chapter-XXX-log.md` | `latest_ai_path` 非 null，回写 release/monetization |
| 8 quality_review | 六方并行 | `10-reviews/quality-reports/` 6 份 | **总分=100 且 15 项硬门禁全通过** |
| 9-12 launch / monetization / data / reader | 正文存量 | `14-`/`15-`/周报/互动日志 | 分别校验 `release_allowed` / `monetization_allowed` |

门禁机制本体（L1412-1430）：**F1 文件存在性 → F2 状态更新 → F3 内容最低标准 → F4 质量门禁（仅关键阶段）**，逐级检查、任一级失败即停；"关键阶段"的 F4 失败**不提供跳过选项**，门禁检查方式是"读输出文件直接验证"而非读审查摘要（L1436-1441）。门禁规则表见 L1489-1622，执行顺序见 L1624-1632。

### B2 质量审查：15 项硬门禁 + 9 维 100 分制
`quality-review/SKILL.md` 是总索引，实际由 6 个独立 agent+SKILL 并行：continuity-reviewer(25) + character-world-reviewer(25) + plot-logic-reviewer(15) + commercial-editor(10) + engagement-reviewer(18) + ai-compliance-officer(7) = 100（L14-22）。

**15 项硬门禁**（L47-65）：1 场景覆盖率=100% / 2 偏离度=0% / 3 滚动 10 章累积偏离=0 / 4 字数偏差≤±30% / 5 时间线·地点·人物硬冲突 / 6 必写场景缺失 / 7 结束状态与 context card 一致 / 8 Bible 不可变更事实被改写 / 9 Bible 改写有正式修订记录 / 10 关键伏笔逾期未回收 / 11 CCC 三要素（仅 1-3 章）/ 12 连续 3 章弱钩子 / 13 中段（40-60%）主角被动且无新变量 / 14 连续 5 章情感签名偏离 / 15 连续 10 章无中回报。任一阻断即停。归属：1-9 在 continuity-check，10+13 在 plot-logic-check，11-12+14-15 在 engagement-check（该文件 L26-29、L34-39）。

**9 维与满分要求**（L71-82）：维度1 设定逻辑性 10（世界规则自洽、力量体系一致、无"临时追加规则"、无废设定）；维度2 人物一致性 15（行为/对话/身份/关系/成长弧）；维度3 情节逻辑性 15（因果链、伏笔埋设→推进→回收、冲突升级不降级、被动主角超 3 章扣分）；维度4 时间线+数值 10（时间连续、年龄同步、战力/经济数值稳定、时间跨度合理）；维度5 结构质量 15（覆盖率 100%、偏离度 0%、信息释放节奏、章末钩子是否兑现细纲承诺、多线协调）；维度6 文学质量 8（无连续 3 句同构、感官描写>60%、口语化对话>80%、视角一致、文风稳定）；维度7 情感体验 10（情绪曲线起伏、期待感、代入感、爽点"铺垫→引爆→余韵"、情感签名履约）；维度8 平台商业化 10；维度9 AI 痕迹+原创 7。**判定（L165-173、L252-278）是二进制的：Step2 无阻断 ∧ Step3 总分=100 才通过；"99 分=不通过"，并明文禁止 Coordinator 说"差一点没关系"**。

**零容忍项**（L180-198）：覆盖率<100%、偏离度>0%、滚动 10 章有任何偏离记录、Bible 事实被改写（走正式修订流程的记录除外）、必写场景缺失、结束状态与 context card 不一致、伏笔逾期。另有四条区间型硬门禁：开篇架构（仅 1-3 章，CCC 任一缺失）；扩展留存门禁（4-10 章：钩子强度≥6/7 章为"强"、字数偏差≤±20%、Clock 仍在滴答）；中段崩坏（40-60%）；回报密度（连续 10 章无中回报）。Bible 修订有正式流程（REV-XXX 编号 + 原事实/新事实/原因/影响范围），并建议"每卷修订不超过 2 次"（L227-250）。

**质量审查细则的可操作阈值**（L387-511）：痕迹密度 ≤5% 优秀 / 5-15% 合格 / 15-30% 需优化 / >30% 不合格；直接情感表达 <3 处/章；程度副词（非常/十分/特别/极其/相当/格外/异常）每章 <10 个且不连续使用；过渡词"每 500 字 <3 个相同"，且"然后"每段≤1次、"于是"每章≤5次、"接着"/"所以"每章≤3次。`ai-compliance-check` 补充："痕迹密度每超过 15% 阈值 5 个百分点 → 扣 2 分"。

**审查防放水与审查分离**：`quality-review` L94-109 定义"每份审查报告最低标准 4/4"——≥2 个具体发现、每条引用正文原文、标注严重程度（阻断/警告/建议）、明确通过/不通过；"通过，无问题"= 无效审查、必须驳回重审（重启用更严 prompt，要求至少 3 个问题）。L560-586 明确"自我审查偏差"问题与解决方案：**必须用独立 subagent 审查**，且主会话自检与独立 subagent 评分差异 >15 分时以**较低分**为准并标注"审查一致性差异"。这是 B 块里唯一值得从元规则里拎出来的一句话：**Creator/Reviewer 绝对分离**。

### B3 与「爽点/追读/完读率」相关的可操作判据
- **钩子强度三级定义**（`chapter-outline/SKILL.md` L134-139）：强 = 揭示让读者"无法不翻页"的信息 + 制造"必须知道答案"的认知缺口；中 = 留下未解问题但冲击力一般；弱 = 自然收束无强驱动力。规则：**连续 3 章弱钩子=弃书高风险区，前 5 章至少 4 章强钩子**。硬数据被反复引用：带悬念结尾追读率高 22%、前 50 页流失 44% 读者、番茄前 200 字无钩子=80% 用户划走。
- **CCC 开篇三要素**（`opening-optimization/SKILL.md` L33-44，自述"基于 1000+ 作品研究"）：Contract 类型承诺——前 300 字内让读者感知类型归属（第 1 页）；Clock 时间压力——有时间限制的困境或风险升级中（前 10%）；Crucible 不可退出——被框入无法简单退出的处境（前 25%）。第一章结构配比：钩子开篇 100-300 字 / 人设速写 500-800 字 / 冲突引入 800-1200 字 / 悬念收尾 100-200 字；第一章字数 1500-2500。黄金开篇公式 = 环境异变 + 主角反常行为 + 致命威胁；三大钩子类型 = 身份反差 / 环境异变 / 行为反常。
- **平台差异化判据**（`commercial-check` L27-60、`content-generation` L449-527）：番茄——前 300 字出冲突、每 800 字一个微型悬念、章节长度 ≤2500 字（content-generation 写"控制在 2000-2500"）、标题须悬念型/反转型；起点——VIP 章开头必须有即时回报（禁用过渡或回顾开头）、章内制造"停留 20 秒+"沉浸点、每章至少一个"值回票价"场景、**周二为 PK 日内容质量最高**、对话:描写 = 6:4；晋江——情感描写有层次、章末有可讨论话题；七猫——前 500 字完成"冲突+人设+悬念"闭环、每 1000 字一个小高潮、情绪拉扯设计（播种期待→适度压抑→炸裂释放）、广告断点处有悬念、章节 2000-3000 字。
- **付费转化判据**：付费章开头 300 字内即时回报；**付费后 3 章爽点密度 ≥ 免费部分 1.5 倍**（`commercial-check` L71，`chapter-outline-review` L63 复述）；付费章标注钩子类型（悬念卡点/高潮前卡点/反转卡点/升级卡点）与"预期转化强度"，并列出可能导致退款的风险因素（`chapter-outline` L141-145）。
- **回报分级**：小回报每 2-3 章≥1、中回报间隔 ≤10 章（连续 10 章无中回报=读者弃书高风险）、大回报每卷末 1 次（`outline-review` L155-157；`novel-architect` 同为"小 2-3 章·中 7-10 章·大每卷末"）。
- **推荐/传播触发点**：爆款每章至少 1 个触发点；高唤醒情绪（敬畏/惊喜/愤怒）驱动分享，低唤醒（悲伤/满足）抑制分享；社交货币类型 = "推荐本章会让推荐者显得____"（`chapter-outline` L147-151）。`reader-interaction` L112-124：超级粉丝占 2% 读者但驱动 18% 消费、9 倍分享率；读者生命周期为 普通→活跃（连续追更≥5章）→付费→粉丝（累计互动≥10次）→传播者（单次强情感冲击）。
- **情感签名**：`creation-planning` L27-56 要求先定 1 个主情感（爽感驱动/紧张悬疑/情感共鸣/热血燃向/幽默解压/智识满足）+1-2 辅助情感，写入 `project_info.emotional_signature`；每章履约由审查比对，连续 5 章偏离=阻断。

### B4 数据闭环：信号→阈值→行动→调整级别
宿主侧代码实现（`lib/index.js` L1179-1223 `computeSignals`，注释自述"阈值表来自源工作流 v4.x 数据监控 skill，硬编码为参考值"）：

| 信号 | 阈值 | 严重度 | 系统给出的建议行动 |
|---|---|---|---|
| 完读率低 | 完读率 <10%（10 万字节点） | high | 触发开篇优化：重审前 3 章（opening-optimization） |
| 章节流失 | 读完率 <30% | high | 定位流失章节 → 生成章节诊断与重写建议 |
| 追读下降 | 连续 3 天降幅 >10% | high | 触发最近 3 章节奏/爽点分析 |
| 追读单日下降 | 降幅 >10%/天 | medium | 关注最新章节节奏，3 天连续则触发分析 |
| 收藏停滞 | 连续 7 天日增 <10 | medium | 书名/简介/封面优化建议 |
| 差评集中 | 同一问题 ≥3 条同类差评 | medium | 提取关键词 → 修改方案 → 回归验证 |
| 收益持续下滑 | 连续 4 周降幅 >20% | high | 止损决策框架：评估停更/改向/完结 |

- 数据入口：`novel_data_ingest` 支持两种来源——records 数组（每项必含 `date: YYYY-MM-DD`）或 `platform`（执行该平台配置的 `fetchCommand`，解析 stdout 的 JSON 行）。入库按 date 去重、滚动保留最近 730 条。
- `data-monitoring/SKILL.md` 补充指标健康标准（L25-33）：10 万字完读率>15%、20 万字>8%、三日留存>10%、每章读完率>50%、点击率>5%、退款率<3%；起点付费追读排名的达标线是"挤进同期前 20 名"。
- 预警分级（L213-243）：**黄色** = 完读率连续 3 天下降 / 日阅读人数降超 20% / 追读持续减少；**红色** = 完读率 <5% / 日阅读人数降超 50% / 连续断更超 2 天 / 大量负面评论。
- 闭环流程（L367-402）：异常检测 → 问题定位 → 原因分析 → 生成修改方案 → **必须经 ask_user_question 让用户选择（全部应用/选择性应用/暂不修改）** → 调用 content-generation 重写 → 发布 → **7 天观察期跟踪** → 评估是否继续调整。核心口径一句话："数据闭环的核心是'发现→定位→修复→验证'，不能只做前两步"。
- **调整级别**（`data-driven-optimization/SKILL.md` L31-36）：章内 → 细纲 → 大纲（须走 REV 修订流程，每卷 ≤2 次）→ 题材/立意级（仅在数据连续 2 周恶化且用户主动提出时，**不允许 AI 单方触发**）。每个对策须以"方案→影响分析→预期收益/风险"三元组经用户确认。
- **止损触发条件**（L542-551）：收入连续 4 周降 >20% / 追读连续 2 周降 >30% / 连续获推荐但数据无改善 / 完读率 <5%。止损决策框架以用户选择收口（继续加大优化 / 缩减更新准备新书 / 完结后开新书 / 直接开新书 / 再观察 X 周），并给"继续投入 6 个月预估收入 vs 弃书机会成本"的对照。

### B5 AI 参与度 A/B/C 分级
来源 `human-ai-collaboration/SKILL.md` L49-108。核心判断口径：**"不是像不像 AI，而是 AI 是不是在替代人类做创作主体"**。
- **路径 A 平台安全**：AI 仅限资料查询、市场调研、校对语法、起名灵感、要素级灵感、粗纲级辅助；**不允许 AI 生成正文段落/续写情节/生成核心对话** → `release_allowed=true`、`monetization_allowed=true`，可正常进入 launch-strategy 与 monetization-strategy。
- **路径 B 灰区**：AI 生成场景描写素材、对话初稿供改写、辅助改写部分段落，且人类完成核心剧情/情感/个性化表达、AI 素材经大幅人工改写 → 两个 flag 均置 **false**；建议仅练习/自发平台/非签约发布，想签约须大幅改稿后重新评估。
- **路径 C 高风险**：AI 生成完整章节正文初稿 / 连续多章 AI 主导 / 证据链不完整（无法自证人工参与）→ **直接阻断** launch-strategy 与 monetization-strategy；并给出财务风险提示（签约被拒、已发布作品下架、永久取消签约资格）。
- 落地刚性：结论必须**回写** `workflow-state.guardrails.latest_ai_path / release_allowed / monetization_allowed`（L325-356），原文强调"只生成日志但不回写状态，视为流程未完成"；`publish` 与 `monetization-strategy` 各自在入口校验对应 flag（`lib/index.js` L1034、monetization SKILL L24-28）。
- 配套"人味注入清单"（L242-255）：每章至少 5 项——独特比喻、不规则句式≥3 处、非视觉感官细节≥2 处、口语化对话、个人化描写、情绪留白、节奏变化、场景"脏细节"。证据链留存包写 `13-creation-logs/chapter-XXX-log.md`（人工构思记录 / AI 对话过程 / AI 输出首稿 / 改写前后对照 / 投稿前确认声明 4 项勾选）。

### B6 其它有价值的商业细节（略读所得）
`launch-strategy` 存稿公式：**安全存稿量 = 签约门槛字数 + (日更字数 × 推荐期天数) + 应急缓冲**（示例：番茄 10 万 + 4000×14 + 2 万 ≈ 18 万字）；各平台建议存稿起点 10-15 万 / 番茄 15-20 万 / 晋江 5-8 万 / 七猫 8-10 万（L49-71）。`platform-research` 对数据真实性设了硬规则：签约数据"至少 1 个官方来源"，否则必须标注"公开规则不充分，不应作强结论"，**禁止输出无来源的具体数值**（如"千字 X 元""分成 X%"），搜索关键词必须用当前年月动态生成（L86-121）。`publish-pipeline` 声明：番茄/起点/晋江/七猫**没有公开作者数据 API**，脚本化抓取有封号风险须用户知情同意；导出的 `dist/<平台>/chapter-NNN.md` 尾部带"本章字数"统计需人工复核。`using-writing-workflow` L144-226 的跨书学习机制维护工作根目录下的 `author-playbook.json`（projects[].lessons 的 what_worked / what_didnt_work / would_do_differently + patterns.best_genres / effective_hook_types / emotional_signature_performance），在新项目选题、规划、审查三处注入历史经验。

---

## C 块｜16 个 Agent 预设与协作

### C1 预设声明与挂载机制
`preset.yml` 只有 2 行：`name: 小说写作工作流` + description（覆盖平台调研→…→数据驱动优化闭环，并说明配套 `dsh-novel-writing` 插件提供小说工作台）。
`agent.cordis.yml`（222 行）是**宿主包组合文件**（AGENT-PLANE），要点：
- L16-47 `- id: persona / name: '@deepseek-ai/dsh-persona'`，`config.prefix` 为多行人设正文（含三层角色模型、写作价值观五条、工具纪律）。**这是 preset 与 DSH 对接的 key**：契约 item 5.6 记录该行 config 键契约 `keys=[prefix,suffix,complete,includeRuntimeContext]`、`requiredKeys=[prefix]`、`usedKeys=[prefix]`，并注明"rc.2 起人设正文键是 `prefix`，旧键 `text` 已不存在——用错键会让**整棵预设挂载被否决**"（真实事故 BUG-007）。`complete` 刻意不写 = schema 默认 false，使人设作为"一段"参与组装。权威校验用已装宿主的 Config + resolveConfig 逐行核对（`test/fixtures/host-surfaces/preset-schema-face.mjs`）。
- 其余行按能力分组并带 `config`/`disabled`/`isolate`：`agent-instructions(maxBytes:65536)`；shell 用平台分流 `disabled: !!js process.platform === 'win32'`（bash/pwsh 互斥）；`tool-fs` / `tool-fs-search` / `tool-jobs`；**skill 挂载** L83-90 `skill-filesystem` 的 `customSkillDirs: [!!js "process.getBuiltinModule('node:url').fileURLToPath(new URL('skills/', baseUrl))"]`——`baseUrl` 相对解析，使预设自带的 29 个 SKILL 随预设目录走；`tool-skill`；**L94-95 `- id: tool-novel / name: dsh-novel-writing/tools`（插件工具行，可选依赖，未装则静默）**；`tool-goal`；`planning`（`cordis:group` + `isolate.planMode:true`，内含 `dsh-plan-mode`）；`compaction` 组（basic + command-compact + tool-result-pruner `thresholdChars:8192/headChars:4096/tailChars:1024`）；`delegation` 组（subagent-control、subagent `provider:spawn/backgroundMode:continuable`、subagent_fork `provider:fork`、codex 与 claude-code 行 `disabled:true`、workflow-worker-thread、tool-workflow、tool-ralph `maxRounds:64`）；`tool-ask-user` / `tool-todo(allowParallelInProgress:true)` / `tool-web(fetch:false, searchTimeoutMs:60000)`。
- 契约 item 5.2 把这一整个包行清单登记为宿主耦合字面量（"16+ 宿主包行"），item 5.3 登记 `!!js` 求值约定（L52/L56/L81），item 5.4 登记 skill 目录加载约定。

### C2 16 个 Agent 的职责与产出
| Agent 文件 | 身份 | 职责 | 产出 |
|---|---|---|---|
| `market-analyst.md` | 网文市场分析师（"老麦"） | 平台签约政策/收益模式/读者画像 + 红蓝海题材盈利潜力 | `01-platform-research.md`、`02-genre-analysis.md` |
| `competitor-analyst.md` | 竞品拆解专家（"老蔡"） | 头部/中腰部/同期新书拆解与差异化定位；不访问小说全文 | `16-competitor-analysis.md` |
| `creation-strategist.md` | 创作策略顾问（"老方"） | 类型选择、定义情感签名、篇幅/更新/存稿规划、盈利可行性 | `00-work-type.md`、`04-creation-plan.md` |
| `novel-architect.md` | 小说架构师（"老梅"） | 世界观/力量体系/人物/大纲/回报分级表/伏笔（含最迟回收章节） | 7 个文件：`05-outline.md`、`08-characters/{main,supporting}-characters.md`、`character-relationships.md`、`09-worldbuilding/{world-settings,power-system}.md`、`17-continuity/story-bible.md` |
| `chapter-designer.md` | 章节设计师（"格子"） | 大纲→逐章细纲：场景/爽点/章末钩子/付费转化节点 + context card | `06-chapter-outlines/chapter-XXX.md`、`17-continuity/chapter-XXX-context.md` |
| `content-writer.md` | 内容写作者（"老纪"） | 按细纲逐场景生成正文、看护预检、逐场景自检、更新连续性账本 | `07-content/chapter-XXX.md`、`17-continuity/continuity-ledger.md` |
| `continuity-reviewer.md` | 连续性审查员（"老林"） | 正文 vs 细纲/设定/前文，执行连续性硬门槛 1-9 | 审查报告（覆盖率表/偏离度明细/硬冲突/≥2 发现/判定） |
| `character-world-reviewer.md` | 人物世界观审查员（"老秦"） | 逐角色行为/对话/关系/身份/成长弧 + 世界观与力量体系合规 | 审查报告；OOC 零容忍 |
| `plot-logic-reviewer.md` | 情节逻辑审查员（"老周"） | 因果链、伏笔生命周期、冲突升级、主角能动性、巧合合理性 | 审查报告（断裂点/伏笔状态/升级曲线/能动性） |
| `commercial-editor.md` | 商业编辑（"钱姐"） | 平台算法适配、付费卡点、章末钩子、社交传播潜力 | 审查报告（平台核心指标逐项表） |
| `engagement-reviewer.md` | 阅读体验审查员（"小鹿"） | 硬门禁 11-12+14-15 + 文学质量 5 项 + 情感体验 | 审查报告（情绪曲线/最精彩与最薄弱段落/翻页强度强中弱） |
| `ai-compliance-officer.md` | AI 合规官（"老严"） | AI 参与度三级分流、证据链留存包、AI 痕迹检测 + 维度 9 | `13-creation-logs/chapter-XXX-log.md` + 回写 `guardrails.*` |
| `launch-strategist.md` | 发布策略师（"老徐"） | 安全存稿量、签约流程、开书时机、首秀 14 天策略 | `14-launch-strategy.md` |
| `monetization-advisor.md` | 变现顾问（"老钱"） | VIP 上架时机、付费卡点、全勤/打赏/月票激励、IP 衍生 | `15-monetization-strategy.md` |
| `data-analyst.md` | 数据运营分析师（"小余"） | 完读/留存/追读/退款/ARPU 监控、流失章定位、数据→内容闭环、止损框架、读者互动 | `11-data-monitoring/` 报告、`12-reader-interaction/` 日志 |
| `novel-creator.md` | Novel Creator（**已废弃**） | 文件自述"自 v4.0.0 起正文生成职责由 content-writer 承担，不再被 orchestrator 调度" | JSON（status/files_created/errors） |

### C3 协作关系：谁审谁、writer 与 reviewer 如何分离
- **团队表**（`using-writing-workflow` L289-309）把 16 个 agent 分成 市场调研组 / 策划创作组 / 内容生产组 / 地基审查组 / 审查组 / 运营组。**地基审查组**：大纲审查由 continuity-reviewer + character-world-reviewer + commercial-editor ×3 并行；细纲审查由 continuity-reviewer + commercial-editor + engagement-reviewer ×3 并行。**审查组**：正文由 6 个独立 agent 并行审（L313 调度规则第 1 条："创作者与审查者绝对分离"）。
- 调度规则（L311-317）：审查组并行启动；每个 agent 用独立 subagent 且加载对应 agent 定义文件；**"Agent 定义优先于 SKILL"**（agent 文件定义"谁来做、怎么做"，SKILL 定义"做什么标准"）；**Coordinator 只调度，不亲自执行任何内容生成或审查**。
- writer/reviewer 分离的实现方式（综合 16 个 agent 文件正文）：`content-writer.md` 是**唯一明写"不得自审"**的——原文"不自审、不评分、不辩解：写完交给审查组，审查组的意见就是最终意见…你不是审查员"。其余靠**互斥的"你不负责"条款**：character-world-reviewer 不查时间线/因果/文笔；plot-logic-reviewer 不查时间线/OOC/文笔；continuity-reviewer 不查人设/情节/平台适配；commercial-editor 不查时间线/人设/情节/AI 痕迹；engagement-reviewer 不查技术连续性/OOC/情节/商业适配。数据闭环则是 `data-analyst` 只提建议、由 content-writer 执行（原文"不亲自修改内容"）。
- 反向门禁：审查方也被门禁约束——所有 reviewer 都被要求"≥2 条具体发现 + 正文引用 + 明确判定"，否则其报告会被 Coordinator 驳回并用更严 prompt 重审（要求≥3 个问题）。
- **两处未确认/需注意**：① 除 `ai-compliance-officer`（被要求回写 `guardrails`）与废弃的 `novel-creator`（被明确禁止写 state、禁止与用户交互）之外，其余 14 个 agent 文件**未声明** workflow-state 写权限与交互禁令（该约束实际写在与每阶段配套的 SKILL 启动模板与 `using-writing-workflow` 的"Subagent 硬边界"表 L76-84 中：不交互、不改 workflow-state、不做最终决策、不相互通信）；② 全库 grep 未见"禁止修改代码"类条款，该维度对小说 agent 不适用。
- 交互契约：Subagent 不能调用 `ask_user_question`，因此决策型阶段被拆成**两阶段执行协议**（L321-346）：subagent 只出"待确认方案"，Coordinator 用 `ask_user_question` 收用户选择后再落盘或二次调用执行型 subagent。决策型 = work_type_selection / platform_research / genre_selection / novel_confirmation / creation_planning / outline_writing；其余为执行型（L327-330）。

---

## 实际读过的文件清单（含行数）

**A 块（全部完整读完）**
| 文件 | 行数 |
|---|---|
| `package.json` | 46 |
| `cordis.patch.yml` | 12 |
| `lib/index.js`（分段实读：1-280、589-768、856-1235、1236-1474，覆盖率约 75%） | 1474 |
| `lib/tools.js` | 405 |
| `lib/host-boundary.js` | 274 |
| `lib/host-contract.mjs`（读 1-263、264-346，即全文） | 346 |
| `lib/client.js`（**结构化选读**，非通读：1-180、540-959、1560-1689、660-880、3020-3079、5110-5275 及 grep 定位） | 5275 |

**B 块**
| 文件 | 行数 | 读法 |
|---|---|---|
| `skills/using-writing-workflow/SKILL.md` | 1639 | 标题全览 + 精读 1-120/144-347/1175-1264/1408-1639 |
| `skills/quality-review/SKILL.md` | 632 | 精读 1-130/131-310/380-632 |
| `skills/content-generation/SKILL.md` | 791 | 标题全览 + 精读 47-116/449-528/770-791 |
| `skills/data-monitoring/SKILL.md` | 598 | 全文 |
| `skills/human-ai-collaboration/SKILL.md` | 401 | 精读 1-170/230-359 |
| `skills/monetization-strategy/SKILL.md` | 399 | 精读 1-120 |
| `skills/platform-research/SKILL.md` | 605 | 精读 20-129 + 标题全览 |
| `skills/launch-strategy/SKILL.md` | 367 | 精读 20-119 + 标题全览 |
| `skills/creation-planning/SKILL.md` | 570 | 精读 25-104/380-439 |
| `skills/chapter-outline/SKILL.md` | 373 | 精读 125-184 + 标题全览 |
| `skills/opening-optimization/SKILL.md` | 371 | 精读 25-99 |
| `skills/commercial-check/SKILL.md` | 130 | 全文（另由子代理独立复核） |
| `skills/engagement-check/SKILL.md` | 123 | 全文 |
| `skills/data-driven-optimization/SKILL.md` | 43 | 经子代理全文提取 |
| `skills/reader-interaction/SKILL.md` | 483 | 精读 112-171 + 标题全览 |
| 其余 14 个小 SKILL（continuity/plot-logic/character-world/ai-compliance/outline-review/chapter-outline-review/publish-pipeline/novel-studio/work-type-selection/competitor-analysis/genre-selection/novel-style-learning/outline-writing/novel-confirmation） | 43-288 | 经子代理逐文件全文提取（frontmatter、维度分值、硬门禁编号、阈值、报告结构、执行 agent） |

**C 块**
| 文件 | 行数 |
|---|---|
| `agent-presets/novel-writing/preset.yml` | 2 |
| `agent-presets/novel-writing/agent.cordis.yml` | 222（全文） |
| `agents/*.md` × 16 | 3108-5663 字节/个，经子代理逐文件全文提取 |

**未读取/未确认**：`CHANGELOG.md`(256KB)、`README.md`、`AGENTS.md`、`.governance/`、`docs/`（含 COMPAT-001 分析、UX-0xx 研究报告、release checklist）、`install.ps1` / `install.sh`、`scripts/*.mjs`、`test/*.mjs`、`.github/workflows/ci.yml`——这些仅在契约与代码注释中被**引用**（如 item 4.1-4.6 描述安装通道、item 6.4 描述 CI mock 面钉），本人未打开原文核对。仓库内的 `.governance/` 制度与面向 AI 开发者的流程元规则按要求未纳入提取。
