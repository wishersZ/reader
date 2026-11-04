# 测试与回归约定

这个仓库的 Electron 测试会真实启动窗口，单次约 20–40 秒。为了避免重复跑同一状态，按下面的分层和节奏执行。

## 分层命令

| 命令 | 覆盖 | 大约耗时 |
|---|---|---|
| `npm run test:quick` | 书源引擎 + EPUB 解析（纯 Node） | 几秒 |
| `npm run test:window` | 窗口 / 纯文本 / 单行 / 桌面模式 | 20–30 秒 |
| `npm run test:reader` | 书签 / 净化 / 进度 / 排版 / 备份 | 20–30 秒 |
| `npm run test:ui` | window + reader | 40–60 秒 |
| `npm test` | 全量 = quick + ui | 50–80 秒 |

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
| 书源规则 / 抓取引擎 | `test:quick` |
| EPUB 解析 / 目录 / 封面 | `test:quick` |
| 纯文本模式 / 单行 / 紧凑布局 / 窗口尺寸 | `test:window` |
| 桌面模式 / 托盘 / 老板键 / 毛玻璃 / 描边 | `test:window` |
| 书签 / 净化规则 / 进度条 / 排版 / 备份 | `test:reader` |
| 同时动公共渲染或窗口 + 阅读逻辑 | `test:ui`，提交前再 `npm test` |
| 合并 / 发版 | `npm test` |
