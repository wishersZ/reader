# 规则审计与更新（2026-10-29 · 工具与模型更新后）

> 触发：DSH 工具集与模型更新。口径：**工具名以当前会话实际暴露的为准**；**模型无关化**——规则不再写死厂商或档位（sonnet / opus / ChatGPT / GPT…），统一为"由当前会话模型执行"。

## 一、一句话结论

按上述口径核对了 4 个规则面（治理指令、插件预设/角色/SKILL、打包技能包、已安装技能库），**12 个文件已更新**：34 处规则文本 + 1 处角色工具授权表（含配套测试断言）。历史留档、上游哈希资产按纪律未动，单列在 §五。改动已实测：oh-story `tsc --noEmit` 0 错、单测 **148/148**；dsh-novel-writing 预设校验通过，smoke 与 HEAD 基线**逐项一致（0 回归）**。

## 二、判定口径（旧 → 新）

| 场景 | 当前 DSH 名 | 规则里残留的旧名 |
|---|---|---|
| 向用户提问 | `ask_user_question` | AskUserQuestion |
| 派发子代理 | `subagent` / `subagent_fork` | Agent 工具 / Task |
| 读文件 | `read` / `glob` / `grep` | Read / Glob / Grep |
| 写文件 | `write` / `edit` | Write / Edit |
| 执行命令 | `pwsh`（Windows）/ `bash`（POSIX） | Bash |
| 联网 | `web_search` / `web_fetch` | WebSearch / WebFetch |
| 待办 | `todo_write` | TodoWrite |
| 定时 | `schedule_create` 等 | `/schedule`、`/loop` |
| 脚本入口 | 技能自身目录（会话给出 Base directory） | `${CLAUDE_PLUGIN_ROOT}` |
| 模型 | 会话提供，规则不写死 | sonnet / opus / ChatGPT / GPT |

## 三、改动清单

### A. `.plugin-stage/dsh-novel-writing`（本会话每次自动注入的那套治理规则）

| 文件 | 改动 |
|---|---|
| `AGENTS.md` | `AskUserQuestion` → `ask_user_question`（10 处，L9/10/50/164/167/198×2/204/238/246）；`禁止 Write/Edit/Bash` → `write/edit/pwsh`；`Agent 工具 spawn` → `subagent / subagent_fork`；hook 重装命令由纯 POSIX `cp` 改为 POSIX/Windows 双写（`cp` / `Copy-Item`） |
| `agent-presets/novel-writing/agents/competitor-analyst.md:46` | `WebSearch` → `web_search` |
| `agent-presets/novel-writing/agents/market-analyst.md:43` | 同上 |
| `agent-presets/novel-writing/agents/monetization-advisor.md:45` | 同上 |
| `agent-presets/novel-writing/skills/using-writing-workflow/SKILL.md` | ①「市场数据」补 `web_fetch`（读原文/官方页面）；②新增「文件与命令」条：`read/write/edit/glob/grep` + `pwsh`(Win)/`bash`(POSIX)，并声明旧名不存在；③两处「Claude 使用不同方式重试」→「换一种方式重试」；④「PUA Skill 集成」整段改为 DSH 等价「卡壳复盘」——用只读 `subagent` 复盘，去掉 `pua:pua` / superpowers 依赖 |

> 注：该文件 git diff 里另有 +27 行的「批次写作入口」段，是你未提交的 BATCH-001 工作，**不属于本次改动**。

### B. `.plugin-stage/oh-story-dsh`（DSH 适配层；不碰上游打包资产）

| 文件 | 改动 |
|---|---|
| `packages/dsh-plugin/src/skill-provider.ts` | 新增 `DSH_TOOL_NAMING` 常量，注入 story / drama / game / video 四条 bridge：上游文本里的 Claude Code 工具名一律按 DSH 名替代，**只调用本会话可见的工具** |
| `packages/dsh-plugin/src/role-provider.ts` | native-tools 角色 preamble 加一句：把角色正文里的旧工具名映射到 DSH 等价物，不可见的不调 |
| `packages/dsh-plugin/src/role-tool.ts` | 角色 shell 授权由只授 `bash` 改为 `bash` + `pwsh` 并存——Windows 预设暴露的是 `pwsh`，原授权下 `narrative-writer` / `story-researcher` 在 Windows 拿不到命令工具；运行期仍按会话实际注册的工具过滤，POSIX 无副作用 |
| `packages/dsh-plugin/tests/role-tool.test.ts` | 同步断言：`Bash` 映射展开为平台双名（`dshTools` 改 `flatMap`），5 处 allow 期望补 `pwsh` |

打包的 13+11+7+6 个 SKILL 与 7 个 Role **一字未改**：它们由 manifest 哈希固定，改动会直接破 `pnpm assets:check`；运行期由上面两条 bridge/override 覆盖（这也是仓库自身的规则："Never edit the bundled Skill files"）。

### C. 已安装技能库 `C:\Users\Administrator\.dsh\skills`

| 文件 | 改动 |
|---|---|
| `draft/SKILL.md` | `${CLAUDE_PLUGIN_ROOT}/skills/draft/build_docx.py` → `<本技能目录>/build_docx.py`（DSH 无该环境变量，原命令跑不通）；`## 其它模型（ChatGPT/DeepSeek 等…）` → `## 没有脚本执行环境时` |
| `trends/SKILL.md` | `WebSearch` → `web_search`（2 处）+ 补 `web_fetch`；「日常更新」段去掉 Claude Code 的 `/schedule`、`/loop`，改为 DSH 定时能力或手动 |
| `slang/SKILL.md` | `WebSearch` → `web_search`（2 处） |

### D. 写作规则文档（现已归入 `docs/rules/`）

`AI写小说规则模板.md`、`写书流程设计.md` 等**无需改动**：全文 grep 无工具名、无模型档位（唯一的 "Claude" 出现在来源引用标题里），规则本身与模型无关。

## 四、验证（实跑）

| 项 | 命令 | 结果 |
|---|---|---|
| 预设校验 | `node test/validate-preset.mjs`（dsh-novel-writing） | `PRESET VALIDATION PASSED`（degraded；schema-face `NOT_RUN`——本机无可解析的 `@deepseek-ai/cordis` profile 目录） |
| 回归对照 | HEAD 干净 worktree 跑 `node test/smoke.mjs` → 再打上本次补丁重跑 | **两次都是 `300 passed, 2 failed`**，逐项相同 ⇒ 本次规则改动 0 回归 |
| 基线已有 2 红 | 同上 | ①`BUG-007 看护三态 NOT_RUN`（环境缺 profile）；②`COMPAT-014 302≠301`（声明计数陈旧）——均与本次无关 |
| 类型检查 | `pnpm exec tsc -p tsconfig.json --noEmit`（oh-story/dsh-plugin） | exit 0 |
| 单测 | `pnpm test:unit`（oh-story） | **20 files / 148 tests 全过** |
| 空白检查 | `git diff --check`（两个仓库） | exit 0 |

另：我误把 dsh-novel-writing 的 5 个文件写成了 CRLF（仓库统一 LF），已归一化回 LF；`git diff` 现为 +55/−33 的真实改动量。

## 五、待决项（未改动，需你拍板）

1. **`dsh-novel-writing` 的 `tool-web.fetch: false`**
   `web_fetch` 已可用，但预设仍关着抓取。要"读官方原文"就得打开——这是联网面变更，等你点头。

2. **`AGENTS.md` 引用的治理工具链在本仓不存在**
   `commands/governance-init.md`、`skills/software-project-governance/`、`infra/verify_workflow.py|resolve_entry.py|archive.py|cleanup.py` 在 `.plugin-stage/dsh-novel-writing` 下均无实体，只有 `.governance/` 数据。这些"下一步动作"实际执行不了，属模板与仓库不匹配，需插件上游修，或在本仓补一份最小实现。

3. **已装技能库会被上游重同步覆盖**
   `~/.dsh/skills/_webnovel-repo-info/SYNC-INFO.txt` 已声明：从 `chinese-webnovel-skills` 重新同步会覆盖 C 组改动。要长期保留需回灌上游，或把 3 个文件的改动并入 `G:\txt\.skill-patch\` 的补丁链。

4. **`ci.yml` 行尾漂移（预存在，非本次）**
   工作树的 `.github/workflows/ci.yml` 被整体转成 CRLF（真实改动只有 9 行）。smoke 的 heredoc 解析器按 LF 匹配，因此在主工作树里 smoke 会在 `ci-mock-face` 处直接抛错；在 HEAD worktree 就正常。建议把该文件转回 LF。

## 六、附：本次环境记录

- 会话初期 `pwsh` 每次调用都返回 `3221225794`（`0xC0000142` / DLL 初始化失败），无法执行任何命令；切到 `danger-full-access` 后恢复（`pwsh 7.6.6`）。怀疑与 `workspace-write` 沙箱注入有关，供排查参考。
- 为跑测试临时装了依赖：`dsh-novel-writing/node_modules`（`@deepseek-ai/schemastery`）、`oh-story-dsh/node_modules`（`corepack pnpm install --frozen-lockfile`）；`git status` 未因此变化（均被忽略）。临时 worktree 与 pnpm shim 目录已清理。
