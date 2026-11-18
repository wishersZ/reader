/* P0 功能冒烟测试：净化规则 / 书签 / 进度条拖动 / 排版变量 / EPUB 原生目录 / 书架筛选排序 / 备份恢复
   用法：npm run test:reader（临时 userData，退出码 0 表示全部通过）
   基建（防吊死求值/状态轮询/看门狗/断管防护）都在 tools/test-kit.js。 */
const path = require('path');
const fs = require('fs');
const os = require('os');
const electron = require('electron');
const { guard, wait, makeLogger, makeEval, waitFor, armWatchdog } = require('./test-kit');

const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'yuedu-p0-test-'));
process.env.NR_DATA_DIR = dir;

const { app, BrowserWindow } = electron;
require(path.join(__dirname, '..', 'src', 'main.js'));

const logger = makeLogger('test-reader-p0.log');
const { say, check } = logger;
guard(m => say(m));
const evalJs = makeEval(() => BrowserWindow.getAllWindows()[0]);

armWatchdog(say, app, 120000);

(async () => {
  await app.whenReady();
  let quitRequested = false;
  app.on('before-quit', e => { e.preventDefault(); quitRequested = true; });

  /* 打开一本书并轮询等正文渲染出来（渲染是异步的，固定 sleep 会假失败） */
  const openAndWait = async (id, expectParas) => {
    await evalJs(`(async () => { await openBook('${id}'); })()`);
    await waitFor(() => evalJs(`currentId === '${id}' && document.querySelectorAll("#reader p").length ${expectParas ? '=== ' + expectParas : '> 0'}`), 5000);
  };

  /* ---- 造书：两段正文 + 一行广告 + 两个标准章节 ---- */
  await evalJs(`(async () => {
    const text = ['第1章 开始', '正文内容甲'.repeat(20), '广告行 请记住本站网址', '正文内容乙'.repeat(20), '第2章 后续', '正文内容丙'.repeat(20)].join('\\n');
    await dbPut({ id: 'p0-book', name: 'P0测试书', text, size: text.length, format: 'txt', added: Date.now() });
    await openBook('p0-book');
  })()`);
  await waitFor(() => evalJs('currentId === "p0-book" && document.querySelectorAll("#reader p").length === 6'), 5000);
  const paraCount = await evalJs('paras.length');
  const chaps = await evalJs('chapters.map(c => c.title).join("|")');
  check('造书并打开（6 段）+ 章节识别', paraCount === 6 && chaps === '第1章 开始|第2章 后续', 'paras=' + paraCount + ' chapters=' + chaps);

  /* ---- 净化规则：全局规则删除广告行 ---- */
  await evalJs(`(async () => {
    setRules(GLOBAL_RULES_KEY, [{ enabled: true, pattern: '^广告行.*$', replacement: '' }]);
    await openBook('p0-book');
  })()`);
  await waitFor(() => evalJs('document.querySelectorAll("#reader p").length === 5'), 5000);
  const cleaned = await evalJs('JSON.stringify(paras.map(p => p.textContent))');
  check('净化规则删除广告段', typeof cleaned === 'string' && !cleaned.includes('广告行') && cleaned.includes('正文内容丙'), (cleaned || '').slice(0, 80));
  const cache = await evalJs('compileRules("p0-book").length');
  check('规则编译缓存生效', cache === 1, 'rules=' + cache);
  await evalJs(`(async () => { setRules(GLOBAL_RULES_KEY, []); await openBook('p0-book'); })()`);
  await waitFor(() => evalJs('document.querySelectorAll("#reader p").length === 6'), 5000);
  check('清空规则后还原 6 段', (await evalJs('paras.length')) === 6);

  /* ---- EPUB 原生目录：非“第X章”标题（序章/楔子）也能进目录 ---- */
  await evalJs(`(async () => {
    const text = ['楔子 风雪', '正文甲'.repeat(10), '第一章  Dawn', '正文乙'.repeat(10)].join('\\n');
    await dbPut({ id: 'p0-epub', name: 'EPUB目录书', text, size: text.length, format: 'epub', added: Date.now(),
      toc: [{ title: '楔子 风雪', index: 0 }, { title: '序章·启程', index: 2 }] });
    await openBook('p0-epub');
  })()`);
  await waitFor(() => evalJs('currentId === "p0-epub" && document.querySelectorAll("#reader p").length > 0'), 5000);
  const toc = await evalJs('chapters.map(c => c.title + "@" + c.i).join("|")');
  const hCount = await evalJs('document.querySelectorAll("#reader p.h").length');
  check('EPUB 原生目录优先于正则', toc === '楔子 风雪@0|序章·启程@2' && hCount === 2, 'toc=' + toc + ' p.h=' + hCount);

  /* ---- 书签 ---- */
  await openAndWait('p0-book');
  await evalJs(`window.scrollTo(0, 0); toggleMark(); 1`);
  await wait(200);
  const marks1 = await evalJs('JSON.parse(localStorage.getItem("nr-marks-p0-book") || "[]").length');
  const bm1 = await evalJs('document.querySelectorAll("#reader p.bm").length');
  const rows1 = await evalJs('document.querySelectorAll("#markList .mk").length');
  check('加书签已保存、正文标记、面板渲染', marks1 === 1 && bm1 === 1 && rows1 === 1, JSON.stringify({ marks1, bm1, rows1 }));
  await evalJs(`toggleMark(); 1`);
  check('再按一次移除书签', (await evalJs('JSON.parse(localStorage.getItem("nr-marks-p0-book") || "[]").length')) === 0);

  /* ---- 进度条拖动 ---- */
  await evalJs(`window.scrollTo(0, 0); 1`);
  await wait(150);
  const scrubY = await evalJs(`(async () => { scrubTo(innerWidth / 2); await new Promise(r2 => setTimeout(r2, 200)); return Math.round(window.scrollY); })()`);
  const fillW = await evalJs('document.getElementById("progress").style.width');
  check('进度条拖动定位并同步填充', scrubY > 100 && parseFloat(fillW) > 20, 'scrollY=' + scrubY + ' width=' + fillW);

  /* ---- 排版变量 ---- */
  await evalJs(`settings.paraSpace = 0.2; settings.indent = 0; settings.margin = 60; applySettings(); 1`);
  await wait(150);
  const typeStyle = await evalJs(`(() => { const s = getComputedStyle(document.querySelector("#reader p"));
    return { margin: s.marginBottom, indent: s.textIndent, pad: getComputedStyle(document.getElementById("reader")).paddingLeft }; })()`);
  check('段间距/缩进/页边距变量生效', !!typeStyle && typeStyle.margin === '4px' && typeStyle.indent === '0px' && typeStyle.pad === '60px', JSON.stringify(typeStyle));   // 0.2em × 20px = 4px
  await evalJs(`settings.fontFamily = '"SimSun", "宋体", serif'; applySettings(); 1`);
  const font = await evalJs('getComputedStyle(document.getElementById("reader")).fontFamily');
  check('字体选择生效', typeof font === 'string' && font.includes('SimSun'), font);
  await evalJs(`Object.assign(settings, { paraSpace: 0.9, indent: 2, margin: 28, fontFamily: '' }); applySettings(); 1`);

  /* ---- 书架：筛选 / 编辑 / 封面 ---- */
  await evalJs(`showShelf(); 1`);
  await wait(300);
  const shelfBooks = await evalJs(`!!document.getElementById("shelfSort") && !!document.getElementById("shelfFilter") && document.querySelectorAll("#shelf .book").length`);
  const covers = await evalJs(`document.querySelectorAll('#shelf .book .cover').length`);
  check('书架控件齐全且每本有封面', shelfBooks === 2 && covers >= 2, 'books=' + shelfBooks + ' covers=' + covers);
  const filtered = await evalJs(`(async () => {
    const inp = document.getElementById('shelfFilter');
    inp.value = 'EPUB';
    inp.oninput();
    await new Promise(r2 => setTimeout(r2, 100));
    return document.querySelectorAll('#shelf .book').length;
  })()`);
  check('书名筛选生效', filtered === 1, 'matched=' + filtered);
  const renamed = await evalJs(`(async () => {
    const inp = document.getElementById('shelfFilter');
    inp.value = '';
    inp.oninput();
    await openBookEdit('p0-epub');
    document.getElementById('bookNameEdit').value = '改名后的书';
    document.getElementById('btnBookSave').onclick();
    await new Promise(r2 => setTimeout(r2, 300));
    return (await dbGet('p0-epub')).name;
  })()`);
  check('编辑书名保存入库', renamed === '改名后的书', renamed);

  /* ---- 备份恢复：导出 → 清空 → 导入 ---- */
  await evalJs(`setProgress('p0-epub', { index: 0, offset: 0, ratio: 0.5, time: Date.now() }); 1`);
  const bk = await evalJs(`(async () => {
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
  check('备份恢复完整（数量/被删书/书名/设置/进度）',
    !!bk && bk.n === 2 && bk.hasP0 === true && bk.name === '改名后的书' && bk.settings === true && bk.progress === 0.5,
    JSON.stringify(bk));

  /* ---- 收工 ---- */
  say('\n' + (logger.failed ? logger.failed + ' 项失败' : '全部通过'));
  BrowserWindow.getAllWindows()[0].close();
  await wait(800);
  app.exit(logger.failed ? 1 : 0);
})().catch(err => { say('FAIL  测试异常：' + (err && err.stack || err)); app.exit(1); });
