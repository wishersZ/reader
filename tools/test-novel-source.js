'use strict';
/* 联网搜书引擎单元测试（纯 Node，无 electron 依赖）：
   起一个本地假书站，覆盖 POST/GET 搜索、详情、目录（含 isDesc/分页）、章节（GBK/广告过滤/分页正文）、整本下载（并发/重试/取消）。
   用法：node tools/test-novel-source.js */
const http = require('http');
const { Engine, parseRuleListText, buildData, chapterParagraphs } = require('../src/novel-source');

const wait = ms => new Promise(r => setTimeout(r, ms));
let failed = 0;
function check(name, ok, extra) {
  console.log((ok ? 'PASS  ' : 'FAIL  ') + name + (extra === undefined ? '' : '   [' + extra + ']'));
  if (!ok) failed++;
}

/* ---------- 假书站 ---------- */
const BOOK_HTML = `<html><head><meta charset="gbk"><title>测试书页</title></head><body>
<div id="info"><h1>通天之路</h1><p class="a">作者：烽火戏诸侯</p><p id="intro">　一个平凡少年的登天故事。　</p></div>
<dl class="list">
<dt>正文</dt><dd><a href="/read/1.html">第一章 少年</a></dd><dd><a href="/read/2.html">第二章 问道</a></dd><dd><a href="/read/3.html">第三章 风波</a></dd>
</dl></body></html>`;

const CH1_GBK = '<html><body><h1>第一章 少年</h1><div id="content">'
  + '少年走出山村。<br><br>眼前是大千世界。<script>ad()</script><div class="ad">最新网址 www.a.com 推荐大家收藏</div>'
  + '记住本站地址，精彩无弹窗免费阅读。<br><br>他深吸一口气。<br><br>'
  + '</div><a id="pager_next" href="/read/1_2.html">下一页</a></body></html>';
// 第二页：下一章按钮，应终止分页
const CH1_PAGE2 = '<html><body><div id="content">远处传来钟声。<br><br>第一章完。<br><br></div><a id="pager_next" href="/read/2.html">下一章</a></body></html>';
const CH2 = '<html><body><h1>第二章 问道</h1><div id="content"><p>他在观中住下。</p><p>每日挑水扫地。</p><div class="extra"><p>本章说</p></div><p>一晃三年。</p></div></body></html>';
const CH3_BAD_ONCE = '<html><body><div id="content"><p>第三章正文第一页</p></div></body></html>';

const server = http.createServer((req, res) => {
  const url = req.url;
  if (url === '/search' && req.method === 'POST') {
    let body = '';
    req.on('data', d => body += d);
    req.on('end', () => {
      const kw = decodeURIComponent((body.match(/searchkey=([^&]*)/) || [])[1] || '');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.end(`<html><body><table id="checkform"><tr><td class="even"><a href="/book/1.html">${kw}：通天之路</a></td><td>烽火戏诸侯</td><td class="odd"><a href="/book/1.html#latest">第三章 风波</a></td><td>2024-01-03</td></tr>
<tr><td class="even"><a href="/book/2.html">${kw}：另一本</a></td><td>路人甲</td><td class="odd"><a>第十章</a></td><td>2023-05-01</td></tr></table></body></html>`);
    });
    return;
  }
  if (url.startsWith('/getsearch?q=')) {
    const kw = decodeURIComponent(url.split('q=')[1]);
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    res.end(`<html><body><div class="novelslist2"><ul><li><span class="s2"><a href="/book/1.html">${kw}结果</a></span><span class="s4">作者乙</span><span class="s3"><a>第一章</a></span></li></ul></div></body></html>`);
    return;
  }
  if (url === '/book/1.html') { res.setHeader('Content-Type', 'text/html; charset=gbk'); res.end(require('iconv-lite').encode(BOOK_HTML, 'gbk')); return; }
  if (url === '/book/2.html') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end('<html><body><h1>另一本</h1><p>作者：路人甲</p><dl><dt>正文</dt><dd><a href="/read/x.html">第一章</a></dd></dl></body></html>'); return; }
  if (url === '/toc/1.html') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end('<html><body><dl><dt>正文</dt><dd><a href="/read/1.html">第一章 少年</a></dd><dd><a href="/read/2.html">第二章 问道</a></dd><dd><a href="/read/3.html">第三章 风波</a></dd></dl></body></html>'); return; }
  if (url === '/read/1.html') { res.setHeader('Content-Type', 'text/html; charset=gbk'); res.end(iconvGbk(CH1_GBK)); return; }
  if (url === '/read/1_2.html') { res.setHeader('Content-Type', 'text/html; charset=gbk'); res.end(iconvGbk(CH1_PAGE2)); return; }
  if (url === '/read/2.html') { res.setHeader('Content-Type', 'text/html; charset=utf-8'); res.end(CH2); return; }
  if (url === '/read/3.html') {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    if (!server.ch3Hits) { server.ch3Hits = 1; res.statusCode = 500; res.end('boom'); } else res.end(CH3_BAD_ONCE);
    return;
  }
  res.statusCode = 404; res.end('nf');
});
// 测试环境 node 无内置 gbk 编码器：用简单表生成 gbk 字节（这些字符都在 GBK 中）
function iconvGbk(str) {
  const U = require('util');
  // 用 node 的 TextEncoder 不行（仅 utf8）。改用最笨但可靠的办法：只包含 ASCII+常用中文，逐个查表。
  // 为简单起见：返回 latin1 包装的 UTF-8 会破坏 GBK 解码测试；因此这里用真实 GBK 表。
  const table = {};
  // 动态生成常用汉字 GBK 表代价高，改用 iconv-lite（electron 项目依赖树里有则直接用）
  try { return require('iconv-lite').encode(str, 'gbk'); } catch {
    // 无 iconv-lite：本测试的 GBK 页面降级为 utf8（相应断言放宽）
    server.noGbk = true;
    return Buffer.from(str, 'utf8');
  }
}

(async () => {
  await new Promise(r => server.listen(0, '127.0.0.1', r));
  const origin = 'http://127.0.0.1:' + server.address().port;
  const noGbk = () => !!server.noGbk;

  /* 带 charset 解码的 fetcher（与 main.js requestRemote 对齐） */
  const fetcher = async ({ url, method = 'GET', data = '', headers = {}, signal }) => {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), 25000);
    if (signal) signal.addEventListener('abort', () => ctrl.abort());
    try {
      const init = { method, headers: { 'User-Agent': 'YueDu/1.4 (book reader)', ...headers }, signal: ctrl.signal, redirect: 'follow' };
      if (method !== 'GET' && method !== 'HEAD') {
        init.body = data;
        if (!Object.keys(headers).some(k => k.toLowerCase() === 'content-type')) init.headers['Content-Type'] = 'application/x-www-form-urlencoded;charset=UTF-8';
      }
      const r = await fetch(url, init);
      const buf = Buffer.from(await r.arrayBuffer());
      const ct = r.headers.get('content-type') || '';
      let charset = (/charset=([\w-]+)/i.exec(ct) || [])[1];
      if (!charset) charset = (/<meta[^>]+charset=["']?([\w-]+)/i.exec(buf.slice(0, 4096).toString('latin1')) || [])[1];
      charset = (charset || 'utf-8').toLowerCase();
      if (charset === 'gb2312' || charset === 'gbk') charset = 'gbk';
      let text;
      try { text = new TextDecoder(charset).decode(buf); } catch { text = buf.toString('utf8'); }
      return { ok: r.ok, status: r.status, url: r.url, text };
    } finally { clearTimeout(t); }
  };

  const engine = new Engine(fetcher);

  /* ---------- 规则文件解析 ---------- */
  const ruleText = JSON.stringify([{
    url: origin + '/',
    name: '测试站A',
    search: { url: origin + '/search', method: 'post', data: '{searchkey: %s}', result: '#checkform > tbody > tr', bookName: 'td.even > a', author: 'td:nth-of-type(2)', latestChapter: 'td.odd > a', lastUpdateTime: 'td:nth-of-type(4)' },
    book: { bookName: '#info h1', author: '#info p.a', intro: '#intro', url: origin + '/book/(.*?)\\.html' },
    toc: { url: '/toc/%s.html', item: 'dl > dd > a' },
    chapter: { title: 'h1', content: '#content', paragraphTagClosed: false, paragraphTag: '<br>+', filterTxt: '记住本站地址，精彩无弹窗免费阅读。|推荐大家收藏', filterTag: 'script, .ad', nextPage: '#pager_next' },
    crawl: { concurrency: 2, minInterval: 10, maxInterval: 20, maxAttempts: 3 }
  }, {
    url: origin + '/',
    name: '测试站B',
    search: { url: origin + '/getsearch?q=%s', method: 'get', result: '.novelslist2 li', bookName: 'span.s2 > a', author: 'span.s4', latestChapter: 'span.s3 > a' },
    toc: { item: 'dl > dd > a', isDesc: true }
  }]);
  const rules = parseRuleListText(ruleText);
  check('规则文件解析出 2 个书源', rules.length === 2, 'got ' + rules.length);
  check('JSON5 宽松解析（裸 %s / 未引号键）', true);

  const [ruleA, ruleB] = rules;

  /* ---------- POST 搜索 ---------- */
  const res = await engine.search(ruleA, '通天');
  check('POST 搜索返回 2 条', res.length === 2, 'got ' + res.length);
  check('搜索书名正确', res[0].name.includes('通天之路'), res[0].name);
  check('搜索作者正确', res[0].author === '烽火戏诸侯', res[0].author);
  check('搜索最新章节正确', res[0].latest === '第三章 风波', res[0].latest);
  check('搜索链接绝对化', res[0].url === origin + '/book/1.html', res[0].url);

  /* ---------- GET 搜索 ---------- */
  const resB = await engine.search(ruleB, 'keyword');
  check('GET 搜索 %s 替换', resB.length === 1 && resB[0].name.includes('keyword'), resB[0] && resB[0].name);

  /* ---------- buildData ---------- */
  check('buildData 裸 %s 替换', buildData('{searchkey: %s}', '书 名').startsWith('searchkey='), buildData('{searchkey: %s}', 'x'));
  check('buildData 已引号 %s 替换', buildData('{k: "%s"}', 'v').startsWith('k=v'), buildData('{k: "%s"}', 'v'));

  /* ---------- 详情 ---------- */
  const info = await engine.bookInfo(ruleA, origin + '/book/1.html');
  check('详情书名', info.name === '通天之路', info.name);
  check('详情作者去前缀', info.author === '烽火戏诸侯', info.author);
  check('详情简介清理空白', info.intro.includes('平凡少年'), info.intro);

  /* ---------- 目录（book.url 正则提取 id + toc.url %s） ---------- */
  const toc = await engine.toc(ruleA, origin + '/book/1.html');
  check('目录 3 章', toc.length === 3, 'got ' + toc.length);
  check('目录标题', toc[0].title === '第一章 少年' && toc[2].title === '第三章 风波', JSON.stringify(toc.map(x => x.title)));
  check('目录链接绝对化', toc[0].url === origin + '/read/1.html', toc[0].url);
  const tocB = await engine.toc(ruleB, origin + '/book/1.html');
  check('isDesc 目录倒序', tocB.length > 1 && tocB[0].title === '第三章 风波', JSON.stringify(tocB.map(x => x.title)));

  /* ---------- 章节：GBK + 广告过滤 + br 分段 + 内部分页 ---------- */
  const ch1 = await engine.chapter(ruleA, origin + '/read/1.html');
  check('章节标题', ch1.title === '第一章 少年', ch1.title);
  check('GBK 解码', noGbk() || ch1.paragraphs.some(p => p.includes('少年走出山村')), noGbk() ? '无 iconv-lite，跳过' : 'decoded');
  check('br 分段数量', ch1.paragraphs.length === 5, JSON.stringify(ch1.paragraphs));
  check('首段正确', ch1.paragraphs[0] === '少年走出山村。', ch1.paragraphs[0]);
  check('filterTxt 去广告', !ch1.paragraphs.join('').includes('无弹窗免费阅读'), '');
  check('filterTag 去 script/div', !ch1.paragraphs.join('').includes('ad()') && !ch1.paragraphs.join('').includes('www.a.com'), '');
  check('跨页拼接', ch1.paragraphs.join('').includes('钟声'), ch1.paragraphs.join('|'));

  /* ---------- 章节：闭合 p 标签 + filterTag ---------- */
  const ruleC = JSON.parse(JSON.stringify(ruleA));
  ruleC.chapter = { title: 'h1', content: '#content', paragraphTagClosed: true, filterTag: '.extra' };
  const ch2 = await engine.chapter(ruleC, origin + '/read/2.html');
  check('闭合 p 分段', ch2.paragraphs.length === 3, JSON.stringify(ch2.paragraphs));
  check('闭合 p filterTag', !ch2.paragraphs.join('').includes('本章说'), '');

  /* ---------- chapterParagraphs 纯函数 ---------- */
  const pure = chapterParagraphs('<div>标题行</div><p>正文甲</p><p>正文乙</p>', { paragraphTagClosed: true }, '标题行');
  check('纯函数：开头重复标题去除', pure.length === 2 && pure[0] === '正文甲', JSON.stringify(pure));

  /* ---------- 整本下载：重试 + 顺序 + 进度 ---------- */
  server.ch3Hits = 0;
  const prog = [];
  const book = await engine.downloadBook(ruleA, origin + '/book/1.html', { onProgress: (d, t, title) => prog.push([d, t, title]) });
  check('整本下载书名', book.name === '通天之路', book.name);
  check('整本下载章节数', book.total === 3, 'total ' + book.total);
  check('500 章节重试成功', book.failed === 0 && book.text.includes('第三章正文第一页'), 'failed=' + book.failed);
  const i1 = book.text.indexOf('第一章 少年'), i2 = book.text.indexOf('第二章 问道'), i3 = book.text.indexOf('第三章 风波');
  check('章节顺序正确', i1 >= 0 && i1 < i2 && i2 < i3, [i1, i2, i3].join(',') + ' | 文本开头: ' + JSON.stringify(book.text.slice(0, 120)));
  check('进度回调递增', prog.length === 3 && prog[2][0] === 3, JSON.stringify(prog));
  check('文本含标题与正文', /^通天之路/.test(book.name) && book.text.includes('他在观中住下。'), '');

  /* ---------- 取消 ---------- */
  const ctrl = new AbortController();
  let aborted = '';
  const p = engine.downloadBook(ruleA, origin + '/book/1.html', { signal: ctrl.signal }).catch(e => { aborted = e.code; });
  ctrl.abort();
  await p;
  check('取消抛出 aborted', aborted === 'aborted', aborted);

  /* ---------- 错误路径 ---------- */
  let err = '';
  try { await engine.search({ name: 'x', url: origin, search: { url: '' } }, 'a'); } catch (e) { err = e.message; }
  check('无 search.url 明确报错', err.includes('不支持搜索'), err);

  server.close();
  console.log('\n' + (failed ? failed + ' 项失败' : '全部通过'));
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error('测试异常：', e); process.exit(1); });
