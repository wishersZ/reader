/* 窗口/模式冒烟测试：老板键 / 托盘 / 透明桌面模式 / 纯文本 / 单行极限缩小 / 伪装皮肤
   用法：npm run test:window（或 npx electron tools/test-window-modes.js）
        NR_VISUAL=1 时会在桌面模式停住，方便人工/截图确认透明效果
   用临时 userData 目录运行，不会动真实配置；退出码 0 表示全部通过。
   基建（防吊死求值/状态轮询/看门狗/断管防护）都在 tools/test-kit.js。 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const Module = require('module');
const electron = require('electron');
const { guard, wait, makeLogger, makeEval, waitFor, armWatchdog } = require('./test-kit');

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'yuedu-win-test-'));
process.env.NR_DATA_DIR = dir;

// 统计 main.js 建了几个托盘图标（electron.Tray 不能直接改写，从模块加载处替身）
let trayCount = 0;
const RealTray = electron.Tray;
class TrackingTray extends RealTray { constructor(...args) { super(...args); trayCount++; } }
const origLoad = Module._load;
Module._load = function (request, parent, isMain) {
  const result = origLoad.apply(this, arguments);
  if (request === 'electron' && parent && /src[\\/]main\.js$/.test(parent.filename || '')) {
    return new Proxy(result, { get: (t, k) => (k === 'Tray' ? TrackingTray : t[k]) });
  }
  return result;
};

const { app, BrowserWindow, globalShortcut } = require('electron');
require(path.join(__dirname, '..', 'src', 'main.js'));

const logger = makeLogger('test-window-modes.log');
const { say, check } = logger;
guard(m => say(m));
const evalJs = makeEval(() => BrowserWindow.getAllWindows()[0]);
const shotDir = path.join(__dirname, '..', '.tmp-check');
const norm = c => String(c || '').toLowerCase();

armWatchdog(say, app);

/* ============ 同类断言合并用的小探针 ============ */
const cur = () => BrowserWindow.getAllWindows()[0];
// 有系统边框 = 内容区比窗口小；无边框 = 内容区有效且与窗口同宽
const hasFrame = w => { const b = w.getBounds(), c = w.getContentBounds(); return c.width > 0 && c.width < b.width; };
const noFrame = w => { const b = w.getBounds(), c = w.getContentBounds(); return c.width > 0 && c.width === b.width; };
const dataset = key => evalJs(`document.documentElement.dataset.${key}`);
const displayOf = id => evalJs(`getComputedStyle(document.getElementById("${id}")).display`);
const bodyCount = () => evalJs('document.querySelectorAll("#reader p").length');
const shot = async name => { const img = await cur().webContents.capturePage(); fs.writeFileSync(path.join(shotDir, name), img.toPNG()); };
/* 恢复阅读位置按段落对齐，工具栏行数/分块高度估算会有几点偏差，取三次测量的最小值 */
async function anchorDrift(savedIndex) {
  let best = Infinity;
  for (let i = 0; i < 3; i++) {
    best = Math.min(best, Math.abs((await evalJs('topPara()')) - savedIndex));
    if (best <= 1) break;
    await wait(700);
  }
  return best;
}

(async () => {
  await app.whenReady();
  let quitRequested = false;
  // 拦住真正的退出，好让测试自己决定什么时候结束
  app.on('before-quit', e => { e.preventDefault(); quitRequested = true; say('-- before-quit'); });
  app.on('child-process-gone', (_e, d) => say('-- child-process-gone ' + JSON.stringify(d)));
  process.on('uncaughtException', err => say('-- uncaughtException ' + (err && err.stack || err)));
  process.on('unhandledRejection', err => say('-- unhandledRejection ' + (err && err.stack || err)));
  fs.mkdirSync(shotDir, { recursive: true });

  /* ---- 普通模式初始状态 ---- */
  let w = cur();
  check('窗口已创建', !!w);
  const st0 = (await evalJs('window.app.windowState()')) || {};
  check('初始状态：普通模式 + 默认老板键 + 托盘就绪',
    !!w && norm(w.getBackgroundColor()) === '#f7f3e8' && hasFrame(w) &&
    st0.bossKey === 'Control+Alt+Q' && (await dataset('desktop')) === 'off' && trayCount === 1,
    JSON.stringify({ bg: w && w.getBackgroundColor(), bossKey: st0.bossKey, tray: trayCount }));

  /* ---- 老板键：隐藏 / 恢复 ---- */
  await evalJs('window.app.hideWindow(); 1');
  await wait(400);
  const hiddenOk = cur().isVisible() === false;
  await evalJs('window.app.showWindow(); 1');
  await wait(400);
  check('老板键隐藏 / 恢复', hiddenOk && cur().isVisible() === true);

  /* ---- 任务栏隐身：窗口应带 WS_EX_TOOLWINDOW（不进任务栏 / Alt+Tab） ---- */
  const stealthOk = await new Promise(res => {
    try {
      require('child_process').execFile('powershell',
        ['-NoProfile', '-NonInteractive', '-Command',
          '$null = Add-Type -AssemblyName UIAutomationClient; ' +
          'Add-Type -Namespace SWQ -Name U -MemberDefinition "[DllImport(`"user32.dll`")] public static extern int GetWindowLongW(System.IntPtr h, int i);"; ' +
          '$r = [System.Windows.Automation.AutomationElement]::RootElement; ' +
          '$c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, ' + process.pid + '); ' +
          '$found = $false; ' +
          'foreach ($w in $r.FindAll([System.Windows.Automation.TreeScope]::Children, $c)) { ' +
          '  $h = [IntPtr]$w.Current.NativeWindowHandle; if ($h -eq [IntPtr]::Zero) { continue }; ' +
          '  if ($w.Current.Name -notmatch "月读") { continue }; ' +
          '  if (([SWQ.U]::GetWindowLongW($h, -20) -band 0x80) -ne 0) { $found = $true } ' +
          '}; "TOOLWINDOW=" + $found'],
        { windowsHide: true, timeout: 20000 },
        (e, so) => res(!e && String(so).includes('TOOLWINDOW=True')));
    } catch { res(false); }
  });
  check('任务栏隐身：顶层窗口带 WS_EX_TOOLWINDOW', stealthOk);

  /* ---- 老板键改键：可改 / 非法被拒 / 冲突时保留原键 ---- */
  let r = await evalJs('window.app.setBossKey("Control+Alt+Shift+F9")');
  const okChange = !!r && r.bossKey === 'Control+Alt+Shift+F9' && globalShortcut.isRegistered('Control+Alt+Shift+F9');
  r = await evalJs('window.app.setBossKey("Control+Alt+Shift+F9+Nope")');
  const okInvalid = !!r && !!r.bossKeyError && r.bossKey === 'Control+Alt+Shift+F9';
  r = await evalJs('window.app.setBossKey("Control+Alt+Q")');
  const okDefault = !!r && ((r.bossKey === 'Control+Alt+Q' && globalShortcut.isRegistered('Control+Alt+Q')) || (!!r.bossKeyError && r.bossKey === 'Control+Alt+Shift+F9'));
  check('老板键改键（可改 / 非法拒 / 冲突留）', okChange && okInvalid && okDefault,
    JSON.stringify({ okChange, okInvalid, okDefault, err: r && r.bossKeyError }));

  /* ---- 造一本书，记住阅读位置 ---- */
  const before = await evalJs(`(async () => {
    const text = Array.from({ length: 400 }, (_, i) => '第' + (i + 1) + '段 ' + '测试正文内容'.repeat(12)).join('\\n');
    await dbPut({ id: 'test-pos', name: '测试书', text, size: text.length, format: 'txt', added: Date.now() });
    await openBook('test-pos');
    await new Promise(r => setTimeout(r, 600));
    window.scrollTo(0, 8000);
    window.__nrFlush();
    return { y: Math.round(window.scrollY), saved: JSON.parse(localStorage.getItem('nr-progress-test-pos') || 'null') };
  })()`);
  check('测试书已打开并记录进度', !!before && before.y > 7000 && before.saved && before.saved.index > 0,
    'scrollY=' + (before && before.y) + ' 段落=' + (before && before.saved && before.saved.index));
  if (!before || !before.saved) throw new Error('测试书未就绪，后面的检查无法继续');
  await shot('normal-mode.png');

  /* ---- 伪装皮肤：VS Code / Excel ---- */
  await evalJs('setSkin("vscode"); 1');
  await wait(300);
  const vs = {
    skin: (await dataset('skin')) === 'vscode',
    title: (await evalJs('document.title')) === 'novel-notes.js - Visual Studio Code',
    toolbarHidden: (await displayOf('topbar')) === 'none',
    chrome: (await evalJs('document.getElementById("skinChrome").children.length')) >= 3,
    comment: (await evalJs('getComputedStyle(document.querySelector("#reader p"), "::before").content')).includes('//'),
    mono: (await evalJs('getComputedStyle(document.getElementById("reader")).fontFamily')).includes('Consolas')
  };
  check('VS Code 皮肤', Object.values(vs).every(Boolean), JSON.stringify(vs));
  await shot('skin-vscode.png');

  await evalJs('setSkin("excel"); 1');
  await wait(300);
  const xl = {
    skin: (await dataset('skin')) === 'excel',
    title: (await evalJs('document.title')) === '工作簿1 - Excel',
    cellChrome: await evalJs('!!document.querySelector("#skinChrome .colhead") && !!document.querySelector("#skinChrome .formulabar")'),
    cellStyle: await evalJs('(() => { const s = getComputedStyle(document.querySelector("#reader p")); return s.textIndent === "0px" && parseFloat(s.borderBottomWidth) > 0 && s.paddingLeft === "46px"; })()')
  };
  check('Excel 皮肤', Object.values(xl).every(Boolean), JSON.stringify(xl));
  await shot('skin-excel.png');

  await evalJs('setSkin("none"); 1');
  await wait(300);
  const noSkin = (await evalJs('document.title')) === '测试书 - 月读' && (await displayOf('topbar')) === 'flex';
  const driftSkin = await anchorDrift(before.saved.index);
  check('切回无皮肤（标题/工具栏还原，位置保持）', noSkin && driftSkin <= 5, '段落偏差 ' + driftSkin);

  /* ---- 进入桌面模式（窗口重建：轮询等状态，不睡固定时长） ---- */
  say('-- 请求进入桌面模式');
  evalJs('void window.app.setDesktopMode(true); 1').catch(e => say('-- 切换调用结束：' + e.message));
  await waitFor(() => evalJs('document.documentElement.dataset.desktop === "on"'), 8000);
  w = cur();
  check('桌面模式窗口重建为无边框透明',
    !!w && BrowserWindow.getAllWindows().length === 1 && noFrame(w) &&
    (norm(w.getBackgroundColor()) === '#000000' || norm(w.getBackgroundColor()) === '#00000000'),
    w && ('窗口数 ' + BrowserWindow.getAllWindows().length + ' 背景 ' + w.getBackgroundColor()));
  if (!w) throw new Error('桌面模式没有窗口，后面的检查无法继续');
  const deskUi = {
    ghostBar: (await displayOf('ghostBar')) === 'flex',
    btn: (await evalJs('document.getElementById("btnDesktop").textContent')) === '退出桌面模式',
    drag: (await evalJs('getComputedStyle(document.getElementById("topbar")).webkitAppRegion')) === 'drag'
  };
  const driftIn = await anchorDrift(before.saved.index);
  check('桌面模式界面就绪', Object.values(deskUi).every(Boolean), JSON.stringify(deskUi));
  check('切换后回到原来的阅读位置', driftIn <= 5, '段落偏差 ' + driftIn + '（切换前 ' + before.saved.index + '）');

  /* ---- 桌面模式 + 纯文本：只切界面，不重建窗口 ---- */
  const winCountText = BrowserWindow.getAllWindows().length;
  await evalJs('window.app.setTextOnly(true)');
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "on"'), 4000);
  const hidden = {
    topbar: (await displayOf('topbar')) === 'none',
    ghostBar: (await displayOf('ghostBar')) === 'none',
    progTrack: (await displayOf('progTrack')) === 'none',
    pct: (await displayOf('pct')) === 'none',
    body: (await bodyCount()) > 0
  };
  check('桌面模式+纯文本：不重建窗口、界面全隐藏且正文保留',
    BrowserWindow.getAllWindows().length === winCountText && Object.values(hidden).every(Boolean), JSON.stringify(hidden));
  await shot('textonly-desktop.png');
  await evalJs('window.app.setTextOnly(false)');
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "off"'), 4000);
  check('退出纯文本：工具栏恢复', (await displayOf('topbar')) !== 'none');

  /* ---- 背景浓淡 / 置顶 / 描边 ---- */
  await evalJs('window.app.setWindowOptions({ alpha: .3 })');
  await wait(300);
  const bgNow = await evalJs('getComputedStyle(document.body).backgroundColor');
  const stAlpha = (await evalJs('window.app.windowState()')) || {};
  check('背景浓淡生效并记住', bgNow === 'rgba(247, 243, 232, 0.3)' && stAlpha.desktop && stAlpha.desktop.alpha === 0.3, bgNow);

  await evalJs('window.app.setWindowOptions({ onTop: true })');
  await wait(400);
  const onTopOn = cur().isAlwaysOnTop() === true;
  await evalJs('window.app.setWindowOptions({ onTop: false })');
  await wait(400);
  check('置顶可开关', onTopOn && cur().isAlwaysOnTop() === false);

  await evalJs('window.app.setWindowOptions({ outline: true })');
  await wait(300);
  check('描边生效并记住', (await displayOf('frame')) === 'block' && (await dataset('outline')) === 'on');

  /* ---- 画面确实留了透明通道 + 留档截图 ---- */
  {
    const img = await cur().webContents.capturePage();
    fs.writeFileSync(path.join(shotDir, 'desktop-mode.png'), img.toPNG());
    const bmp = img.toBitmap();
    check('桌面模式画面带透明像素', bmp.length >= 4 && bmp[3] < 255, '左上角 alpha=' + (bmp.length >= 4 ? bmp[3] : '?'));
  }

  /* ---- 毛玻璃 ---- */
  const stBlur = (await evalJs('window.app.windowState()')) || {};
  await evalJs('window.app.setWindowOptions({ blur: true })');
  await wait(300);
  const stBlur2 = (await evalJs('window.app.windowState()')) || {};
  check('毛玻璃开关可切换', !!stBlur2.desktop && stBlur2.desktop.blur === true, '系统支持亚克力=' + stBlur.canBlur);

  /* ---- 留时间人工确认透明 / 毛玻璃效果（NR_VISUAL=1，标记文件供外部截图脚本同步） ---- */
  if (process.env.NR_VISUAL) {
    const ms = Number(process.env.NR_VISUAL_MS) || 15000;
    const mark = n => { try { fs.writeFileSync(path.join(shotDir, 'visual-' + n + '.ready'), '1'); } catch {} };
    say('-- 视觉检查 1：纯透明（背景 0 + 描边）');
    await evalJs('window.app.setWindowOptions({ alpha: 0, blur: false, outline: true })');
    mark(1);
    await wait(ms);
    say('-- 视觉检查 2：毛玻璃（背景 15%）');
    await evalJs('window.app.setWindowOptions({ alpha: .15, blur: true })');
    mark(2);
    await wait(ms);
    say('-- 视觉检查结束');
  }
  await evalJs('window.app.setWindowOptions({ blur: false })');

  /* ---- 退出桌面模式（窗口再重建一次，状态要记住） ---- */
  say('-- 请求退出桌面模式');
  evalJs('void window.app.setDesktopMode(false); 1').catch(e => say('-- 切换调用结束：' + e.message));
  await waitFor(() => evalJs('document.documentElement.dataset.desktop === "off"'), 8000);
  w = cur();
  check('退出桌面模式恢复普通窗口',
    !!w && BrowserWindow.getAllWindows().length === 1 && hasFrame(w) && norm(w.getBackgroundColor()) === '#f7f3e8',
    w && ('背景 ' + w.getBackgroundColor()));
  const stOpt = (await evalJs('window.app.windowState()')) || {};
  check('桌面模式选项已记住',
    !!stOpt.desktop && typeof stOpt.desktop.alpha === 'number' && stOpt.desktop.alpha <= 1 &&
    stOpt.desktop.outline === true && stOpt.desktop.blur === false, JSON.stringify(stOpt.desktop));
  const driftOut = await anchorDrift(before.saved.index);
  check('退出后也回到原来的阅读位置', driftOut <= 5, '段落偏差 ' + driftOut);

  /* ---- 极限缩小：普通模式可拖到一行高 ---- */
  await evalJs('shrinkToLine(); 1');
  await waitFor(() => evalJs('document.documentElement.dataset.compact === "on"'));
  const one = cur().getBounds();
  const compactUi = {
    height: one.height <= 120,
    compact: (await dataset('compact')) === 'on',
    toolbarHidden: (await displayOf('topbar')) === 'none',
    body: (await bodyCount()) > 0
  };
  check('缩到一行（高度/紧凑/隐藏/正文）', Object.values(compactUi).every(Boolean), JSON.stringify({ ...compactUi, h: one.height }));
  cur().setBounds({ width: one.width, height: 20 });
  await wait(400);
  const clamped = cur().getBounds();
  check('最小高度挡在“一行”而不是 20px', clamped.height >= one.height - 2, '请求 20 → ' + clamped.height);

  /* ---- 紧凑下拖成 1.x 行自动吸附整行（最小 = 恰好一行正文） ---- */
  const linePx = Math.round(20 * 1.9);   // 测试环境默认字号 20 / 行距 1.9
  cur().setBounds({ width: one.width, height: Math.round(10 + linePx * 1.4) + 40 });
  await waitFor(() => {
    const cb = cur().getContentBounds();
    const v = (cb.height - 10) / linePx;
    return Math.abs(v - Math.round(v)) <= 0.08;
  }, 5000);
  const snapped = cur().getContentBounds().height;
  check('紧凑下拖到 1.x 行自动吸附整行', Math.abs(snapped - (10 + linePx)) <= 3,
    'content=' + snapped + ' 期望=' + (10 + linePx));

  /* ---- 紧凑下一格滚轮 = 一行（120 单位一格；反向清零） ---- */
  const wY0 = await evalJs('window.scrollY');
  await evalJs('window.dispatchEvent(new WheelEvent("wheel", { deltaY: 120, bubbles: true })); 1');
  await wait(150);
  const wY1 = await evalJs('window.scrollY');
  check('滚一格 = 一行', Math.abs((wY1 - wY0) - linePx) <= 2, '滚动 ' + (wY1 - wY0) + 'px 期望 ' + linePx + 'px');
  await evalJs('window.dispatchEvent(new WheelEvent("wheel", { deltaY: 120, bubbles: true })); 1');
  await wait(150);
  const wY2 = await evalJs('window.scrollY');
  check('连续滚第二格仍 = 一行', Math.abs((wY2 - wY1) - linePx) <= 2, '滚动 ' + (wY2 - wY1) + 'px');
  await evalJs('window.dispatchEvent(new WheelEvent("wheel", { deltaY: -120, bubbles: true })); 1');
  await wait(150);
  const wY3 = await evalJs('window.scrollY');
  check('反向滚一格 = 回退一行', Math.abs((wY2 - wY3) - linePx) <= 2, '回退 ' + (wY2 - wY3) + 'px');
  await shot('one-line.png');

  /* ---- 普通模式进入纯文本：重建为无边框窗口 ---- */
  cur().setBounds({ width: 1000, height: 760 });
  await wait(500);
  say('-- 请求进入纯文本模式');
  evalJs('void window.app.setTextOnly(true); 1').catch(e => say('-- 切换调用结束：' + e.message));
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "on"'), 8000);
  w = cur();
  check('纯文本模式重建为无边框窗口', !!w && BrowserWindow.getAllWindows().length === 1 && noFrame(w) && (await dataset('textonly')) === 'on');
  const tHidden = { topbar: (await displayOf('topbar')) === 'none', skin: (await displayOf('skinChrome')) === 'none' };
  const driftText = await anchorDrift(before.saved.index);
  check('纯文本界面全隐藏', Object.values(tHidden).every(Boolean), JSON.stringify(tHidden));
  check('切到纯文本后阅读位置保持', driftText <= 5, '段落偏差 ' + driftText);
  const savedOn = JSON.parse(fs.readFileSync(path.join(dir, 'window-state.json'), 'utf8'));
  check('纯文本状态写入状态文件', savedOn.textOnly === true && savedOn.lineHeight > 0, JSON.stringify({ textOnly: savedOn.textOnly, lineHeight: savedOn.lineHeight }));
  await shot('textonly-normal.png');

  /* ---- 纯文本下也能缩到一行 ---- */
  cur().setBounds({ width: 900, height: 20 });
  await waitFor(() => evalJs('document.documentElement.dataset.compact === "on"'));
  const tiny = cur().getBounds();
  const tinyUi = { height: tiny.height <= 120, compact: (await dataset('compact')) === 'on', body: (await bodyCount()) > 0 };
  check('纯文本窗口缩到一行', Object.values(tinyUi).every(Boolean), JSON.stringify({ ...tinyUi, h: tiny.height }));
  await shot('textonly-oneline.png');

  /* ---- Esc 退出纯文本，窗口恢复普通边框和可用高度 ---- */
  evalJs('document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })); 1').catch(() => {});
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "off"'), 8000);
  w = cur();
  const restored = {
    frame: !!w && hasFrame(w),
    height: !!w && w.getBounds().height >= 360,
    toolbar: (await displayOf('topbar')) === 'flex'
  };
  check('Esc 退出纯文本恢复普通窗口', Object.values(restored).every(Boolean), JSON.stringify({ ...restored, h: w && w.getBounds().height }));

  /* ---- F9：键盘进入去边框正文模式，并可极限缩到只剩一行正文 ---- */
  await evalJs('openFind(); 1');
  await wait(300);
  await evalJs('const kw = document.getElementById("findKw"); kw.focus(); kw.dispatchEvent(new KeyboardEvent("keydown", { key: "F9", bubbles: true })); 1');
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "on"'), 8000);
  await evalJs('closeFind(); 1');
  check('F9 在输入框焦点下也能进入纯文本（F 键全局生效）', (await dataset('textonly')) === 'on');
  evalJs('document.dispatchEvent(new KeyboardEvent("keydown", { key: "F9", bubbles: true })); 1');
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "off"'), 8000);
  check('再按 F9 退出纯文本', (await dataset('textonly')) === 'off');
  /* 进入前实测尺寸：纯文本内无论如何缩放，退出都应还原到这个值 */
  const kBefore = cur().getNormalBounds();
  evalJs('document.dispatchEvent(new KeyboardEvent("keydown", { key: "F9", bubbles: true })); 1');
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "on"'), 8000);
  w = cur();
  const kEntry = { window: !!w && BrowserWindow.getAllWindows().length === 1, frameless: !!w && noFrame(w), toolbar: (await displayOf('topbar')) === 'none' };
  check('F9 进入纯文本（重建无边框、只留正文）', Object.values(kEntry).every(Boolean), JSON.stringify(kEntry));
  cur().setBounds({ width: 900, height: 20 });
  await waitFor(() => evalJs('document.documentElement.dataset.compact === "on"'));
  const kb = cur().getBounds();
  const kOne = { clamp: kb.height > 20 && kb.height <= 120, compact: (await dataset('compact')) === 'on', body: (await bodyCount()) > 0 };
  check('F9 去边框后可缩到只剩一行正文', Object.values(kOne).every(Boolean), JSON.stringify({ ...kOne, h: kb.height }));
  await shot('f9-oneline.png');
  /* 纯文本内缩到一行再退出：仍精确还原“进入时”的 prevBounds，而不是纯文本里的大小 */
  evalJs('void window.app.setTextOnly(false); 1').catch(e => say('-- 切换调用结束：' + e.message));
  await waitFor(() => evalJs('document.documentElement.dataset.textonly === "off"'), 8000);
  const kOut = cur().getBounds();
  check('一行高退出纯文本仍精确还原 prevBounds', Math.abs(kOut.width - kBefore.width) <= 2 && Math.abs(kOut.height - kBefore.height) <= 2,
    '期望≈' + kBefore.width + 'x' + kBefore.height + ' 实际=' + kOut.width + 'x' + kOut.height);
  check('收尾退出纯文本回到普通模式', (await dataset('textonly')) === 'off');

  const saved = JSON.parse(fs.readFileSync(path.join(dir, 'window-state.json'), 'utf8'));
  check('状态落盘正确', saved.desktop.outline === true && saved.desktop.on === false && saved.textOnly === false && typeof saved.lineHeight === 'number',
    JSON.stringify({ d: saved.desktop, textOnly: saved.textOnly, lineHeight: saved.lineHeight }));

  /* ---- 关掉窗口应该退出程序（重建窗口时不能误退出） ---- */
  cur().close();
  await wait(1200);
  check('关闭窗口会退出应用', quitRequested === true && BrowserWindow.getAllWindows().length === 0);

  say('\n' + (logger.failed ? logger.failed + ' 项失败' : '全部通过') + '（userData: ' + dir + '）');
  app.exit(logger.failed ? 1 : 0);
})().catch(err => { say('FAIL  测试异常：' + (err && err.stack || err)); app.exit(1); });
