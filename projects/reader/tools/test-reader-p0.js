/* P0 功能冒烟测试：净化规则 / 书签 / 进度条拖动 / 排版变量 / EPUB 原生目录 / 书架筛选排序 / 备份恢复
   用法：npx electron tools/test-reader-p0.js    （临时 userData，退出码 0 表示全部通过） */
const path = require('path');
const fs = require('fs');
const os = require('os');
const electron = require('electron');

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'yuedu-p0-test-'));
process.env.NR_DATA_DIR = dir;

const { app, BrowserWindow } = electron;
require(path.join(__dirname, '..', 'src', 'main.js'));

const wait = ms => new Promise(r => setTimeout(r, ms));
const logFile = path.join(__dirname, '..', '.tmp-check', 'test-reader-p0.log');
const lines = [];
function say(line) { lines.push(line); console.log(line); try { fs.mkdirSync(path.dirname(logFile), { recursive: true }); fs.writeFileSync(logFile, lines.join('\n') + '\n'); } catch {} }
let failed = 0;
function check(name, ok, extra) {
  if (!ok) failed++;
  say((ok ? 'PASS  ' : 'FAIL  ') + name + (extra === undefined ? '' : '   [' + extra + ']'));
}
const win = () => BrowserWindow.getAllWindows()[0];
const evalJs = code => win().webContents.executeJavaScript(code, true);
process.on('uncaughtException', err => say('-- uncaughtException ' + (err && err.stack || err)));
process.on('unhandledRejection', err => say('-- unhandledRejection ' + (err && err.stack || err)));

(async () => {
  await app.whenReady();
  let quitRequested = false;
  app.on('before-quit', e => { e.preventDefault(); quitRequested = true; });
  await wait(3000);

  /* ---- 造书：两段正文 + 一行广告 + 两个标准章节 ---- */
  await evalJs(`(async () => {
    const text = ['第1章 开始', '正文内容甲'.repeat(20), '广告行 请记住本站网址', '正文内容乙'.repeat(20), '第2章 后续', '正文内容丙'.repeat(20)].join('\\n');
    await dbPut({ id: 'p0-book', name: 'P0测试书', text, size: text.length, format: 'txt', added: Date.now() });
    await openBook('p0-book');
  })()`);
  await wait(800);
  let r = await evalJs('paras.length');
  check('造书并打开（6 段）', r === 6, 'paras=' + r);
  r = await evalJs('chapters.map(c => c.title).join("|")');
  check('章节识别（第1章/第2章）', r === '第1章 开始|第2章 后续', r);

  /* ---- 净化规则：全局规则删除广告行 ---- */
  await evalJs(`(async () => {
    setRules(GLOBAL_RULES_KEY, [{ enabled: true, pattern: '^广告行.*$', replacement: '' }]);
    await openBook('p0-book');
  })()`);
  await wait(800);
  r = await evalJs('JSON.stringify(paras.map(p => p.textContent))');
  check('净化规则删除广告段', !r.includes('广告行') && r.includes('正文内容丙'), r.slice(0, 80));
  r = await evalJs('compileRules("p0-book").length');
  check('规则编译缓存生效', r === 1, 'rules=' + r);
  await evalJs(`setRules(GLOBAL_RULES_KEY, []); openBook('p0-book'); 1`);
  await wait(800);
  r = await evalJs('paras.length');
  check('清空规则后还原 6 段', r === 6, 'paras=' + r);

  /* ---- EPUB 原生目录：非“第X章”标题（序章/楔子）也能进目录 ---- */
  await evalJs(`(async () => {
    const text = ['楔子 风雪', '正文甲'.repeat(10), '第一章  Dawn', '正文乙'.repeat(10)].join('\\n');
    await dbPut({ id: 'p0-epub', name: 'EPUB目录书', text, size: text.length, format: 'epub', added: Date.now(),
      toc: [{ title: '楔子 风雪', index: 0 }, { title: '序章·启程', index: 2 }] });
    await openBook('p0-epub');
  })()`);
  await wait(800);
  r = await evalJs('chapters.map(c => c.title + "@" + c.i).join("|")');
  check('EPUB 原生目录优先于正则', r === '楔子 风雪@0|序章·启程@2', r);
  r = await evalJs('document.querySelectorAll("#reader p.h").length');
  check('章节起点段落带 h 样式', r === 2, 'p.h=' + r);

  /* ---- 书签 ---- */
  await evalJs(`openBook('p0-book'); 1`);
  await wait(800);
  await evalJs(`window.scrollTo(0, 0); toggleMark(); 1`);
  await wait(200);
  r = await evalJs('JSON.parse(localStorage.getItem("nr-marks-p0-book") || "[]").length');
  check('加书签已保存', r === 1, 'marks=' + r);
  r = await evalJs('document.querySelectorAll("#reader p.bm").length');
  check('正文段落有书签标记', r === 1, 'bm=' + r);
  r = await evalJs('document.querySelectorAll("#markList .mk").length');
  check('书签面板渲染 1 条', r === 1, 'rows=' + r);
  await evalJs(`toggleMark(); 1`);
  r = await evalJs('JSON.parse(localStorage.getItem("nr-marks-p0-book") || "[]").length');
  check('再按一次移除书签', r === 0, 'marks=' + r);

  /* ---- 进度条拖动 ---- */
  await evalJs(`window.scrollTo(0, 0); 1`);
  await wait(150);
  r = await evalJs(`(async () => { scrubTo(innerWidth / 2); await new Promise(r2 => setTimeout(r2, 200)); return Math.round(window.scrollY); })()`);
  check('进度条拖动定位到中段', r > 100, 'scrollY=' + r);
  r = await evalJs('document.getElementById("progress").style.width');
  check('拖动后进度填充同步', parseFloat(r) > 20, r);

  /* ---- 排版变量 ---- */
  await evalJs(`settings.paraSpace = 0.2; settings.indent = 0; settings.margin = 60; applySettings(); 1`);
  await wait(150);
  r = await evalJs(`(() => { const s = getComputedStyle(document.querySelector("#reader p"));
    return { margin: s.marginBottom, indent: s.textIndent, pad: getComputedStyle(document.getElementById("reader")).paddingLeft }; })()`);
  check('段间距变量生效', r.margin === '4px', JSON.stringify(r));   // 0.2em × 20px = 4px
  check('首行缩进可关（0px）', r.indent === '0px', r.indent);
  check('页边距变量生效', r.pad === '60px', r.pad);
  await evalJs(`settings.fontFamily = '"SimSun", "宋体", serif'; applySettings(); 1`);
  r = await evalJs('getComputedStyle(document.getElementById("reader")).fontFamily');
  check('字体选择生效', r.includes('SimSun'), r);
  await evalJs(`Object.assign(settings, { paraSpace: 0.9, indent: 2, margin: 28, fontFamily: '' }); applySettings(); 1`);

  /* ---- 书架：筛选 / 排序 / 编辑 ---- */
  await evalJs(`showShelf(); 1`);
  await wait(300);
  r = await evalJs('!!document.getElementById("shelfSort") && !!document.getElementById("shelfFilter") && document.querySelectorAll("#shelf .book").length');
  check('书架有筛选/排序控件和 2 本书', r === 2, 'books=' + r);
  r = await evalJs(`(async () => {
    const inp = document.getElementById('shelfFilter');
    inp.value = 'EPUB';
    inp.oninput();
    await new Promise(r2 => setTimeout(r2, 100));
    return document.querySelectorAll('#shelf .book').length;
  })()`);
  check('书名筛选生效', r === 1, 'matched=' + r);
  r = await evalJs(`(async () => {
    const inp = document.getElementById('shelfFilter');
    inp.value = '';
    inp.oninput();
    await openBookEdit('p0-epub');
    document.getElementById('bookNameEdit').value = '改名后的书';
    document.getElementById('btnBookSave').onclick();
    await new Promise(r2 => setTimeout(r2, 300));
    const b = await dbGet('p0-epub');
    return b.name;
  })()`);
  check('编辑书名保存入库', r === '改名后的书', r);
  r = await evalJs(`document.querySelectorAll('#shelf .book .cover').length`);
  check('书架每本都有封面（无封面图时用首字色块占位）', r >= 2, 'covers=' + r);

  /* ---- 备份恢复：导出 → 清空 → 导入 ---- */
  await evalJs(`setProgress('p0-epub', { index: 0, offset: 0, ratio: 0.5, time: Date.now() }); 1`);
  r = await evalJs(`(async () => {
    const data = await collectBackupData();
    // 清场：删掉一本书、清进度书签规则设置
    await dbDel('p0-book');
    localStorage.removeItem('nr-progress-p0-epub');
    localStorage.removeItem('nr-marks-p0-epub');
    localStorage.removeItem('nr-settings');
    const n = await applyBackupData(JSON.parse(JSON.stringify(data)));
    const bs = await dbAll();
    return { n, count: bs.length, hasP0: bs.some(b => b.id === 'p0-book'), name: (await dbGet('p0-epub')).name,
      settings: !!localStorage.getItem('nr-settings'), progress: (getProgress('p0-epub') || {}).ratio };
  })()`);
  check('备份恢复书籍数量', r && r.n === 2, JSON.stringify(r));
  check('备份恢复被删的书', r && r.hasP0 === true);
  check('备份恢复书名', r && r.name === '改名后的书', r && r.name);
  check('备份恢复设置', r && r.settings === true);
  check('备份恢复阅读进度', r && r.progress === 0.5, r && r.progress);

  /* ---- 收工 ---- */
  say('\n' + (failed ? failed + ' 项失败' : '全部通过'));
  win().close();
  await wait(800);
  app.exit(failed ? 1 : 0);
})().catch(err => { say('FAIL  测试异常：' + (err && err.stack || err)); app.exit(1); });
