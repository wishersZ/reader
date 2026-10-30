'use strict';
/* 联网搜书引擎：freeok/so-novel 书源规则（main-rules.json / rule-template.json5 格式）的 Node 实现。
   语义依据：HtmlExtractor（@href/@src/@js: 语法）、SearchParser、TocParser、ChapterParser、
   ChapterFilter、ChapterFormatter、CrawlUtils（POST data 的 %s 占位、限流参数）。
   安全边界：规则里的 @js:/@java:/@dsl: 脚本一律不执行，仅剥离后按纯 CSS 选择器降级；
   XPath 选择器暂不支持（官方规则集均为 CSS）。网络访问由注入的 fetcher 完成，本模块不依赖 electron。 */
const cheerio = require('cheerio');

const INVISIBLE_RE = /[\p{C}\p{Cf}\p{Co}\p{Zl}\p{Zp}\u200B\uFEFF]/gu;
const ENTITY_RE = /&[^;]+;/g;

class SourceError extends Error {
  constructor(message, code) { super(message); this.code = code || 'source'; }
}

/* ---------- 规则解析与规范化 ---------- */
function parseRuleListText(text) {
  let value;
  try {
    const JSON5 = require('json5');
    value = JSON5.parse(String(text || '').replace(/^\uFEFF/, ''));
  } catch (err) { throw new SourceError('规则文件解析失败：' + err.message, 'parse'); }
  const list = Array.isArray(value) ? value : (value.sources || value.rules || value.data || [value]);
  return list.filter(x => x && typeof x === 'object').map(normalizeRule).filter(r => r.search.url || r.toc.item || r.chapter.content);
}

/* 兼容 so-novel 格式与早期自定义扁平字段 */
function normalizeRule(raw) {
  const r = JSON.parse(JSON.stringify(raw || {}));
  const s = r.search || {};
  if (!r.search && (r.searchUrl || r.searchBook)) {
    r.search = {
      url: r.searchUrl || '', method: r.searchMethod || 'GET', data: r.searchData || '',
      result: r.searchBook || r.searchResult || '', bookName: r.searchBookName || r.bookName || '',
      author: r.searchAuthor || r.author || '', latestChapter: r.searchLatestChapter || r.latestChapter || '',
      lastUpdateTime: r.searchLastUpdateTime || '', category: r.searchCategory || '', wordCount: r.searchWordCount || '',
      status: r.searchStatus || '', nextPage: r.searchNextPage || '', cookies: r.searchCookies || ''
    };
  }
  if (r.search && !r.search.method && s.url) r.search.method = 'GET';
  if (r.toc && typeof r.toc === 'object' && !r.toc.item && r.toc.list) r.toc.item = r.toc.item || 'a';
  r.name = r.name || r.bookSourceName || r.bookSourceUrl || r.url || '未命名书源';
  r.disabled = !!(r.disabled || r.search?.disabled);
  r.crawl = r.crawl || {};
  return r;
}

/* ---------- 选择器语法（HtmlExtractor 语义） ---------- */
function stripQuery(query) {
  const q = String(query || '');
  const i = q.indexOf('@');
  return i > 0 ? q.slice(0, i) : q;
}
function queryInfo(query) {
  const q = String(query || '').trim();
  let attr = null;
  if (q.includes('@href')) attr = 'href';
  else if (q.includes('@src')) attr = 'src';
  else if (/^meta\[/i.test(stripQuery(q).trim())) attr = 'content';
  return {
    selector: stripQuery(q).trim(),
    attr,
    hasDsl: /@(js|java|dsl):/.test(q),
    isXPath: /^(\/|\/\/|\().*/.test(stripQuery(q).trim())
  };
}
function isCtx($, node) { return !!(node && node.cheerio); }
function select($, ctx, selector) {
  if (!selector) return $('');
  if (/^(\/|\/\/|\().*/.test(selector)) throw new SourceError('暂不支持 XPath 选择器：' + selector, 'xpath');
  return isCtx($, ctx) ? ctx.find(selector) : $(selector);
}
const cleanText = t => String(t == null ? '' : t).replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
/* 片段序列化：保留文本节点（children() 只含元素，会丢掉裸文本） */
function serializeFragment($f) {
  return $f.root().contents().toArray().map(node =>
    node.type === 'text' ? node.data : ($f.html(node) || '')
  ).join('');
}

function extract($, ctx, query, baseUrl) {
  if (!query) return '';
  const { selector, attr } = queryInfo(query);
  if (!selector) return '';
  const els = select($, ctx, selector);
  if (!els.length) return '';
  if (!attr) return els.toArray().map(el => cleanText($(el).text())).filter(Boolean).join(' ');
  const v = cleanText(els.first().attr(attr));
  if (!v) return '';
  if (attr === 'href' || attr === 'src') { try { return new URL(v, baseUrl).href; } catch { return v; } }
  return v;
}
function extractHtml($, ctx, query) {
  if (!query) return '';
  const { selector } = queryInfo(query);
  if (!selector) return '';
  const els = select($, ctx, selector);
  if (!els.length) return '';
  return els.toArray().map(el => $(el).html() || '').join('');   // jsoup Elements.html()：各元素 innerHTML 拼接
}
function extractHref($, ctx, query, baseUrl) {
  if (!query) return '';
  const { selector } = queryInfo(query);
  if (!selector) return '';
  const els = select($, ctx, selector);
  if (!els.length) return '';
  const v = cleanText(els.first().attr('href') || els.first().attr('src'));
  if (!v) return '';
  try { return new URL(v, baseUrl).href; } catch { return v; }
}
function extractHrefs($, query, baseUrl) {
  if (!query) return [];
  const { selector } = queryInfo(query);
  if (!selector) return [];
  let els;
  try { els = select($, null, selector); } catch { return []; }
  const out = [];
  for (const el of els.toArray()) {
    const v = cleanText($(el).attr('href') || $(el).attr('value') || $(el).attr('src'));
    if (!v) continue;
    try { out.push(new URL(v, baseUrl).href); } catch { out.push(v); }
  }
  return out;
}

/* POST data（CrawlUtils.buildData 语义）：JSON5 对象串，值为裸 %s 的位置替换为关键字 */
function buildData(dataTemplate, keyword) {
  const raw = String(dataTemplate || '').trim();
  if (!raw) return new URLSearchParams({ searchkey: keyword }).toString();
  const quoted = raw.replace(/"%s"/g, '%s').replace(/%s/g, () => JSON.stringify(keyword));
  let obj;
  try { obj = require('json5').parse(quoted); }
  catch { return raw.replace(/%s/g, encodeURIComponent(keyword)); }
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(obj)) sp.append(k, String(v));
  return sp.toString();
}

const fmt = (t, id) => String(t || '').replace(/%s/g, id == null ? '' : String(id));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const rand = (a, b) => a + Math.round(Math.random() * Math.max(0, b - a));
function throwIfAborted(signal) { if (signal?.aborted) throw new SourceError('已取消', 'aborted'); }

/* ---------- 引擎 ---------- */
class Engine {
  constructor(fetcher) { this.fetch = fetcher; }   // fetcher({url, method, data, headers, signal}) → {ok,status,text,url}

  /* 统一请求入口：网络错误 / 主动取消都归一成 SourceError */
  async #fetch(opts) {
    try { return await this.fetch(opts); }
    catch (err) {
      if (opts.signal?.aborted || err?.name === 'AbortError') throw new SourceError('已取消', 'aborted');
      throw err;
    }
  }
  async #get(url, signal) {
    const res = await this.#fetch({ url, signal });
    if (!res.ok) throw new SourceError('HTTP ' + (res.status || '请求失败'), 'http');
    return res;
  }

  /* 搜索。返回 [{name, author, url, latest, lastUpdateTime, category, wordCount, status, intro?}] */
  async search(rule, keyword, { signal, maxPages = 5 } = {}) {
    const r = normalizeRule(rule);
    const s = r.search;
    if (rule.disabled || s.disabled) throw new SourceError('书源已禁用', 'disabled');
    if (!s.url) throw new SourceError('书源没有 search.url，不支持搜索', 'nosearch');
    if (/@(js|java|dsl):/.test(s.url)) throw new SourceError('搜索链接含 @js: 脚本，暂不支持', 'dsl');
    const method = String(s.method || 'GET').toUpperCase();
    const headers = {};
    if (s.cookies) headers.Cookie = s.cookies;
    let url = s.url, data = '';
    if (method === 'POST') data = buildData(s.data, keyword);
    else url = fmt(s.url, encodeURIComponent(keyword));
    const res = await this.#fetch({ url, method, data, headers, signal });
    if (!res.ok) throw new SourceError('搜索请求失败 HTTP ' + (res.status || ''), 'http');
    const page = this.#parseSearchPage(r, res.text, res.url);
    if (!page.length && r.book && r.book.bookName) {
      const info = this.#parseBookInfo(r, res.text, res.url);
      if (info.name) return [{ name: info.name, author: info.author, url: res.url, latest: info.latestChapter, lastUpdateTime: info.lastUpdateTime, status: info.status, category: info.category, wordCount: info.wordCount, intro: info.intro, direct: true }];
    }
    let all = page;
    if (s.nextPage && page.length) {
      const $ = cheerio.load(res.text);
      let links = [];
      try { links = extractHrefs($, s.nextPage, res.url); } catch { links = []; }
      links = [...new Set(links)].slice(0, maxPages - 1);
      for (const u of links) {
        throwIfAborted(signal);
        try {
          const p = await this.#get(u, signal);
          all = all.concat(this.#parseSearchPage(r, p.text, p.url));
        } catch { /* 分页失败忽略 */ }
      }
    }
    return all.slice(0, 100);
  }

  #parseSearchPage(rule, html, pageUrl) {
    const $ = cheerio.load(html);
    const s = rule.search;
    let items = [];
    try { items = select($, null, stripQuery(s.result)).toArray(); } catch { return []; }
    if (!items.length) return [];
    const out = [];
    for (const el of items.slice(0, 100)) {
      const $el = $(el);
      const name = extract($, $el, s.bookName, pageUrl);
      if (!name) continue;
      out.push({
        name,
        url: extractHref($, $el, s.bookName, pageUrl) || extractHref($, $el, 'a', pageUrl),
        author: extract($, $el, s.author, pageUrl),
        latest: extract($, $el, s.latestChapter, pageUrl),
        lastUpdateTime: extract($, $el, s.lastUpdateTime, pageUrl),
        category: extract($, $el, s.category, pageUrl),
        wordCount: extract($, $el, s.wordCount, pageUrl),
        status: extract($, $el, s.status, pageUrl)
      });
    }
    return out.filter(x => x.url);
  }

  /* 详情页信息 */
  async bookInfo(rule, bookUrl, { signal } = {}) {
    const res = await this.#get(bookUrl, signal);
    return this.#parseBookInfo(normalizeRule(rule), res.text, res.url || bookUrl);
  }
  #parseBookInfo(rule, html, pageUrl) {
    const $ = cheerio.load(html);
    const b = rule.book || {};
    const grab = (q) => { try { return extract($, null, q, pageUrl); } catch { return ''; } };
    return {
      name: grab(b.bookName), author: grab(b.author).replace(/^作者[:：]\s*/, ''),
      intro: cleanText(grab(b.intro)), category: grab(b.category),
      latestChapter: grab(b.latestChapter), lastUpdateTime: grab(b.lastUpdateTime).replace(/^(更新时间|最后更新)[:：]\s*/, ''),
      status: grab(b.status),
      coverUrl: (() => { try { return extract($, null, b.coverUrl, pageUrl); } catch { return ''; } })()
    };
  }

  /* 目录：返回 [{title, url}]，按阅读顺序 */
  async toc(rule, bookUrl, { signal, maxPages = 20, maxItems = 5000 } = {}) {
    const r = normalizeRule(rule);
    const toc = r.toc || {};
    let id = '';
    if (r.book && r.book.url) {
      try {
        const m = new RegExp(stripQuery(r.book.url)).exec(bookUrl);
        if (m) id = m[1] || '';
      } catch { /* book.url 不是正则就按普通串处理 */ }
    }
    const tocUrl = toc.url ? new URL(fmt(toc.url, id), bookUrl).href : bookUrl;
    const baseUri = toc.baseUri ? fmt(toc.baseUri, id) : tocUrl;
    const pages = [tocUrl];
    let firstHtml = '';
    if (toc.nextPage) {
      try {
        const res = await this.#get(tocUrl, signal);
        firstHtml = res.text;
        const $ = cheerio.load(res.text);
        const els = select($, null, stripQuery(toc.nextPage));
        const opts = els.toArray().filter(el => String(el.tagName || '').toLowerCase() === 'option' && $(el).attr('value'));
        if (opts.length) {
          // 下拉菜单：一次性取全部分页 URL
          for (const el of opts) {
            let u = '';
            try { u = new URL($(el).attr('value'), baseUri).href; } catch { u = ''; }
            if (!u) u = extractHref($, $(el), toc.nextPage, tocUrl);
            if (u && !pages.includes(u)) pages.push(u);
          }
        } else {
          // “下一页”按钮递归
          let cur = tocUrl, guard = 0;
          while (guard++ < maxPages) {
            const d = guard === 1 ? $ : cheerio.load((await this.#get(cur, signal)).text);
            const nx = extractHref(d, null, toc.nextPage, cur);
            if (!nx || nx === cur || pages.includes(nx)) break;
            pages.push(nx); cur = nx;
          }
        }
      } catch { /* 分页失败就用第一页 */ }
    }
    const chapters = [];
    for (const p of pages.slice(0, maxPages)) {
      throwIfAborted(signal);
      let html = (p === tocUrl && firstHtml) ? firstHtml : (await this.#get(p, signal)).text;
      const $ = cheerio.load(html);
      let doc = $;
      if (toc.list) {
        const inner = extractHtml($, null, toc.list);
        if (inner) doc = cheerio.load(inner);
      }
      let els = [];
      try { els = doc(stripQuery(toc.item || 'a')).toArray(); } catch { els = []; }
      let list = els.map(el => {
        const v = cleanText(doc(el).attr('href') || doc(el).attr('src'));
        let u = '';
        if (v) { try { u = new URL(v, p).href; } catch { u = v; } }
        return { title: cleanText(doc(el).text()), url: u };
      }).filter(x => x.title && x.url);
      if (toc.isDesc) list = list.reverse();
      for (const c of list) { if (chapters.length >= maxItems) break; chapters.push(c); }
    }
    return chapters;
  }

  /* 单章：返回 {title, paragraphs[]}（过滤 + 排版后的纯文本段落） */
  async chapter(rule, chapterUrl, { signal } = {}) {
    const r = normalizeRule(rule);
    const c = r.chapter || {};
    if (/@(js|java|dsl):/.test(String(c.content || ''))) { /* 正文选择器带脚本：降级为纯选择器 */ }
    const parts = [];
    let title = '';
    let cur = chapterUrl, guard = 0;
    const paginate = !!c.nextPage && !c.nextPageInJs;
    while (true) {
      throwIfAborted(signal);
      const res = await this.#get(cur, signal);
      const $ = cheerio.load(res.text);
      if (!title && c.title) { try { title = extract($, null, c.title, res.url); } catch {} }
      const html = extractHtml($, null, c.content);
      if (!cleanText(html.replace(/<[^>]+>/g, ' '))) throw new SourceError('正文内容为空', 'empty');
      parts.push(html);
      if (!paginate || guard++ >= 19) break;
      let nextUrl = '';
      let nextTxt = '';
      try {
        const els = select($, null, stripQuery(c.nextPage));
        nextTxt = cleanText(els.text());
        nextUrl = extractHref($, null, c.nextPage, res.url);
      } catch { break; }
      if (!nextUrl || nextUrl === cur) break;
      if (c.nextChapterLink) { try { if (new RegExp(c.nextChapterLink).test(nextUrl)) break; } catch {} }
      if (!/[-_]\d\.html?$/i.test(nextUrl) && /(下一章|没有了|>>|书末页)/.test(nextTxt)) break;
      cur = nextUrl;
    }
    if (!title) title = '正文';
    const paragraphs = chapterParagraphs(parts.join('\n'), c, title);
    if (!paragraphs.length) throw new SourceError('正文内容为空', 'empty');
    return { title, paragraphs };
  }

  /* 整本下载：返回 {name, author, text, total, failed}，text 与本地 txt 格式一致 */
  async downloadBook(rule, bookUrl, { signal, onProgress, concurrency, delayRange } = {}) {
    const r = normalizeRule(rule);
    const crawl = r.crawl || {};
    const conc = Math.max(1, Math.min(6, Number(concurrency || crawl.concurrency || 2)));
    const dMin = Number(delayRange?.[0] ?? crawl.minInterval ?? 300);
    const dMax = Number(delayRange?.[1] ?? crawl.maxInterval ?? 700);
    const attempts = Math.max(1, Number(crawl.maxAttempts || 3));
    const info = await this.bookInfo(rule, bookUrl, { signal }).catch(() => ({ name: '', author: '' }));
    const toc = await this.toc(rule, bookUrl, { signal });
    if (!toc.length) throw new SourceError('目录为空或解析失败', 'notoc');
    const results = new Array(toc.length).fill(null);
    const queue = toc.map((ch, i) => ({ ch, i }));
    let done = 0, failed = 0;
    const worker = async () => {
      for (;;) {
        throwIfAborted(signal);
        const job = queue.shift();
        if (!job) return;
        let lastErr = null;
        for (let a = 1; a <= attempts; a++) {
          try {
            results[job.i] = await this.chapter(rule, job.ch.url, { signal });
            lastErr = null; break;
          } catch (err) {
            lastErr = err;
            if (err.code === 'aborted') throw err;
            await sleep(rand(dMin, dMax) * a);
          }
        }
        if (lastErr) { failed++; results[job.i] = { title: job.ch.title, paragraphs: ['【本章下载失败：' + lastErr.message + '】'] }; }
        done++;
        if (onProgress) onProgress(done, toc.length, job.ch.title, failed);
        await sleep(rand(dMin, dMax));
      }
    };
    await Promise.all(Array.from({ length: conc }, worker));
    const lines = [];
    for (let i = 0; i < toc.length; i++) {
      const r2 = results[i] || { title: toc[i].title, paragraphs: ['【本章下载失败】'] };
      lines.push(toc[i].title || r2.title, ...r2.paragraphs, '');   // 章节名以目录为准（与 so-novel 一致）
    }
    const fallbackName = decodeURIComponent((bookUrl.match(/\/([^/?#]+?)(?:\.html?)?\/?$/) || [])[1] || '在线书籍');
    return { name: info.name || fallbackName, author: info.author || '', intro: info.intro || '', text: lines.join('\n'), total: toc.length, failed };
  }
}

/* 章节 HTML → 段落（ChapterFilter + ChapterFormatter + 渲染的忠实移植） */
function chapterParagraphs(contentHtml, c, title) {
  let html = String(contentHtml || '');
  html = html.replace(INVISIBLE_RE, '').replace(ENTITY_RE, '');
  if (c.filterTxt) {
    try { html = html.replace(new RegExp(c.filterTxt, 'g'), ''); } catch { /* 非法正则忽略 */ }
  }
  if (c.filterTag) {
    try {
      const sel = String(c.filterTag).split(',').map(s => s.trim()).filter(Boolean).join(',');
      if (sel) {
        const $f = cheerio.load(html, null, false);
        $f(sel).remove();
        html = serializeFragment($f);
      }
    } catch { /* 非法选择器忽略 */ }
  }
  // 去全部标签属性
  {
    const $x = cheerio.load(html, null, false);
    $x('*').each((_, el) => { for (const k of Object.keys(el.attribs || {})) $x(el).removeAttr(k); });
    html = serializeFragment($x);
  }
  // 删除正文开头的重复标题（纯文本比对）
  try {
    const t1 = cleanText(title), t2 = cleanText(String(title || '').replace(/\s+/g, ''));
    const re = new RegExp('^(\\s|<[^>]+>)*(' + (t1 ? t1.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') : '$^') + '|' + (t2 ? t2.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') : '$^') + ')', '');
    html = html.replace(re, '$1');
  } catch { }
  // 空标签清理
  html = html.replace(/<([a-zA-Z][a-zA-Z0-9]*)>(?:\s|&nbsp;|<\/\1>)*<\/\1>/g, '').replace(/<([a-zA-Z][a-zA-Z0-9]*)\s*\/>/g, '');
  let raw;
  if (c.paragraphTagClosed) {
    // 非 <p> 闭合标签替换为 <p>
    raw = html.replace(/<(?!p\b)([a-zA-Z][a-zA-Z0-9]*)>([\s\S]*?)<\/\1>/g, '<p>$2</p>');
  } else {
    const sep = c.paragraphTag || '<br>+';
    raw = '';
    try {
      for (const line of html.split(new RegExp(sep))) {
        if (cleanText(line.replace(/<[^>]+>/g, ' '))) raw += '<p>' + line + '</p>';
      }
    } catch { raw = html; }
  }
  const paras = [];
  const re = /<p>([\s\S]*?)<\/p>/g;
  let m;
  while ((m = re.exec(raw))) {
    const $p = cheerio.load(m[1], null, false);
    const t = cleanText($p.text());
    if (t) paras.push(t);
  }
  // 首段若仍是标题本身，去掉
  while (paras.length && (cleanText(paras[0]) === cleanText(title) || (title && cleanText(paras[0]) === cleanText(title.replace(/\s+/g, ''))))) paras.shift();
  return paras;
}

module.exports = { Engine, SourceError, parseRuleListText, normalizeRule, buildData, queryInfo, chapterParagraphs, stripQuery, extractHtml, select, extract };
