/* 窗口模式冒烟测试：老板键 / 系统托盘 / 透明桌面模式 / 置顶 · 毛玻璃 · 描边
   用法：npx electron tools/test-window-modes.js
        NR_VISUAL=1 时会在桌面模式停住，方便人工/截图确认透明效果
   用临时 userData 目录运行，不会动真实配置；退出码 0 表示全部通过。 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const Module = require('module');
const electron = require('electron');

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

const wait = ms => new Promise(r => setTimeout(r, ms));
const logFile = path.join(__dirname, '..', '.tmp-check', 'test-window-modes.log');
const lines = [];
function say(line) { lines.push(line); console.log(line); try { fs.mkdirSync(path.dirname(logFile), { recursive: true }); fs.writeFileSync(logFile, lines.join('\n') + '\n'); } catch {} }
let failed = 0;
function check(name, ok, extra) {
  if (!ok) failed++;
  say((ok ? 'PASS  ' : 'FAIL  ') + name + (extra === undefined ? '' : '   [' + extra + ']'));
}
const win = () => BrowserWindow.getAllWindows()[0];
const evalJs = code => win().webContents.executeJavaScript(code, true);
const shotDir = path.join(__dirname, '..', '.tmp-check');
const norm = c => String(c || '').toLowerCase();
// 恢复阅读位置按段落对齐，但工具栏行数/分块高度估算会让段落号有几点偏差，取两次测量的较小值再比
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
  await wait(3000);
  fs.mkdirSync(shotDir, { recursive: true });

  /* ---- 普通模式 ---- */
  let w = win();
  check('窗口已创建', !!w);
  check('普通模式背景是纸张色', norm(w.getBackgroundColor()) === '#f7f3e8', w.getBackgroundColor());
  check('普通模式带系统边框', w.getContentBounds().width < w.getBounds().width, '边框宽 ' + (w.getBounds().width - w.getContentBounds().width));

  let st = await evalJs('window.app.windowState()');
  check('默认老板键 Control+Alt+Q', st.bossKey === 'Control+Alt+Q', st.bossKey);
  check('默认不是桌面模式', st.desktop.on === false);
  check('页面初始状态是普通模式', (await evalJs('document.documentElement.dataset.desktop')) === 'off');
  check('托盘图标已创建', trayCount === 1, 'Tray 实例数 ' + trayCount);

  /* ---- 老板键：隐藏 / 恢复 ---- */
  await evalJs('window.app.hideWindow(); 1');
  await wait(400);
  check('老板键能隐藏窗口', win().isVisible() === false);
  await evalJs('window.app.showWindow(); 1');
  await wait(400);
  check('再按一次恢复窗口', win().isVisible() === true);

  /* ---- 改老板键（默认键可能被已安装的月读占用，用 F9 组合验证注册） ---- */
  let r = await evalJs('window.app.setBossKey("Control+Alt+Shift+F9")');
  check('老板键可改', r.bossKey === 'Control+Alt+Shift+F9' && globalShortcut.isRegistered('Control+Alt+Shift+F9'), r.bossKey);
  r = await evalJs('window.app.setBossKey("Control+Alt+Shift+F9+Nope")');
  check('无效快捷键会被拒绝并保留原键', !!r.bossKeyError && r.bossKey === 'Control+Alt+Shift+F9', r.bossKeyError);
  r = await evalJs('window.app.setBossKey("Control+Alt+Q")');
  check('默认键被占用时给出提示并保留原键',
    (r.bossKey === 'Control+Alt+Q' && globalShortcut.isRegistered('Control+Alt+Q')) || (!!r.bossKeyError && r.bossKey === 'Control+Alt+Shift+F9'),
    r.bossKeyError || '已注册 ' + r.bossKey);
  check('老板键状态带回错误信息字段', typeof r.bossKeyError === 'string', r.bossKeyError || '（当前键可用）');

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
  check('测试书已打开并记录进度', before.y > 7000 && before.saved && before.saved.index > 0, 'scrollY=' + before.y + ' 段落=' + (before.saved && before.saved.index));
  fs.writeFileSync(path.join(shotDir, 'normal-mode.png'), (await win().webContents.capturePage()).toPNG());

  /* ---- 伪装皮肤：VS Code / Excel ---- */
  await evalJs('setSkin("vscode"); 1');
  await wait(300);
  check('VS Code 皮肤：data-skin', (await evalJs('document.documentElement.dataset.skin')) === 'vscode');
  check('VS Code 皮肤：窗口标题伪装', (await evalJs('document.title')) === 'novel-notes.js - Visual Studio Code', await evalJs('document.title'));
  check('VS Code 皮肤：真实工具栏隐藏', (await evalJs('getComputedStyle(document.getElementById("topbar")).display')) === 'none');
  check('VS Code 皮肤：假窗口外框出现', (await evalJs('document.getElementById("skinChrome").children.length')) >= 3);
  check('VS Code 皮肤：正文注释前缀', (await evalJs('getComputedStyle(document.querySelector("#reader p"), "::before").content')).includes('//'));
  check('VS Code 皮肤：等宽字体', (await evalJs('getComputedStyle(document.getElementById("reader")).fontFamily')).includes('Consolas'));
  fs.writeFileSync(path.join(shotDir, 'skin-vscode.png'), (await win().webContents.capturePage()).toPNG());

  await evalJs('setSkin("excel"); 1');
  await wait(300);
  check('Excel 皮肤：data-skin', (await evalJs('document.documentElement.dataset.skin')) === 'excel');
  check('Excel 皮肤：窗口标题伪装', (await evalJs('document.title')) === '工作簿1 - Excel', await evalJs('document.title'));
  check('Excel 皮肤：列头与公式栏', (await evalJs('!!document.querySelector("#skinChrome .colhead") && !!document.querySelector("#skinChrome .formulabar")')));
  const cellStyle = await evalJs('(() => { const s = getComputedStyle(document.querySelector("#reader p")); return { indent: s.textIndent, border: s.borderBottomWidth, pad: s.paddingLeft }; })()');
  check('Excel 皮肤：单元格样式', cellStyle.indent === '0px' && parseFloat(cellStyle.border) > 0 && cellStyle.pad === '46px', JSON.stringify(cellStyle));
  fs.writeFileSync(path.join(shotDir, 'skin-excel.png'), (await win().webContents.capturePage()).toPNG());

  await evalJs('setSkin("none"); 1');
  await wait(300);
  check('切回无皮肤：标题还原', (await evalJs('document.title')) === '测试书 - 月读', await evalJs('document.title'));
  check('切回无皮肤：工具栏恢复', (await evalJs('getComputedStyle(document.getElementById("topbar")).display')) === 'flex');
  const driftSkin = await anchorDrift(before.saved.index);
  check('皮肤切换后阅读位置保持', driftSkin <= 5, '段落偏差 ' + driftSkin);

  /* ---- 进入桌面模式（窗口会重建） ---- */
  say('-- 请求进入桌面模式');
  evalJs('void window.app.setDesktopMode(true); 1').catch(e => say('-- 切换调用结束：' + e.message));
  await wait(3000);
  w = win();
  check('桌面模式重建了窗口', !!w && BrowserWindow.getAllWindows().length === 1, '窗口数 ' + BrowserWindow.getAllWindows().length);
  if (!w) throw new Error('桌面模式没有窗口，后面的检查无法继续');
  check('桌面模式窗口用全透明背景色', norm(w.getBackgroundColor()) === '#000000' || norm(w.getBackgroundColor()) === '#00000000', w.getBackgroundColor());
  check('桌面模式去掉了系统边框', w.getContentBounds().width === w.getBounds().width, '边框宽 ' + (w.getBounds().width - w.getContentBounds().width));
  check('页面状态切成桌面模式', (await evalJs('document.documentElement.dataset.desktop')) === 'on');
  check('桌面模式工具栏出现', (await evalJs('getComputedStyle(document.getElementById("ghostBar")).display')) === 'flex');
  check('桌面模式按钮变成退出', (await evalJs('document.getElementById("btnDesktop").textContent')) === '退出桌面模式');
  check('无边框窗口有拖动区', (await evalJs('getComputedStyle(document.getElementById("topbar")).webkitAppRegion')) === 'drag');
  const driftIn = await anchorDrift(before.saved.index);
  check('切换后回到原来的阅读位置', driftIn <= 5, '段落偏差 ' + driftIn + '（切换前 ' + before.saved.index + '）');

  /* ---- 背景浓淡 ---- */
  await evalJs('window.app.setWindowOptions({ alpha: .3 })');
  await wait(300);
  const bg = await evalJs('getComputedStyle(document.body).backgroundColor');
  check('背景浓淡生效', bg === 'rgba(247, 243, 232, 0.3)', bg);
  check('背景浓淡已记住', (await evalJs('window.app.windowState()')).desktop.alpha === 0.3);

  /* ---- 置顶 ---- */
  await evalJs('window.app.setWindowOptions({ onTop: true })');
  await wait(400);
  check('置顶已开启', win().isAlwaysOnTop() === true);
  await evalJs('window.app.setWindowOptions({ onTop: false })');
  await wait(400);
  check('置顶可关闭', win().isAlwaysOnTop() === false);

  /* ---- 描边 ---- */
  await evalJs('window.app.setWindowOptions({ outline: true })');
  await wait(300);
  check('描边已显示', (await evalJs('getComputedStyle(document.getElementById("frame")).display')) === 'block');
  check('描边状态已记住', (await evalJs('document.documentElement.dataset.outline')) === 'on');

  /* ---- 画面确实留了透明通道 + 留档截图 ---- */
  await win().webContents.capturePage().then(img => {
    fs.writeFileSync(path.join(shotDir, 'desktop-mode.png'), img.toPNG());
    const bmp = img.toBitmap();
    check('桌面模式画面带透明像素', bmp.length >= 4 && bmp[3] < 255, '左上角 alpha=' + (bmp.length >= 4 ? bmp[3] : '?'));
  });

  /* ---- 毛玻璃 ---- */
  const canBlur = (await evalJs('window.app.windowState()')).canBlur;
  await evalJs('window.app.setWindowOptions({ blur: true })');
  await wait(300);
  st = await evalJs('window.app.windowState()');
  check('毛玻璃开关可切换', st.desktop.blur === true, '系统支持亚克力=' + canBlur);

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
  evalJs('void window.app.setDesktopMode(false); 1').catch(e => say('-- 切换调用结束：' + e.message));
  await wait(3000);
  w = win();
  check('退出桌面模式回到不透明窗口', norm(w.getBackgroundColor()) === '#f7f3e8', w.getBackgroundColor());
  check('退出后仍是普通边框', w.getContentBounds().width < w.getBounds().width);
  check('页面状态回到普通模式', (await evalJs('document.documentElement.dataset.desktop')) === 'off');
  const driftOut = await anchorDrift(before.saved.index);
  check('退出后也回到原来的阅读位置', driftOut <= 5, '段落偏差 ' + driftOut);
  st = await evalJs('window.app.windowState()');
  check('桌面模式选项记在状态里', typeof st.desktop.alpha === 'number' && st.desktop.alpha <= 1 && st.desktop.outline === true && st.desktop.blur === false, JSON.stringify(st.desktop));
  const saved = JSON.parse(fs.readFileSync(path.join(dir, 'window-state.json'), 'utf8'));
  check('状态已落盘', saved.desktop.outline === true && saved.desktop.on === false);

  /* ---- 关掉窗口应该退出程序（重建窗口时不能误退出） ---- */
  win().close();
  await wait(1200);
  check('关闭窗口会退出应用', quitRequested === true && BrowserWindow.getAllWindows().length === 0);

  say('\n' + (failed ? failed + ' 项失败' : '全部通过') + '（userData: ' + dir + '）');
  app.exit(failed ? 1 : 0);
})().catch(err => { say('FAIL  测试异常：' + (err && err.stack || err)); app.exit(1); });
