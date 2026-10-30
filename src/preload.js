const { contextBridge, ipcRenderer } = require('electron');

// 主进程创建窗口时把当前窗口状态塞进启动参数，渲染进程首屏就能按桌面模式排版
function initialState() {
  const arg = (process.argv || []).find(a => a.startsWith('--nr-state='));
  if (!arg) return null;
  try { return JSON.parse(decodeURIComponent(arg.slice('--nr-state='.length))); } catch { return null; }
}

contextBridge.exposeInMainWorld('app', {
  initialState: initialState(),
  openUrl: url => ipcRenderer.send('open-url', url),
  importDialog: () => ipcRenderer.invoke('import:dialog'),
  importBuffer: (name, data) => ipcRenderer.invoke('import:buffer', { name, data }),
  requestSource: options => ipcRenderer.invoke('source:request', options),
  parseSourceRules: text => ipcRenderer.invoke('source:parse-rules', text),
  donateImages: () => ipcRenderer.invoke('donate:images'),

  /* 联网搜书：搜索 / 详情 / 目录 / 整本下载（带进度与取消） */
  searchBooks: (rule, keyword) => ipcRenderer.invoke('search:search', { rule, keyword }),
  searchBookInfo: (rule, url) => ipcRenderer.invoke('search:book-info', { rule, url }),
  searchToc: (rule, url) => ipcRenderer.invoke('search:toc', { rule, url }),
  searchDownload: (id, rule, url) => ipcRenderer.invoke('search:download', { id, rule, url }),
  searchCancel: id => ipcRenderer.send('search:cancel', id),
  onSearchProgress: cb => ipcRenderer.on('search:progress', (_e, p) => cb(p)),

  /* 窗口：老板键 / 托盘 / 透明桌面模式 / 置顶 · 毛玻璃 · 描边 */
  windowState: () => ipcRenderer.invoke('win:state'),
  setDesktopMode: on => ipcRenderer.invoke('win:desktop', !!on),
  setWindowOptions: patch => ipcRenderer.invoke('win:options', patch),
  setBossKey: accel => ipcRenderer.invoke('bosskey:set', accel),
  minimizeWindow: () => ipcRenderer.send('win:minimize'),
  closeWindow: () => ipcRenderer.send('win:close'),
  hideWindow: () => ipcRenderer.send('win:hide'),
  showWindow: () => ipcRenderer.send('win:show'),
  onStateChanged: cb => ipcRenderer.on('win:state-changed', (_e, st) => cb(st)),
  onHidden: cb => ipcRenderer.on('win:hidden', () => cb()),

  /* 数据备份与自定义字体 */
  backupSave: (defaultName, data) => ipcRenderer.invoke('backup:save', { defaultName, data }),
  backupLoad: () => ipcRenderer.invoke('backup:load'),
  fontPick: () => ipcRenderer.invoke('font:pick'),
  fontList: () => ipcRenderer.invoke('font:list'),
  fontRead: name => ipcRenderer.invoke('font:read', name),
  fontRemove: name => ipcRenderer.invoke('font:remove', name)
});
