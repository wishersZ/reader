'use strict';
/*
 * 月读 · 拆分导出核心
 * ---------------------------------------------------------------------------
 * 整合自 novel_split.py（长篇小说「规范化 → 章节排序 → 分卷/分部分」工具），
 * 移植为 CommonJS 模块，由主进程 require（见 src/main.js 的 split:preview /
 * split:export 两个 IPC）。渲染层不直接加载本模块，避免大文本进 UI 线程。
 *
 * 与 Python 版的差异（有意为之）：
 *   - 不做编码探测/转换：书稿在导入时已被 main.js 的 decodeTxt() 解成 JS 字符串，
 *     导出统一写 UTF-8，可用 opts.bom 决定是否加 BOM。
 *   - 章节/卷解析逻辑、复合词黑名单、密集列表过滤、分段排序、零丢失校验全部保留。
 *
 * 主要导出：
 *   analyze(text, opts)     -> 结构分析（卷/章/异常），不产生文件
 *   splitBook(text, opts)   -> 切分，返回要写盘的 [{name, content}] + manifest
 *   cnToInt(str) / cnIndex(n) / sanitizeName(s)
 */

const VERSION = '1.0';

/* ============================ 常量 ============================ */

const CN_CHARS = '零〇○一二三四五六七八九十百千万两';
const NUM_PAT = `[0-9０-９${CN_CHARS}]+`;
const CHAPTER_UNITS = '章回节話话';
const VOLUME_UNITS = '卷部';
const AMBIGUOUS_UNITS = '篇集'; // 「篇/集」在不同书里含义不同，按上下文自适应

// 标题行两侧的装饰字符（=== 《》 【】 空白 等），仅用于识别，不改动输出
const DECOR_CLASS = '[=＝\\-—–―*＊·・#＃_﹏~～ \\t\\u3000\\u00a0]';
const WRAPPERS = [['【', '】'], ['［', '］'], ['[', ']'], ['《', '》'],
                  ['（', '）'], ['(', ')'], ['『', '』'], ['「', '」']];

const SPECIAL_HEAD_RE = /^(序章|序言|序|楔子|引子|前言|卷首语|开篇|登场人物|人物介绍)\s*[：:、.，,\-—]?\s*(.*)$/;
const SPECIAL_TAIL_RE = /^(终章|尾声|后记|完本感言|完结感言|作者的话|番外篇|番外|特别篇|外传|附录)\s*[：:、.，,\-—]?\s*(.*)$/;

// 「无分隔符」时的复合词黑名单：拦「第二回合补卡两张。」「第543章之前好不容易过了」这类正文，
// 但保住「第10章重新开场抽取」这种真标题。
const COMPOUND_BLOCK = {
  '回': '合来到去想过事声应答忆顾头家身',
  '节': '目奏约省能制假气日',
  '话': '题说语音',
  '章': '之节回程',
  '集': '合团中',
  '篇': '章幅目',
  '卷': '之起土子',
  '部': '', // 保留「第一部分」这类真正的分卷写法
};
const VOLUME_TITLE_BLOCK = /本卷完|卷后语|卷末|本卷结束|卷尾|感言|后记|公告|请假|上架/;
const SEP_START_RE = /^[：:、.，,\-—～~・\s\u3000]/;

const HEADING_MAX_LEN = 60;   // 标题整行长度上限，超过视为正文
const HEADING_PUNCT_LEN = 30; // 含句号且超过此长度视为正文
const TOC_MIN_RUN = 5;        // 连续密集标题达到此数量即判为目录/面板列表
const TOC_MAX_GAP = 2;        // 密集块内相邻标题的行距上限
const AI_CHUNK_CHARS = 100000; // 未指定份数时，每份目标净字数

// 短关键词后面直接跟序数，通常是正文列表项而非章节（如「序九：血脉」）
const SHORT_SPECIAL = ['序', '引子', '前言', '楔子', '开篇'];
const ORDINAL_HEAD = new RegExp(`^[0-9０-９${CN_CHARS}]`);

// 广告 / 水印：仅当“独立成行 + 足够短 + 不像正文”时才删
const AD_PATTERNS = [
  /https?:\/\//i, /www\./i, /\.com\b/i, /\.net\b/i, /\.org\b/i, /\.cc\b/i,
  /搜书吧/, /笔趣/, /顶点小说/, /奇书网/, /书包网/, /燃文/, /飞卢/,
  /全本小说/, /无弹窗/, /手机阅读/, /手机版阅读/, /免费阅读/, /全文阅读/,
  /更新最快/, /最快更新/, /最新网址/, /备用地址/, /请记住本站/, /记住本站/,
  /本站域名/, /下载自/, /本书下载/, /txt下载/i, /电子书下载/, /QQ群/i, /书友群/,
  /微信公众号/, /本章未完/, /点击下一页/, /加入书架/, /投推荐票/,
  /求收藏/, /求月票/, /求订阅/, /求推荐/, /跪求/, /打赏/,
  /^\s*[（(]?本章完[)）]?\s*$/, /^\s*[（(]?未完待续[)）]?\s*$/,
  /^\s*[（(]?全文完[)）]?\s*$/,
];
const SEPARATOR_RE = /^[\s\-—–―=＝*＊·・#＃_﹏~～.]{3,}$/;
const ILLEGAL_FS = /[\\/:*?"<>|\r\n\t]+/g;

const CHAPTER_RE = new RegExp(`^(?:正文\\s*)?第\\s*(?<num>${NUM_PAT})\\s*(?<unit>[${CHAPTER_UNITS}])\\s*(?<rest>.*)$`);
const VOLUME_RE = new RegExp(`^(?:正文\\s*)?第\\s*(?<num>${NUM_PAT})\\s*(?<unit>[${VOLUME_UNITS}])\\s*(?<rest>.*)$`);
const VOLUME_BARE_RE = new RegExp(`^(?<unit>[${VOLUME_UNITS}])\\s*(?<num>${NUM_PAT})\\s*(?<rest>.*)$`);
const AMBIGUOUS_RE = new RegExp(`^(?:正文\\s*)?第\\s*(?<num>${NUM_PAT})\\s*(?<unit>[${AMBIGUOUS_UNITS}])\\s*(?<rest>.*)$`);

/* ============================ 小工具 ============================ */

// 注意：CJK 字符作对象键必须加引号 —— 「○」(U+25CB) 属于 Symbol 类别，不是合法标识符
const CN_DIGITS = { '零': 0, '〇': 0, '○': 0, '一': 1, '壹': 1, '二': 2, '两': 2, '贰': 2,
  '三': 3, '叁': 3, '四': 4, '肆': 4, '五': 5, '伍': 5, '六': 6, '陆': 6, '七': 7, '柒': 7,
  '八': 8, '捌': 8, '九': 9, '玖': 9 };
const CN_UNITS = { '十': 10, '拾': 10, '百': 100, '佰': 100, '千': 1000, '仟': 1000,
  '万': 10000, '亿': 100000000 };

/** 中文/全角/阿拉伯数字 → int；失败返回 null。支持 一 / 十 / 十一 / 一百零三 / 两。 */
function cnToInt(input) {
  if (input == null) return null;
  const s = String(input).normalize('NFKC').trim();
  if (!s) return null;
  if (/^[0-9]+$/.test(s)) return parseInt(s, 10);
  let total = 0, section = 0, number = 0;
  for (const ch of s) {
    if (ch in CN_DIGITS) { number = CN_DIGITS[ch]; }
    else if (ch in CN_UNITS) {
      const u = CN_UNITS[ch];
      if (u >= 10000) { section = (section + number) * u; total += section; section = 0; number = 0; }
      else { section += (number || 1) * u; number = 0; }
    } else return null;
  }
  return total + section + number;
}

/** 1 → 一, 11 → 十一, 21 → 二十一；>99 直接用阿拉伯数字。 */
function cnIndex(n) {
  const d = '零一二三四五六七八九';
  if (n < 1) return String(n);
  if (n < 10) return d[n];
  if (n === 10) return '十';
  if (n < 20) return '十' + d[n % 10];
  if (n < 100) return d[Math.floor(n / 10)] + '十' + (n % 10 ? d[n % 10] : '');
  return String(n);
}

/** 清理成合法文件名。 */
function sanitizeName(name, limit = 80) {
  let s = String(name || '').normalize('NFC').replace(ILLEGAL_FS, '_').trim().replace(/^\.+|\.+$/g, '');
  s = s.replace(/\s+/g, ' ');
  if (s.length > limit) s = s.slice(0, limit).trim();
  return s || 'untitled';
}

/** 去掉标题行两侧的 === / 括号 / 空白等装饰。 */
function stripDecorations(line) {
  let s = String(line).trim(), prev = null;
  while (prev !== s) {
    prev = s;
    s = s.replace(new RegExp('^' + DECOR_CLASS + '+'), '').replace(new RegExp(DECOR_CLASS + '+$'), '');
    for (const [a, b] of WRAPPERS) {
      if (s.length > a.length + b.length && s.startsWith(a) && s.endsWith(b)) s = s.slice(a.length, -b.length).trim();
    }
  }
  return s;
}

/**
 * 净字数：不含任何空白字符。
 * 注意按 Unicode **码点**计数，而不是 JS 的 String.length（UTF-16 码元）：
 * 生僻字（CJK 扩展 B 及以后）和 emoji 在 JS 里占 2 个码元，按码点算才是「1 个字」，
 * 也和 Python 版 len() 的口径一致。实测某本书有 61 个这类字符，口径不同会差 61。
 */
function netChars(s) {
  const t = String(s).replace(/\s/g, '');
  let n = t.length;
  for (let i = 0; i < t.length; i++) {
    const c = t.charCodeAt(i);
    if (c >= 0xd800 && c <= 0xdbff && i + 1 < t.length) {
      const d = t.charCodeAt(i + 1);
      if (d >= 0xdc00 && d <= 0xdfff) { n--; i++; }
    }
  }
  return n;
}

function cleanTitle(rest) {
  return String(rest || '')
    .replace(/^[：:、.，,。\-—～~・\s]+/, '')
    .replace(/[：:、\s]+$/, '')
    .trim();
}

/** 标题行的启发式否决：过长、或含句末标点且偏长。 */
function looksLikeProse(line) {
  if (line.length > HEADING_MAX_LEN) return true;
  if (line.includes('。') && line.length > HEADING_PUNCT_LEN) return true;
  return false;
}

/** 单位字后没有分隔符时，用复合词黑名单否决。 */
function acceptHeading(unit, rest) {
  if (!rest || SEP_START_RE.test(rest)) return true;
  const block = COMPOUND_BLOCK[unit] || '';
  return block.indexOf(rest[0]) === -1;
}

/* ============================ 一、解析结构 ============================ */

/**
 * 扫描全文，识别卷 / 章 / 特殊章。
 * @returns {{volumes:Array, chapters:Array, notes:string[], preambleLines:number}}
 */
function scanMarkers(lines) {
  const notes = [];
  const found = [];      // {kind, unit, num, title, raw, line}
  const ambiguous = [];

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const s = stripDecorations(raw);
    if (!s || looksLikeProse(s)) continue;

    let m = VOLUME_RE.exec(s) || VOLUME_BARE_RE.exec(s);
    if (m && acceptHeading(m.groups.unit, m.groups.rest)) {
      const title = cleanTitle(m.groups.rest);
      if (!VOLUME_TITLE_BLOCK.test(title)) {
        found.push({ kind: 'volume', unit: m.groups.unit, num: cnToInt(m.groups.num), title, raw, line: i });
        continue;
      }
    }
    m = CHAPTER_RE.exec(s);
    if (m && acceptHeading(m.groups.unit, m.groups.rest)) {
      found.push({ kind: 'chapter', unit: m.groups.unit, num: cnToInt(m.groups.num), title: cleanTitle(m.groups.rest), raw, line: i });
      continue;
    }
    m = AMBIGUOUS_RE.exec(s);
    if (m && acceptHeading(m.groups.unit, m.groups.rest)) {
      ambiguous.push({ unit: m.groups.unit, num: cnToInt(m.groups.num), title: cleanTitle(m.groups.rest), raw, line: i });
      continue;
    }
    for (const [re, kind] of [[SPECIAL_HEAD_RE, 'special-head'], [SPECIAL_TAIL_RE, 'special-tail']]) {
      m = re.exec(s);
      if (m) {
        const title = cleanTitle(m[2]);
        // 「序」「引子」这类短词后面直接跟序数，通常是正文里的列表项
        if (kind === 'special-head' && SHORT_SPECIAL.includes(m[1]) && ORDINAL_HEAD.test(title)) break;
        found.push({ kind, unit: m[1], num: null, title, raw, line: i });
        break;
      }
    }
  }

  // 目录页 / 系统面板列表过滤：真实章节之间必有正文，连续多行标题几乎不可能是真章节
  let kept = dropDenseRuns(found, notes, '');
  const volLike = kept.filter((f) => f.kind === 'volume').length;
  const chapLike = kept.filter((f) => f.kind === 'chapter').length;

  if (ambiguous.length) {
    const asVolume = volLike < 2 && chapLike === 0;
    notes.push(`把 ${ambiguous.length} 个「${AMBIGUOUS_UNITS.split('').join('/')}」标记当作${asVolume ? '卷' : '章'}处理` +
               `（卷标记 ${volLike} 个、章标记 ${chapLike} 个）。`);
    for (const a of ambiguous) kept.push({ ...a, kind: asVolume ? 'volume' : 'chapter' });
    kept = dropDenseRuns(kept, notes, '篇/集');
  }

  kept.sort((a, b) => a.line - b.line);

  const volumes = kept.filter((m) => m.kind === 'volume');
  const chapters = kept.filter((m) => m.kind !== 'volume');

  // 章节归属到卷
  let cursor = 0, vi = -1;
  for (const m of kept) {
    while (cursor < volumes.length && volumes[cursor].line < m.line) { cursor++; vi = cursor - 1; }
    m.volumeIdx = vi;
  }
  volumes.forEach((v, k) => { v.volumeIdx = k; });

  // 正文净字数
  chapters.sort((a, b) => a.line - b.line);
  for (let k = 0; k < chapters.length; k++) {
    const next = k + 1 < chapters.length ? chapters[k + 1].line : lines.length;
    let n = 0;
    for (let j = chapters[k].line + 1; j < next; j++) n += netChars(lines[j]);
    chapters[k].chars = n;
  }

  // 剔除空壳重复标题（同卷同章号、标题为空或与兄弟相同、正文 < 50 字）
  const dropped = dropDuplicateShells(chapters);
  if (dropped) {
    notes.push(`剔除 ${dropped} 个空壳重复标题（同卷同章号、标题为空或与兄弟相同、正文 < 50 字），` +
               `其行文已并入前一章，未丢失内容。`);
    for (let k = 0; k < chapters.length; k++) {
      const next = k + 1 < chapters.length ? chapters[k + 1].line : lines.length;
      let n = 0;
      for (let j = chapters[k].line + 1; j < next; j++) n += netChars(lines[j]);
      chapters[k].chars = n;
    }
  }

  const preambleLines = chapters.length ? chapters[0].line : (volumes.length ? volumes[0].line : 0);
  return { volumes, chapters, notes, preambleLines };
}

/** 剔除“目录/面板列表”式的密集标题（连续 >= TOC_MIN_RUN 且行距 <= TOC_MAX_GAP）。 */
function dropDenseRuns(found, notes, label) {
  const idxs = found.map((f, k) => (f.kind !== 'volume' ? k : -1)).filter((k) => k >= 0);
  const doomed = new Set();
  let run = [];
  const flush = () => { if (run.length >= TOC_MIN_RUN) run.forEach((k) => doomed.add(k)); run = []; };
  for (const k of idxs) {
    if (run.length && found[k].line - found[run[run.length - 1]].line <= TOC_MAX_GAP) run.push(k);
    else { flush(); run = [k]; }
  }
  flush();
  if (!doomed.size) return found;
  const hits = [...doomed].map((k) => found[k].line).sort((a, b) => a - b);
  notes.push(`疑似目录/列表${label}：第 ${hits[0] + 1}–${hits[hits.length - 1] + 1} 行` +
             `共 ${doomed.size} 个密集标题已忽略。`);
  return found.filter((_, k) => !doomed.has(k));
}

/** 同卷同章号里，正文极短且无标题/同标题的，判为重复标题剔除。 */
function dropDuplicateShells(chapters) {
  const groups = new Map();
  for (const c of chapters) {
    if (c.kind !== 'chapter' || c.num == null) continue;
    const key = c.volumeIdx + '|' + c.num;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(c);
  }
  const doomed = new Set();
  for (const items of groups.values()) {
    if (items.length < 2) continue;
    let keep = items[0];
    for (const m of items) {
      if ((m.title ? 1 : 0) > (keep.title ? 1 : 0) || ((m.title ? 1 : 0) === (keep.title ? 1 : 0) && m.chars > keep.chars)) keep = m;
    }
    for (const m of items) {
      if (m === keep) continue;
      if (m.chars < 50 && (!m.title || m.title === keep.title)) doomed.add(m);
    }
  }
  if (!doomed.size) return 0;
  for (let i = chapters.length - 1; i >= 0; i--) if (doomed.has(chapters[i])) chapters.splice(i, 1);
  return doomed.size;
}

/* ============================ 二、排序 ============================ */

/**
 * 按卷分组，组内按章号排序；自动识别章号重置并分段。
 * mode: 'auto'（默认，分段排序）| 'force'（整卷按章号重排）| 'off'（保持原序）
 */
function sortChapters(chapters, mode) {
  const notes = [];
  const moves = [];
  const groups = new Map();
  for (const c of chapters) {
    const k = c.volumeIdx;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(c);
  }
  const ordered = [];
  for (const vi of [...groups.keys()].sort((a, b) => a - b)) {
    const items = groups.get(vi);
    const numbered = items.filter((c) => c.kind === 'chapter' && c.num != null);
    let inversions = 0;
    for (let k = 0; k + 1 < numbered.length; k++) if (numbered[k].num > numbered[k + 1].num) inversions++;
    if (mode === 'off' || !inversions) { ordered.push(...items); continue; }

    let seg = 0;
    if (mode !== 'force') {
      for (let k = 0; k < numbered.length; k++) {
        if (k > 0 && numbered[k].num <= numbered[k - 1].num) seg++;
        numbered[k].seg = seg;
      }
    }
    // 未编号的特殊章不做首尾归拢，而是锚定到它前面那一章之后，
    // 这样只有真正乱序的章节才会移动，避免“抬到开头”造成全书索引整体位移。
    const anchor = new Map();
    let last = [-1, 0];
    for (const c of items) {
      if (c.kind === 'chapter' && c.num != null) last = [mode === 'force' ? 0 : (c.seg || 0), c.num];
      anchor.set(c, last);
    }
    const before = new Map(items.map((c, k) => [c, k]));
    const result = items.slice().sort((a, b) => {
      const A = anchor.get(a), B = anchor.get(b);
      if (A[0] !== B[0]) return A[0] - B[0];
      if (A[1] !== B[1]) return A[1] - B[1];
      const sa = a.kind === 'chapter' ? 0 : 1, sb = b.kind === 'chapter' ? 0 : 1;
      if (sa !== sb) return sa - sb;
      return a.order - b.order;
    });
    let local = 0;
    result.forEach((c, k) => { if (before.get(c) !== k) { moves.push({ marker: c, from: before.get(c), to: k }); local++; } });
    ordered.push(...result);

    const label = vi >= 0 ? `卷${vi + 1}` : '卷前内容';
    if (local) {
      notes.push(`${label}：发现 ${inversions} 处章号逆序，已重排 ${numbered.length} 章，实际移动 ${local} 章，明细见 _排序调整.tsv。`);
    } else {
      notes.push(`${label}：发现 ${inversions} 处章号逆序（疑似章号重置或原书笔误），但分段排序后无需移动任何一章，已保持原始顺序。`);
    }
  }
  return { ordered, notes, moves };
}

/* ============================ 三、规范化 ============================ */

/**
 * 逐行清理并统一排版。返回 { lines, removed, headingIdx }
 *  - 清理广告/分隔线（keepAds 可关）
 *  - 压缩连续空行
 *  - 正文段首统一缩进 indent 个全角空格（标题行与书前简介不缩进）
 */
function normalizeLines(lines, markers, opts) {
  const removed = [];
  const out = [];
  const mapping = new Map(); // 原始行号 → 规范化后行号（被删的行没有条目）
  const headings = new Set([...markers.volumes, ...markers.chapters].map((m) => m.line));
  const indent = '\u3000'.repeat(opts.indent | 0);
  let blanks = 0;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    let text;

    if (!opts.keepAds) {
      const s = raw.trim();
      if (s && SEPARATOR_RE.test(s)) { text = ''; }
      else if (s && s.length <= 80 && !/^[“「『"]/.test(s) && AD_PATTERNS.some((re) => re.test(s))) {
        removed.push([i + 1, s]);
        continue;
      } else text = raw.replace(/[ \t\u00a0]+$/, '');
    } else {
      text = raw.replace(/[ \t\u00a0]+$/, '');
    }

    if (headings.has(i)) {
      blanks = 0;
      text = String(raw).trim();
    } else if (text.trim() === '') {
      blanks++;
      if (blanks > opts.maxBlank) continue;
      text = '';
    } else {
      blanks = 0;
      const body = text.trim().replace(/^[\s\u3000\u00a0]+/, '').replace(/[ \t\u00a0]+$/, '');
      // 正文之前的前置内容（书名/作者/简介）不缩进
      text = i < markers.preambleLines ? body : indent + body;
    }
    mapping.set(i, out.length);
    out.push(text);
  }
  return { lines: out, removed, mapping };
}

/* ============================ 四、切分策略 ============================ */

function splitByVolumes(ordered, volumes) {
  const groups = new Map();
  for (const c of ordered) {
    const k = Math.max(c.volumeIdx, 0);
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(c);
  }
  return volumes.slice().sort((a, b) => a.line - b.line).map((v, k) => {
    const marker = v.num != null ? `第${v.num}${v.unit}` : v.unit;
    const name = v.title ? `${marker} ${v.title}` : marker;
    return { name, markers: [v, ...(groups.get(k) || [])] };
  });
}

function splitByParts(ordered, n) {
  const items = ordered.slice();
  n = Math.max(1, Math.min(n, items.length));
  const total = items.reduce((s, c) => s + c.chars, 0) || 1;
  const target = total / n;
  const parts = [];
  let cur = [], acc = 0, remaining = n;
  for (let i = 0; i < items.length; i++) {
    cur.push(items[i]); acc += items[i].chars;
    if (remaining - 1 > 0 && acc >= target && items.length - i - 1 >= remaining - 1) {
      parts.push(cur); cur = []; acc = 0; remaining--;
    }
  }
  if (cur.length) parts.push(cur);
  return parts.map((markers, i) => ({ name: `第${cnIndex(i + 1)}部分`, markers }));
}

function splitByMaxChars(ordered, maxChars) {
  const parts = [];
  let cur = [], acc = 0;
  for (const c of ordered) {
    if (cur.length && acc + c.chars > maxChars) { parts.push(cur); cur = []; acc = 0; }
    cur.push(c); acc += c.chars;
  }
  if (cur.length) parts.push(cur);
  return parts.map((markers, i) => ({ name: `第${cnIndex(i + 1)}部分`, markers }));
}

/** 把各份映射成规范化文本中的 [start, end) 行区间；首份从 0 开始以纳入前置内容。 */
function buildSpans(normLines, mapping, parts) {
  const rows = [];
  for (const p of parts) {
    const idxs = p.markers.map((m) => mapping.get(m.line)).filter((v) => v != null);
    if (idxs.length) rows.push({ ...p, start: Math.min(...idxs) });
  }
  if (!rows.length) return [];
  rows.sort((a, b) => a.start - b.start);
  rows[0].start = 0;
  return rows.map((r, k) => ({
    ...r,
    end: k + 1 < rows.length ? Math.max(r.start, rows[k + 1].start) : normLines.length,
  }));
}

/* ============================ 五、对外接口 ============================ */

/** 只做结构分析，不产生文件。 */
function analyze(text, opts = {}) {
  const lines = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const m = scanMarkers(lines);
  const sortMode = opts.sort || 'auto';
  const sorted = sortChapters(m.chapters, sortMode);

  const nums = sorted.ordered.filter((c) => c.kind === 'chapter' && c.num != null).map((c) => c.num);
  const seen = new Set(), dup = [];
  for (const n of nums) { if (seen.has(n) && !dup.includes(n)) dup.push(n); seen.add(n); }
  const missing = [];
  if (nums.length) {
    for (let n = Math.min(...nums); n <= Math.max(...nums); n++) if (!seen.has(n)) missing.push(n);
  }
  const thin = sorted.ordered.filter((c) => c.kind === 'chapter' && c.chars < 100);

  return {
    volumes: m.volumes,
    chapters: sorted.ordered,
    notes: [...m.notes, ...sorted.notes],
    moves: sorted.moves,
    stats: {
      totalChars: lines.reduce((s, l) => s + netChars(l), 0),
      lineCount: lines.length,
      volumeCount: m.volumes.length,
      chapterCount: sorted.ordered.filter((c) => c.kind === 'chapter').length,
      specialCount: sorted.ordered.filter((c) => c.kind.startsWith('special')).length,
      numRange: nums.length ? [Math.min(...nums), Math.max(...nums)] : null,
      duplicates: dup,
      missing,
      thin: thin.slice(0, 8).map((c) => ({ line: c.line + 1, raw: c.raw.trim(), chars: c.chars })),
    },
  };
}

/** 规范化后的整本文本（用于「整本另存 UTF-8」和切分共用）。 */
function normalizeText(text, opts = {}) {
  const o = {
    indent: opts.indent == null ? 2 : opts.indent,
    maxBlank: opts.maxBlank == null ? 1 : opts.maxBlank,
    keepAds: !!opts.keepAds,
    sort: opts.sort || 'auto',
  };
  const lines = String(text).replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n');
  const m = scanMarkers(lines);
  const sorted = sortChapters(m.chapters, o.sort);
  const norm = normalizeLines(lines, m, o);
  return { normLines: norm.lines, removed: norm.removed, mapping: norm.mapping, markers: m, sorted };
}

/**
 * 切分。返回 { files:[{name, content}], manifest, verification, notes }
 * mode: 'auto' | 'volume' | 'parts' | 'chars' | 'single'
 */
function splitBook(text, opts = {}) {
  const o = {
    mode: opts.mode || 'auto',
    parts: opts.parts | 0,
    maxChars: opts.maxChars | 0,
    minVolumes: opts.minVolumes == null ? 2 : opts.minVolumes,
    indent: opts.indent == null ? 2 : opts.indent,
    maxBlank: opts.maxBlank == null ? 1 : opts.maxBlank,
    keepAds: !!opts.keepAds,
    sort: opts.sort || 'auto',
    eol: opts.eol === 'lf' ? '\n' : '\r\n',
    book: opts.book || '未命名',
    autoPartsTarget: opts.autoPartsTarget || AI_CHUNK_CHARS,
  };

  const norm = normalizeText(text, o);
  const { normLines, markers, sorted } = norm;
  const notes = [...markers.notes, ...sorted.notes];
  const book = sanitizeName(o.book, 60);
  const ordered = sorted.ordered;

  if (!ordered.length) {
    return { files: [], manifest: null, verification: null, notes: [...notes, '未识别到任何章节。'] };
  }

  // ---- 选择切分方式 ----
  let parts, modeLabel;
  const useVolume = o.mode === 'volume' || (o.mode === 'auto' && markers.volumes.length >= o.minVolumes);
  const totalChars = ordered.reduce((s, c) => s + c.chars, 0);
  const autoParts = !o.parts && !o.maxChars;
  const nParts = o.parts > 0 ? o.parts : Math.max(1, Math.ceil(totalChars / o.autoPartsTarget));

  if (o.mode === 'single') {
    parts = [{ name: '全本', markers: ordered, whole: true }];
    modeLabel = '整本';
  } else if (useVolume && markers.volumes.length) {
    parts = splitByVolumes(ordered, markers.volumes);
    modeLabel = '按卷';
  } else if (o.mode === 'chars' || (o.mode === 'auto' && o.maxChars)) {
    parts = splitByMaxChars(ordered, o.maxChars || o.autoPartsTarget);
    modeLabel = `按字数≤${(o.maxChars || o.autoPartsTarget).toLocaleString()}`;
  } else {
    parts = splitByParts(ordered, nParts);
    modeLabel = `按数量${nParts}份`;
    if (o.mode === 'auto' && autoParts) notes.push(`未指定份数，按每份约 ${Math.round(o.autoPartsTarget / 1000)}K 字自动切为 ${nParts} 份。`);
    if (o.mode === 'volume' && !markers.volumes.length) notes.push('未发现卷标记，回退为按数量均分。');
  }

  // ---- 组装文件内容 ----
  const files = [];
  let total = 0;
  const manifestFiles = [];

  if (o.mode === 'single') {
    const body = normLines.slice();
    const content = body.join(o.eol) + (body.length ? o.eol : '');
    files.push({ name: `${book}_全本_UTF8.txt`, content });
    manifestFiles.push({ file: `${book}_全本_UTF8.txt`, part: '全本', chapters: ordered.filter((c) => c.kind === 'chapter').length, chars: body.reduce((s, l) => s + netChars(l), 0), first_chapter: ordered[0].raw.trim(), last_chapter: ordered[ordered.length - 1].raw.trim() });
    total = manifestFiles[0].chars;
  } else {
    const spans = buildSpans(normLines, norm.mapping, parts);
    for (const sp of spans) {
      const body = normLines.slice(sp.start, sp.end);
      const content = body.join(o.eol) + (body.length ? o.eol : '');
      const chapters = sp.markers.filter((m) => m.kind !== 'volume');
      const chars = body.reduce((s, l) => s + netChars(l), 0);
      const fname = `${book}_${sanitizeName(sp.name, 60)}.txt`;
      files.push({ name: fname, content });
      total += chars;
      manifestFiles.push({
        file: fname, part: sp.name, chapters: chapters.length, chars,
        first_chapter: chapters.length ? chapters[0].raw.trim() : '',
        last_chapter: chapters.length ? chapters[chapters.length - 1].raw.trim() : '',
      });
    }
  }

  // ---- 元数据文件 ----
  const fullChars = normLines.reduce((s, l) => s + netChars(l), 0);
  const stats = {
    book: o.book, mode: modeLabel, volumes: markers.volumes.length,
    chapters: ordered.filter((c) => c.kind === 'chapter').length,
    specials: ordered.filter((c) => c.kind.startsWith('special')).length,
    lines: normLines.length, removedLines: norm.removed.length,
    totalChars: fullChars,
  };

  const idx = [
    `# 《${o.book}》拆分索引`, '',
    `- 切分方式：${modeLabel}，共 ${files.length} 份，**净字数零丢失**（${total.toLocaleString()} 字）`,
    `- 结构：卷 ${stats.volumes} 个 / 章 ${stats.chapters} 章 / 特殊章 ${stats.specials} 个`,
    `- 规范化：${markers.chapters.length ? '' : ''}共 ${stats.lines.toLocaleString()} 行，清理广告/分隔线 ${stats.removedLines} 行`,
    `- 正文段首缩进：${o.indent} 个全角空格，换行 ${o.eol === '\r\n' ? 'CRLF' : 'LF'}`,
    '', '## 文件清单', '',
    '| # | 文件 | 章数 | 净字数 | 起 | 止 |', '|---|---|---|---|---|---|',
    ...manifestFiles.map((f, k) => `| ${k + 1} | \`${f.file}\` | ${f.chapters} | ${f.chars.toLocaleString()} | ${f.first_chapter.slice(0, 34)} | ${f.last_chapter.slice(0, 34)} |`),
  ];
  if (notes.length) idx.push('', '## 处理提示', '', ...notes.map((n) => `- ${n}`));
  if (norm.removed.length) idx.push('', `> 被删掉的 ${norm.removed.length} 行疑似广告/水印已存档在 \`_已删除行.txt\`。`);
  files.push({ name: '00_目录索引.md', content: idx.join('\n') + '\n' });

  const tsv = ['序号\t类型\t卷\t章号\t标题\t原行号\t净字数'];
  ordered.forEach((m, k) => {
    const vol = m.volumeIdx >= 0 && markers.volumes[m.volumeIdx]
      ? (markers.volumes[m.volumeIdx].num != null ? `第${markers.volumes[m.volumeIdx].num}${markers.volumes[m.volumeIdx].unit}` : markers.volumes[m.volumeIdx].unit)
      : '';
    tsv.push([k + 1, m.kind, vol, m.num == null ? '' : m.num, (m.title || m.raw.trim()).replace(/\t/g, ' '), m.line + 1, m.chars].join('\t'));
  });
  files.push({ name: '01_章节清单.tsv', content: tsv.join('\n') + '\n' });

  if (norm.removed.length) {
    files.push({
      name: '_已删除行.txt',
      content: `# 被判定为广告/水印/分隔线而删除的行，共 ${norm.removed.length} 行\n# 若误删正文，请勾选「保留广告行」重新导出\n\n` +
               norm.removed.map(([ln, t]) => `${ln}\t${t}`).join('\n') + '\n',
    });
  }
  if (sorted.moves.length) {
    files.push({
      name: '_排序调整.tsv',
      content: '# 章节排序时发生位置变动的记录\n章号\t标题\t原行号\t原位置\t新位置\n' +
               sorted.moves.map((mv) => [mv.marker.num == null ? '' : mv.marker.num, (mv.marker.title || mv.marker.raw.trim()).replace(/\t/g, ' '), mv.marker.line + 1, mv.from + 1, mv.to + 1].join('\t')).join('\n') + '\n',
    });
  }

  const manifest = { ...stats, files: manifestFiles, notes, moves: sorted.moves.length };
  files.push({ name: 'manifest.json', content: JSON.stringify(manifest, null, 2) + '\n' });

  // 零丢失校验：各份净字数之和 == 规范化全文净字数
  const verification = {
    ok: total === fullChars && (o.mode === 'single' || total > 0),
    sumParts: total,
    fullText: fullChars,
    loss: total - fullChars,
  };

  return { files, manifest, verification, notes, stats };
}

module.exports = { VERSION, cnToInt, cnIndex, sanitizeName, analyze, splitBook, normalizeText, netChars };
