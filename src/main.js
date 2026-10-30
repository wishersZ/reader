const { app, BrowserWindow, Menu, Tray, globalShortcut, ipcMain, dialog, shell, nativeImage } = require('electron');
const path = require('path');
const posix = path.posix;
const os = require('os');
const fs = require('fs');
const JSZip = require('jszip');
const { XMLParser } = require('fast-xml-parser');
const cheerio = require('cheerio');
const JSON5 = require('json5');
const { Engine, parseRuleListText } = require('./novel-source');
const { parseEpub } = require('./epub');
if (process.env.NR_DATA_DIR) app.setPath('userData', process.env.NR_DATA_DIR);

const ASSETS = path.join(__dirname, '..', 'assets');
const DEFAULT_BOSS_KEY = 'Control+Alt+Q';
const stateFile = () => path.join(app.getPath('userData'), 'window-state.json');

/* ============ 窗口状态：大小位置、桌面模式、老板键都记在这里（下次启动原样恢复） ============ */
function normalizeState(raw) {
  const st = raw && typeof raw === 'object' ? raw : {};
  const d = st.desktop && typeof st.desktop === 'object' ? st.desktop : {};
  const b = d.bounds && Number.isFinite(d.bounds.width) && Number.isFinite(d.bounds.height) ? d.bounds : null;
  const alpha = Number(d.alpha);
  return {
    width: Number(st.width) || 1000, height: Number(st.height) || 760,
    x: Number.isFinite(st.x) ? st.x : undefined,
    y: Number.isFinite(st.y) ? st.y : undefined,
    maximized: !!st.maximized,
    bossKey: typeof st.bossKey === 'string' ? st.bossKey : DEFAULT_BOSS_KEY,
    desktop: {
      on: !!d.on,
      alpha: Number.isFinite(alpha) ? Math.min(1, Math.max(0, alpha)) : 0,
      onTop: !!d.onTop, blur: !!d.blur, outline: !!d.outline,
      maximized: !!d.maximized, bounds: b
    }
  };
}
function loadState() {
  try {
    // 状态文件可能被记事本存成带 BOM 的 UTF-8，去掉再解析
    return normalizeState(JSON.parse(fs.readFileSync(stateFile(), 'utf8').replace(/^\uFEFF/, '')));
  } catch { return normalizeState({}); }
}
function saveState() { try { fs.writeFileSync(stateFile(), JSON.stringify(state)); } catch {} }

let state = normalizeState({});
let mainWindow = null;
let tray = null;
let rebuilding = false;
let bossKeyError = '';   // 启动时默认键可能被别的程序占用，界面要能提示

/* 毛玻璃（系统亚克力）需要 Windows 11 22H2（build 22621）以上 */
function supportsAcrylic() {
  if (process.platform !== 'win32') return false;
  if (typeof BrowserWindow.prototype.setBackgroundMaterial !== 'function') return false;
  const m = /^10\.0\.(\d+)/.exec(os.release());
  return !!m && parseInt(m[1], 10) >= 22621;
}

const publicState = () => ({
  desktop: { ...state.desktop },
  bossKey: state.bossKey,
  bossKeyError,
  canBlur: supportsAcrylic(),
  visible: !!mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible(),
  maximized: !!mainWindow && !mainWindow.isDestroyed() && mainWindow.isMaximized()
});

/* ============ 窗口：普通模式用系统边框，桌面模式换成无边框透明窗口 ============ */
function windowOptions() {
  const d = state.desktop;
  const common = {
    show: false, title: '月读', icon: path.join(ASSETS, 'icon.png'), autoHideMenuBar: true,
    minWidth: 480, minHeight: 360,
    webPreferences: {
      contextIsolation: true, spellcheck: false,
      preload: path.join(__dirname, 'preload.js'),
      additionalArguments: ['--nr-state=' + encodeURIComponent(JSON.stringify(publicState()))]
    }
  };
  if (d.on) {
    const b = d.bounds || state;
    return {
      ...common,
      width: b.width, height: b.height, x: Number.isFinite(b.x) ? b.x : undefined, y: Number.isFinite(b.y) ? b.y : undefined,
      frame: false, transparent: true, backgroundColor: '#00000000', hasShadow: false, resizable: true,
      alwaysOnTop: !!d.onTop,
      ...(d.blur && supportsAcrylic() ? { backgroundMaterial: 'acrylic' } : {})
    };
  }
  return {
    ...common,
    width: state.width, height: state.height, x: state.x, y: state.y,
    backgroundColor: '#f7f3e8'
  };
}

function applyWindowOptions(w) {
  if (!w || w.isDestroyed()) return;
  const d = state.desktop;
  try { w.setAlwaysOnTop(!!(d.on && d.onTop), 'floating'); } catch {}
  try {
    if (process.platform === 'win32' && typeof w.setBackgroundMaterial === 'function') {
      w.setBackgroundMaterial(d.on && d.blur && supportsAcrylic() ? 'acrylic' : 'none');
    }
  } catch {}
}

function captureBounds(w) {
  if (!w || w.isDestroyed()) return;
  const b = w.getNormalBounds();   // 最小化时也能拿到还原后的大小
  if (state.desktop.on) {
    state.desktop.bounds = { width: b.width, height: b.height, x: b.x, y: b.y };
    state.desktop.maximized = w.isMaximized();
  } else {
    state.width = b.width; state.height = b.height; state.x = b.x; state.y = b.y;
    state.maximized = w.isMaximized();
  }
  saveState();
}

function createWindow() {
  const w = new BrowserWindow(windowOptions());
  mainWindow = w;
  Menu.setApplicationMenu(null);
  const d = state.desktop;
  const wantMax = d.on ? d.maximized : state.maximized;
  w.loadFile(path.join(__dirname, 'index.html'));
  w.once('ready-to-show', () => {
    if (w.isDestroyed()) return;
    if (wantMax) w.maximize();
    applyWindowOptions(w);
    w.show();
  });
  w.webContents.on('did-finish-load', () => sendState(w));
  w.on('hide', () => { if (!w.isDestroyed()) { w.setSkipTaskbar(true); w.webContents.send('win:hidden'); } refreshTray(); });
  w.on('show', () => { if (!w.isDestroyed()) w.setSkipTaskbar(false); refreshTray(); });
  w.on('close', () => captureBounds(w));
  w.on('closed', () => { if (mainWindow === w) mainWindow = null; });
  return w;
}

/* 桌面模式和普通模式的窗口参数（frame / transparent）不能运行时切换，只能重建窗口；进度存在 localStorage 里，重开自动回到原处 */
async function rebuildWindow() {
  rebuilding = true;   // destroy 会同步触发 window-all-closed，先挡住“最后一个窗口关掉就退出”
  const old = mainWindow;
  mainWindow = null;
  if (old && !old.isDestroyed()) {
    old.removeAllListeners('close'); old.removeAllListeners('hide'); old.removeAllListeners('show');
    try { await old.webContents.executeJavaScript('window.__nrFlush && window.__nrFlush()', true); } catch {}
    old.destroy();
  }
  createWindow();
  setImmediate(() => { rebuilding = false; });
}

async function setDesktopMode(on) {
  on = !!on;
  if (state.desktop.on === on) { broadcastState(); return publicState(); }
  if (mainWindow && !mainWindow.isDestroyed()) captureBounds(mainWindow);
  state.desktop.on = on;
  saveState();
  await rebuildWindow();
  refreshTray();
  return publicState();
}

function setWindowOptions(patch) {
  const p = patch && typeof patch === 'object' ? patch : {};
  const d = state.desktop;
  if (Number.isFinite(Number(p.alpha))) d.alpha = Math.min(1, Math.max(0, Number(p.alpha)));
  if ('onTop' in p) d.onTop = !!p.onTop;
  if ('blur' in p) d.blur = !!p.blur;
  if ('outline' in p) d.outline = !!p.outline;
  saveState();
  applyWindowOptions(mainWindow);
  refreshTray();
  broadcastState();
  return publicState();
}

/* ============ 老板键：全局快捷键一键隐藏 / 恢复 ============ */
function hideWindow() { const w = mainWindow; if (w && !w.isDestroyed() && w.isVisible()) w.hide(); }
function showWindow() {
  const w = mainWindow;
  if (!w || w.isDestroyed()) return;
  if (w.isMinimized()) w.restore();
  w.show(); w.focus();
}
function toggleWindow() {
  const w = mainWindow;
  if (!w || w.isDestroyed()) return;
  if (w.isVisible() && !w.isMinimized()) hideWindow(); else showWindow();
}
function registerBossKey(accel) {
  try { globalShortcut.unregisterAll(); } catch {}
  const key = typeof accel === 'string' ? accel.trim() : '';
  if (!key) { bossKeyError = ''; return { ok: true, key: '' }; }
  try {
    if (!globalShortcut.register(key, toggleWindow)) { bossKeyError = '注册失败：' + key + ' 可能已被其它程序占用'; return { ok: false, error: bossKeyError }; }
    bossKeyError = '';
    return { ok: true, key };
  } catch (err) { bossKeyError = '快捷键无效：' + err.message; return { ok: false, error: bossKeyError }; }
}
const keyLabel = a => String(a || '').replace(/Control/g, 'Ctrl').replace(/Super/g, 'Win').replace(/\+/g, ' + ');

/* ============ 系统托盘：常驻图标，隐藏后也能恢复 ============ */
function trayIcon() {
  let icon = nativeImage.createFromPath(path.join(ASSETS, 'icon.ico'));
  if (icon.isEmpty()) icon = nativeImage.createFromPath(path.join(ASSETS, 'icon.png'));
  if (icon.isEmpty()) return null;
  if (icon.getSize().width > 24) icon = icon.resize({ width: 16, height: 16 });
  return icon;
}
function createTray() {
  if (tray) return;
  const icon = trayIcon();
  if (!icon) return;
  try { tray = new Tray(icon); } catch { tray = null; return; }
  tray.setToolTip('月读');
  tray.on('click', toggleWindow);
  refreshTray();
}
function refreshTray() {
  if (!tray || tray.isDestroyed()) return;
  const d = state.desktop;
  const visible = !!mainWindow && !mainWindow.isDestroyed() && mainWindow.isVisible();
  tray.setToolTip('月读' + (visible ? '' : '（已隐藏' + (state.bossKey ? '，' + keyLabel(state.bossKey) + ' 恢复' : '') + '）'));
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: visible ? '隐藏窗口' : '显示窗口', click: toggleWindow },
    { type: 'separator' },
    { label: '桌面模式（透明）', type: 'checkbox', checked: d.on, click: () => setDesktopMode(!state.desktop.on) },
    { label: '置顶', type: 'checkbox', checked: !!d.onTop, enabled: d.on, click: () => setWindowOptions({ onTop: !state.desktop.onTop }) },
    { label: '毛玻璃', type: 'checkbox', checked: !!d.blur, enabled: d.on && supportsAcrylic(), click: () => setWindowOptions({ blur: !state.desktop.blur }) },
    { label: '描边', type: 'checkbox', checked: !!d.outline, enabled: d.on, click: () => setWindowOptions({ outline: !state.desktop.outline }) },
    { type: 'separator' },
    { label: '老板键：' + (state.bossKey ? keyLabel(state.bossKey) + (bossKeyError ? '（不可用）' : '') : '未设置'), enabled: false },
    { type: 'separator' },
    { label: '退出月读', click: () => app.quit() }
  ]));
}

function sendState(w) { if (w && !w.isDestroyed()) w.webContents.send('win:state-changed', publicState()); }
function broadcastState() { sendState(mainWindow); }

/* ============ 窗口相关 IPC ============ */
ipcMain.handle('win:state', () => publicState());
ipcMain.handle('win:desktop', (_e, on) => setDesktopMode(on));
ipcMain.handle('win:options', (_e, patch) => setWindowOptions(patch));
ipcMain.handle('bosskey:set', (_e, accel) => {
  const key = typeof accel === 'string' ? accel.trim() : '';
  const r = registerBossKey(key);
  if (!r.ok) { const err = r.error; registerBossKey(state.bossKey); bossKeyError = err; return { ...publicState(), bossKeyError: err }; }
  state.bossKey = key;
  saveState();
  refreshTray();
  broadcastState();
  return publicState();
});
ipcMain.on('win:minimize', e => { const w = BrowserWindow.fromWebContents(e.sender); if (w) w.minimize(); });
ipcMain.on('win:close', e => { const w = BrowserWindow.fromWebContents(e.sender); if (w) w.close(); });
ipcMain.on('win:hide', () => hideWindow());
ipcMain.on('win:show', () => showWindow());

/* ============ 导入 txt / epub ============ */
function decodeTxt(buf) {
  if (buf[0] === 0xFF && buf[1] === 0xFE) return new TextDecoder('utf-16le').decode(buf);
  if (buf[0] === 0xFE && buf[1] === 0xFF) return new TextDecoder('utf-16be').decode(buf);
  try { return new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch { return new TextDecoder('gbk').decode(buf); }
}

const importFile = async (name, buf) => /\.epub$/i.test(name)
  ? parseEpub(buf, path.basename(name))
  : { name: name.replace(/\.txt$/i, ''), text: decodeTxt(buf), format: 'txt' };

ipcMain.handle('import:dialog', async e => {
  const w = BrowserWindow.fromWebContents(e.sender);
  const r = await dialog.showOpenDialog(w, { properties: ['openFile', 'multiSelections'], filters: [{ name: '电子书和文本', extensions: ['txt', 'epub'] }] });
  if (r.canceled) return [];
  const out = [];
  for (const p of r.filePaths) {
    try { out.push(await importFile(path.basename(p), fs.readFileSync(p))); }
    catch (err) { out.push({ error: path.basename(p) + '：' + err.message }); }
  }
  return out;
});
ipcMain.handle('import:buffer', async (e, { name, data }) => {
  try { return await importFile(name, Buffer.from(data)); }
  catch (err) { return { error: name + '：' + err.message }; }
});

/* ============ 联网搜书：只访问用户导入的规则里的 http(s) 地址 ============ */
function normalizeUrl(raw) {
  const u = String(raw || '').trim();
  if (!/^https?:\/\//i.test(u)) throw new Error('只允许访问 http:// 或 https:// 地址');
  return u;
}
const UA_POOL = [
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36',
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0'
];
async function requestRemote({ url, method = 'GET', data = '', headers = {}, signal }) {
  const target = normalizeUrl(url);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);
  if (signal) {
    if (signal.aborted) { clearTimeout(timer); throw Object.assign(new Error('已取消'), { name: 'AbortError' }); }
    signal.addEventListener('abort', () => controller.abort(), { once: true });
  }
  try {
    const headersOut = { 'User-Agent': UA_POOL[(Math.random() * UA_POOL.length) | 0], ...headers };
    if (!headersOut.Referer) { try { headersOut.Referer = new URL(target).origin; } catch {} }
    const init = { method: String(method).toUpperCase(), headers: headersOut, signal: controller.signal, redirect: 'follow' };
    if (init.method !== 'GET' && init.method !== 'HEAD') {
      init.body = typeof data === 'string' ? data : new URLSearchParams(data || {}).toString();
      if (!Object.keys(headers).some(k => k.toLowerCase() === 'content-type')) init.headers['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8';
    }
    const r = await fetch(target, init);
    const ab = await r.arrayBuffer();
    if (ab.byteLength > 12 * 1024 * 1024) throw new Error('远程响应超过 12 MB，已停止读取');
    // 编码：响应头 charset 优先，其次 <meta charset>；GBK/GB2312 统一按 gbk 解码
    const ct = r.headers.get('content-type') || '';
    let charset = (/charset=([\w-]+)/i.exec(ct) || [])[1];
    if (!charset) charset = (/<meta[^>]+charset=["']?([\w-]+)/i.exec(Buffer.from(ab).slice(0, 4096).toString('latin1')) || [])[1];
    charset = (charset || 'utf-8').toLowerCase();
    if (charset === 'gb2312' || charset === 'gbk' || charset === 'gb-2312') charset = 'gbk';
    if (!/^(gbk|gb18030|big5|utf-?8)$/.test(charset)) charset = 'utf-8';
    let text;
    try { text = new TextDecoder(charset).decode(ab); } catch { text = new TextDecoder('utf-8').decode(ab); }
    return { ok: r.ok, status: r.status, url: r.url, text };
  } finally { clearTimeout(timer); }
}

/* 书源引擎：so-novel 规则语义，网络层用 requestRemote */
const engine = new Engine(opts => requestRemote(opts));

ipcMain.handle('source:request', async (_e, options) => {
  try { return await requestRemote(options); }
  catch (err) { return { ok: false, status: 0, error: err.name === 'AbortError' ? '请求已取消或超时' : err.message }; }
});
ipcMain.handle('source:parse-rules', (_e, text) => {
  try { return { ok: true, rules: parseRuleListText(text) }; }
  catch (err) { return { ok: false, error: err.message }; }
});

/* 搜索 / 详情 / 目录 / 整本下载（下载可取消，进度经 search:progress 推送） */
const downloads = new Map();   // id → AbortController
const runSearch = fn => fn().then(r => ({ ok: true, r })).catch(err => ({ ok: false, error: err.code === 'aborted' ? '已取消' : err.message }));
ipcMain.handle('search:search', (_e, { rule, keyword }) => runSearch(() => engine.search(rule, String(keyword || '').trim())));
ipcMain.handle('search:book-info', (_e, { rule, url }) => runSearch(() => engine.bookInfo(rule, url)));
ipcMain.handle('search:toc', (_e, { rule, url }) => runSearch(() => engine.toc(rule, url)));
ipcMain.handle('search:download', async (e, { id, rule, url }) => {
  const controller = new AbortController();
  downloads.set(id, controller);
  const wc = e.sender;
  try {
    const book = await engine.downloadBook(rule, url, {
      signal: controller.signal,
      onProgress: (done, total, title, failed) => { try { if (!wc.isDestroyed()) wc.send('search:progress', { id, done, total, title, failed }); } catch {} }
    });
    return { ok: true, book };
  } catch (err) {
    return { ok: false, error: controller.signal.aborted || err.code === 'aborted' ? '已取消' : err.message };
  } finally { downloads.delete(id); }
});
ipcMain.on('search:cancel', (_e, id) => { const c = downloads.get(id); if (c) c.abort(); });
ipcMain.on('open-url', (e, url) => { try { shell.openExternal(normalizeUrl(url)); } catch {} });
ipcMain.handle('donate:images', () => {
  const out = {};
  for (const [k, f] of [['wechat', 'wechat.png'], ['alipay', 'alipay.png'], ['any', 'donate.png']]) {
    const p = path.join(ASSETS, f);
    if (fs.existsSync(p)) out[k] = 'data:image/png;base64,' + fs.readFileSync(p).toString('base64');
  }
  return out;
});

/* ============ 数据备份：导出 / 导入 书架+进度+书签+书源+设置（JSON 文件） ============ */
ipcMain.handle('backup:save', async (e, { defaultName, data }) => {
  try {
    const w = BrowserWindow.fromWebContents(e.sender);
    const r = await dialog.showSaveDialog(w, { defaultPath: defaultName || '月读备份.json', filters: [{ name: '月读备份', extensions: ['json'] }] });
    if (r.canceled || !r.filePath) return { ok: false, canceled: true };
    if (Buffer.byteLength(String(data || '')) > 512 * 1024 * 1024) return { ok: false, error: '备份数据过大' };
    fs.writeFileSync(r.filePath, String(data));
    return { ok: true, path: r.filePath };
  } catch (err) { return { ok: false, error: err.message }; }
});
ipcMain.handle('backup:load', async e => {
  try {
    const w = BrowserWindow.fromWebContents(e.sender);
    const r = await dialog.showOpenDialog(w, { properties: ['openFile'], filters: [{ name: '月读备份', extensions: ['json'] }] });
    if (r.canceled || !r.filePaths[0]) return { ok: false, canceled: true };
    const data = JSON.parse(fs.readFileSync(r.filePaths[0], 'utf8').replace(/^\uFEFF/, ''));
    return { ok: true, data };
  } catch (err) { return { ok: false, error: err.message }; }
});

/* ============ 自定义字体：字体文件放 userData/fonts，渲染进程按需取 data URL 注册 @font-face ============ */
const fontsDir = () => path.join(app.getPath('userData'), 'fonts');
const FONT_MIME = { ttf: 'font/ttf', otf: 'font/otf', ttc: 'font/collection', woff: 'font/woff', woff2: 'font/woff2' };
function listFonts() {
  try {
    return fs.readdirSync(fontsDir())
      .filter(f => FONT_MIME[f.split('.').pop().toLowerCase()])
      .map(f => ({ name: f, family: f.replace(/\.[^.]+$/, '') }));
  } catch { return []; }
}
ipcMain.handle('font:pick', async e => {
  try {
    const w = BrowserWindow.fromWebContents(e.sender);
    const r = await dialog.showOpenDialog(w, { properties: ['openFile', 'multiSelections'], filters: [{ name: '字体文件', extensions: Object.keys(FONT_MIME) }] });
    if (r.canceled) return { ok: false, canceled: true };
    fs.mkdirSync(fontsDir(), { recursive: true });
    const seen = new Set();
    for (const p of r.filePaths) {
      const base = path.basename(p);
      if (seen.has(base.toLowerCase())) continue;
      seen.add(base.toLowerCase());
      fs.copyFileSync(p, path.join(fontsDir(), base));
    }
    return { ok: true, fonts: listFonts() };
  } catch (err) { return { ok: false, error: err.message }; }
});
ipcMain.handle('font:list', () => ({ ok: true, fonts: listFonts() }));
ipcMain.handle('font:read', (_e, name) => {
  try {
    const safe = path.basename(String(name || ''));
    const ext = safe.split('.').pop().toLowerCase();
    const p = path.join(fontsDir(), safe);
    if (!FONT_MIME[ext] || !fs.existsSync(p)) return { ok: false, error: '字体不存在' };
    return { ok: true, dataUrl: 'data:' + FONT_MIME[ext] + ';base64,' + fs.readFileSync(p).toString('base64') };
  } catch (err) { return { ok: false, error: err.message }; }
});
ipcMain.handle('font:remove', (_e, name) => {
  try {
    const p = path.join(fontsDir(), path.basename(String(name || '')));
    if (fs.existsSync(p)) fs.unlinkSync(p);
    return { ok: true, fonts: listFonts() };
  } catch (err) { return { ok: false, error: err.message }; }
});

/* ============ 启动 ============ */
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => showWindow());
  app.whenReady().then(() => {
    state = loadState();
    createWindow();
    createTray();
    const r = registerBossKey(state.bossKey);
    if (!r.ok) console.warn(r.error);
  });
}
// 重建窗口时会先销毁旧窗口，那一刻不算“用户关掉了所有窗口”
app.on('window-all-closed', () => { if (rebuilding || (mainWindow && !mainWindow.isDestroyed())) return; app.quit(); });
app.on('will-quit', () => { try { globalShortcut.unregisterAll(); } catch {} });
