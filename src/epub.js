/* EPUB 解析：抽正文段落、原生目录（EPUB2 NCX / EPUB3 nav）、封面
   独立成模块是为了能在纯 Node 下单元测试（不依赖 electron）。 */
const path = require('path');
const posix = path.posix;
const JSZip = require('jszip');
const { XMLParser } = require('fast-xml-parser');
const cheerio = require('cheerio');

const textOf = value => typeof value === 'string' ? value : value?.['#text'] || '';
const asArray = value => value == null ? [] : Array.isArray(value) ? value : [value];

const flatten = t => String(t || '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();

/* 相对 href → { file(容器内绝对路径), frag } */
function resolveHref(opfDir, baseDir, href) {
  const s = String(href || '');
  const hash = s.indexOf('#');
  const filePart = hash >= 0 ? s.slice(0, hash) : s;
  const frag = hash >= 0 ? s.slice(hash + 1) : '';
  if (!filePart) return null;
  try {
    return { file: posix.normalize(posix.join(opfDir, baseDir || '', decodeURIComponent(filePart))), frag };
  } catch { return null; }
}

/* EPUB2：NCX navMap → [{title, href}]（保留嵌套顺序） */
function parseNcx(xml) {
  const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_', textNodeName: '#text', isArray: name => ['navPoint'].includes(name) });
  let doc;
  try { doc = parser.parse(xml); } catch { return []; }
  const out = [];
  const walk = pts => {
    for (const np of asArray(pts)) {
      const label = flatten(textOf(np?.navLabel?.text));
      const src = np?.content?.['@_src'] || '';
      if (label && src) out.push({ title: label, href: src });
      walk(np?.navPoint);
    }
  };
  walk(doc?.ncx?.navMap?.navPoint);
  return out;
}

/* EPUB3：nav.xhtml 里的 toc nav → [{title, href}] */
function parseNavDoc(html) {
  const $ = cheerio.load(html, { decodeEntities: true });
  let $nav = $('nav').filter((_, el) => /(^|\s)(toc|directory)(\s|$)/i.test($(el).attr('epub:type') || $(el).attr('type') || '')).first();
  if (!$nav.length) $nav = $('nav').first();
  if (!$nav.length) return [];
  const out = [];
  $nav.find('a[href]').each((_, a) => {
    const title = flatten($(a).text());
    const href = $(a).attr('href') || '';
    if (title && href && !/^\s*(#|javascript:)/i.test(href)) out.push({ title, href });
  });
  return out;
}

const COVER_MIME = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp' };

async function parseEpub(buf, filename) {
  const zip = await JSZip.loadAsync(buf);
  const containerFile = zip.file('META-INF/container.xml');
  if (!containerFile) throw new Error('EPUB 缺少 META-INF/container.xml');
  const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_', textNodeName: '#text', isArray: name => ['rootfile', 'item', 'itemref'].includes(name) });
  const container = parser.parse(await containerFile.async('string'));
  const roots = asArray(container?.container?.rootfiles?.rootfile);
  const opfPath = roots[0]?.['@_full-path'];
  if (!opfPath) throw new Error('EPUB 未找到 OPF 包文件');
  const opfFile = zip.file(opfPath);
  if (!opfFile) throw new Error('EPUB OPF 文件不存在：' + opfPath);
  const opf = parser.parse(await opfFile.async('string'));
  const pkg = opf.package || opf.Package;
  const metadata = pkg?.metadata || {};
  const title = textOf(metadata['dc:title'] || metadata.title) || String(filename).replace(/\.epub$/i, '');
  const author = textOf(metadata['dc:creator'] || metadata.creator);
  const manifest = {};
  for (const item of asArray(pkg?.manifest?.item)) {
    if (item?.['@_id'] && item?.['@_href']) manifest[item['@_id']] = item;
  }
  const opfDir = posix.dirname(opfPath);

  /* 封面：EPUB2 用 <meta name="cover"> 指向 manifest，EPUB3 用 properties="cover-image" */
  let cover = null;
  try {
    let coverItem = null;
    const metaCover = asArray(metadata.meta).find(m => m?.['@_name'] === 'cover');
    if (metaCover?.['@_content'] && manifest[metaCover['@_content']]) coverItem = manifest[metaCover['@_content']];
    if (!coverItem) coverItem = Object.values(manifest).find(it => /(^|\s)cover-image(\s|$)/.test(String(it?.['@_properties'] || '')));
    if (coverItem) {
      const cf = zip.file(posix.normalize(posix.join(opfDir, decodeURIComponent(coverItem['@_href'].split('#')[0]))));
      if (cf) {
        const cbuf = await cf.async('nodebuffer');
        const ext = String(coverItem['@_href']).split('.').pop().toLowerCase();
        if (cbuf.length <= 3 * 1024 * 1024 && COVER_MIME[ext]) {
          cover = 'data:' + COVER_MIME[ext] + ';base64,' + cbuf.toString('base64');
        }
      }
    }
  } catch { /* 封面是锦上添花，失败不影响正文 */ }

  /* 正文：按 spine 顺序抽取，同时记录每段的来源文件和元素 id，供目录条目精确定位 */
  const paragraphs = [];
  const origin = [];   // origin[i] = { file, id }
  const spine = asArray(pkg?.spine?.itemref);
  for (const ref of spine) {
    const item = manifest[ref?.['@_idref']];
    if (!item?.['@_href']) continue;
    const entry = posix.normalize(posix.join(opfDir, decodeURIComponent(item['@_href'].split('#')[0])));
    const file = zip.file(entry);
    if (!file) continue;
    const html = await file.async('string');
    const $ = cheerio.load(html, { decodeEntities: true });
    $('script,style,noscript,svg').remove();
    const nodes = $('body').find('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre');
    const before = paragraphs.length;
    nodes.each((_, el) => {
      const t = flatten($(el).text());
      if (t) { paragraphs.push(t); origin.push({ file: entry, id: el.attribs?.id || '' }); }
    });
    if (paragraphs.length === before) {
      const t = flatten($('body').text());
      if (t) {
        const parts = t.split(/\r?\n+/).map(x => x.trim()).filter(Boolean);
        paragraphs.push(...parts);
        for (const _ of parts) origin.push({ file: entry, id: '' });
      }
    }
  }
  if (!paragraphs.length) throw new Error('EPUB 中没有可读取的正文');

  /* 目录：优先 EPUB3 nav，其次 EPUB2 NCX（spine@toc 指向，或按 media-type 找） */
  const rawToc = [];
  try {
    const navItem = Object.values(manifest).find(it => /(^|\s)nav(\s|$)/.test(String(it?.['@_properties'] || '')));
    if (navItem) {
      const nf = zip.file(posix.normalize(posix.join(opfDir, decodeURIComponent(navItem['@_href'].split('#')[0]))));
      if (nf) {
        const baseDir = posix.dirname(navItem['@_href'].split('#')[0]);
        for (const e of parseNavDoc(await nf.async('string'))) {
          const r = resolveHref(opfDir, baseDir, e.href);
          if (r) rawToc.push({ title: e.title, ...r });
        }
      }
    }
  } catch { /* nav 解析失败不致命 */ }
  if (!rawToc.length) {
    try {
      let ncxItem = manifest[pkg?.spine?.['@_toc']] || null;
      if (!ncxItem) ncxItem = Object.values(manifest).find(it => String(it?.['@_media-type'] || '').includes('dtbncx'));
      if (ncxItem) {
        const xf = zip.file(posix.normalize(posix.join(opfDir, decodeURIComponent(ncxItem['@_href'].split('#')[0]))));
        if (xf) {
          const baseDir = posix.dirname(ncxItem['@_href'].split('#')[0]);
          for (const e of parseNcx(await xf.async('string'))) {
            const r = resolveHref(opfDir, baseDir, e.href);
            if (r) rawToc.push({ title: e.title, ...r });
          }
        }
      }
    } catch { /* NCX 解析失败不致命 */ }
  }

  /* 目录条目 → 段落序号：先精确匹配锚点 id，再退到文件内第一段 */
  const toc = [];
  for (const e of rawToc) {
    let idx = e.frag ? origin.findIndex(o => o.file === e.file && o.id === e.frag) : -1;
    if (idx < 0) idx = origin.findIndex(o => o.file === e.file);
    if (idx >= 0) toc.push({ title: e.title, index: idx });
  }
  toc.sort((a, b) => a.index - b.index);
  const seen = new Set();
  const tocOut = toc.filter(t => { const k = t.index + '|' + t.title; if (seen.has(k)) return false; seen.add(k); return true; });

  const out = { name: title, author, text: paragraphs.join('\n'), format: 'epub' };
  if (tocOut.length) out.toc = tocOut;
  if (cover) out.cover = cover;
  return out;
}

module.exports = { parseEpub };
