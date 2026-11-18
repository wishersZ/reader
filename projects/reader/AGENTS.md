# 测试与回归约定

这个仓库的 Electron 测试会真实启动窗口，单次约 20–40 秒。为了避免重复跑同一状态，按下面的分层和节奏执行。

## 分层命令

| 命令 | 覆盖 | 大约耗时 |
|---|---|---|
| `npm run test:guard` | 运行台账守卫自测（RUN/SKIP/失败重试/FORCE/stats，纯 Node） | 几秒 |
| `npm run test:stdio` | stdio 防护自测（断管/孤儿/超时兜底，纯 Node） | 几秒 |
| `npm run test:quick` | guard 自测 + stdio 自测 + 书源引擎 + EPUB 解析（纯 Node） | 几秒 |
| `npm run test:window` | 窗口 / 纯文本 / 单行 / 桌面模式 | 20–30 秒 |
| `npm run test:reader` | 书签 / 净化 / 进度 / 排版 / 备份 | 20–30 秒 |
| `npm run test:ui` | window + reader | 40–60 秒 |
| `npm test` | 全量 = quick + ui | 50–80 秒 |

## 测试基建（新脚本必须复用，别再手写）

- `tools/test-kit.js`：`makeLogger`（控制台 + `.tmp-check/*.log` 双写、FAIL 计数）、`makeEval`（渲染进程求值，**已带 webContents 销毁检查与 2s 超时**）、`waitFor`（状态轮询，每次探测独立超时）、`armWatchdog`（看门狗，吊死也必有结论退出）。示例见 `test-window-modes.js` / `test-reader-p0.js`。
- `tools/safe-stdio.js`：`guard()`（console 断管写不外抛、防 EPIPE 死循环；stdout+stderr 双断 = 父进程已死，自行退出防孤儿）、`bounded()`（永不 resolve 的 promise 超时兜底）。被 test-kit 透传。
- 硬性约定：**禁止裸 `webContents.executeJavaScript`**（目标销毁时会永不 resolve 吊死轮询）与**裸 `console.log`**（断管时抛 EPIPE 形成死循环）；窗口重建等异步完成一律 `waitFor` 轮询目标状态，不睡固定时长。

## 运行台账（防重复运行，根治"全量跑太多"）

- 所有套件统一经 `tools/run-suite.js` 执行（package.json 已接入）。**同一代码状态**（HEAD + 工作区 diff + 未跟踪文件内容）下某套件已通过时，打印 `[SKIP]` 并直接退出，不再启动 Electron；`FORCE=1` 可强制重跑（PowerShell：`$env:FORCE='1'; npm test`）。
- 台账在 `.tmp-check/run-ledger.json`（git 忽略），记录每次运行的代码状态指纹、耗时、结果。**统计耗时用 `npm run test:stats`，禁止为"统计"再跑一遍套件。**
- 处理"写入未验证"提醒的正确姿势：先静态证明（`git diff` 时间线、既有日志结论、`node --check`）；确需运行时只跑受影响层，其余层会被台账自动 SKIP。验证提醒 ≠ 重跑。

## 什么时候跑什么

1. **迭代中**只跑受影响的那一层：
   - 只改 `src/novel-source.js` / EPUB 解析 → `test:quick`
   - 只改窗口、纯文本、单行、桌面模式 → `test:window`
   - 只改书签、净化、进度、排版、备份 → `test:reader`
   - 同时改到公共渲染逻辑（`measureTop`、`applySettings`、`updateProgress`）→ `test:ui`
2. **提交前**跑一次 `npm test` 做全量收口。
3. **合并远程代码后**必须重新跑一次 `npm test`。
4. **发布 / 打包前**跑一次 `npm test`。

## 禁止事项

- **同一代码状态不要重复跑同一个套件。** 已经全绿的状态，除非代码或环境变了，否则不重跑。
- **失败后不要原样重跑。** 先看断言和日志；确认是 flaky 就修等待逻辑，确认是真失败就修代码。禁止用“再跑一次”碰运气。
- **不要为了“确认稳定”连续跑两次。** 一次通过即可；稳定性问题用轮询和确定性等待解决。
- **不要每个小改动都上全量。** 连续的小改（例如先去掉 toast、再把高度 +2px）应合并改完，只跑一次受影响套件。
- **不要用固定 `setTimeout` 等窗口状态。** 用 `waitFor` 轮询目标状态（参考 `tools/test-window-modes.js` 里的 `waitFor`）。

## 环境

- `npm test` / `test:window` / `test:reader` 需要真实 GUI 和 Chromium IPC 权限。在受限沙箱里 Electron 会以 `platform_channel` / 拒绝访问直接退出，这不是测试失败。
- 如果窗口测试出现 `getContentBounds().width === 0`，视为环境/时序异常，先重试一次；不要把它当成“边框检查通过”（测试已经加了 `width > 0` 断言）。

## 改动与测试对照

| 改动 | 应跑 |
|---|---|
| 测试基建 / 工具脚本本身 | `test:guard` + `test:stdio` + 受影响套件 |
| 书源规则 / 抓取引擎 | `test:quick` |
| EPUB 解析 / 目录 / 封面 | `test:quick` |
| 纯文本模式 / 单行 / 紧凑布局 / 窗口尺寸 | `test:window` |
| 桌面模式 / 托盘 / 老板键 / 毛玻璃 / 描边 | `test:window` |
| 书签 / 净化规则 / 进度条 / 排版 / 备份 | `test:reader` |
| 同时动公共渲染或窗口 + 阅读逻辑 | `test:ui`，提交前再 `npm test` |
| 合并 / 发版 | `npm test` |
