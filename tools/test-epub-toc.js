/* EPUB 原生目录（EPUB2 NCX / EPUB3 nav）与封面提取的单元测试
   用法：node tools/test-epub-toc.js   （纯 Node，不需要 electron） */
const JSZip = require('jszip');
const { parseEpub } = require('../src/epub');

const PNG_1PX = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==',
  'base64'
);

let failed = 0;
function check(name, ok, extra) {
  console.log((ok ? 'PASS  ' : 'FAIL  ') + name + (extra === undefined ? '' : '   [' + extra + ']'));
  if (!ok) failed++;
}

const CONTAINER = `<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>
</container>`;

const OPF2 = `<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>测试书</dc:title><dc:creator>某作者</dc:creator>
    <meta name="cover" content="cov"/>
  </metadata>
  <manifest>
    <item id="cov" href="cover.png" media-type="image/png"/>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>
    <item id="c2" href="c2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="c1"/><itemref idref="c2"/>
  </spine>
</package>`;

const NCX = `<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="n1" playOrder="1">
      <navLabel><text>序章</text></navLabel><content src="c1.xhtml#s1"/>
      <navPoint id="n1-1" playOrder="2">
        <navLabel><text>第一节</text></navLabel><content src="c1.xhtml#s2"/>
      </navPoint>
    </navPoint>
    <navPoint id="n2" playOrder="3">
      <navLabel><text>第二章</text></navLabel><content src="c2.xhtml"/>
    </navPoint>
  </navMap>
</ncx>`;

const C1 = `<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c1</title></head><body>
<h1 id="s1">序章</h1>
<p id="p1">正文　甲
换行合并</p>
<h2 id="s2">第一节</h2>
<p>正文乙</p>
</body></html>`;

const C2 = `<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c2</title></head><body>
<h1 id="t1">第二章</h1>
<p>正文丙</p>
</body></html>`;

async function buildEpub2() {
  const zip = new JSZip();
  zip.file('mimetype', 'application/epub+zip');
  zip.file('META-INF/container.xml', CONTAINER);
  zip.file('OEBPS/content.opf', OPF2);
  zip.file('OEBPS/toc.ncx', NCX);
  zip.file('OEBPS/c1.xhtml', C1);
  zip.file('OEBPS/c2.xhtml', C2);
  zip.file('OEBPS/cover.png', PNG_1PX);
  return zip.generateAsync({ type: 'nodebuffer' });
}

async function buildEpub3() {
  const OPF3 = `<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>EPUB3书</dc:title><dc:creator>作者三</dc:creator>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="cov" href="imgs/cover.png" media-type="image/png" properties="cover-image"/>
    <item id="c1" href="text/c1.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="c1"/></spine>
</package>`;
  const NAV = `<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"><head><title>toc</title></head><body>
<nav epub:type="toc"><ol>
  <li><a href="text/c1.xhtml#s1">卷一</a><ol><li><a href="text/c1.xhtml#s2">第一节</a></ol></li>
</ol></nav>
<nav epub:type="landmarks"><ol><li><a href="text/c1.xhtml">正文</a></ol></nav>
</body></html>`;
  const C1V3 = `<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>c1</title></head><body>
<h1 id="s1">卷一</h1><p>甲</p><h2 id="s2">第一节</h2><p>乙</p>
</body></html>`;
  const zip = new JSZip();
  zip.file('mimetype', 'application/epub+zip');
  zip.file('META-INF/container.xml', CONTAINER);
  zip.file('OEBPS/content.opf', OPF3);
  zip.file('OEBPS/nav.xhtml', NAV);
  zip.file('OEBPS/text/c1.xhtml', C1V3);
  zip.file('OEBPS/imgs/cover.png', PNG_1PX);
  return zip.generateAsync({ type: 'nodebuffer' });
}

async function buildNoToc() {
  const OPF = `<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>无目录书</dc:title></metadata>
  <manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/></manifest>
  <spine><itemref idref="c1"/></spine>
</package>`;
  const zip = new JSZip();
  zip.file('mimetype', 'application/epub+zip');
  zip.file('META-INF/container.xml', CONTAINER);
  zip.file('OEBPS/content.opf', OPF);
  zip.file('OEBPS/c1.xhtml', C1);
  return zip.generateAsync({ type: 'nodebuffer' });
}

(async () => {
  /* ---- EPUB2：NCX 目录 + meta cover ---- */
  const b2 = await parseEpub(await buildEpub2(), 'test.epub');
  check('EPUB2 书名/作者', b2.name === '测试书' && b2.author === '某作者', b2.name + ' / ' + b2.author);
  const paras2 = b2.text.split('\n');
  check('EPUB2 段落抽取（h1/h2/p 按文档序，内部换行合并）',
    JSON.stringify(paras2) === JSON.stringify(['序章', '正文 甲 换行合并', '第一节', '正文乙', '第二章', '正文丙']),
    JSON.stringify(paras2));
  const toc2 = (b2.toc || []).map(t => t.title + '@' + t.index).join('|');
  check('EPUB2 NCX 目录映射到正确段落', toc2 === '序章@0|第一节@2|第二章@4', toc2);
  check('EPUB2 封面提取为 data URL', typeof b2.cover === 'string' && b2.cover.startsWith('data:image/png;base64,'), String(b2.cover || '').slice(0, 30));

  /* ---- EPUB3：nav 目录 + properties=cover-image ---- */
  const b3 = await parseEpub(await buildEpub3(), 'v3.epub');
  const toc3 = (b3.toc || []).map(t => t.title + '@' + t.index).join('|');
  check('EPUB3 nav 目录映射到正确段落（landmarks 不混入）', toc3 === '卷一@0|第一节@2', toc3);
  check('EPUB3 封面提取', typeof b3.cover === 'string' && b3.cover.startsWith('data:image/png;base64,'));
  check('EPUB3 段落', b3.text.split('\n').length === 4, b3.text.split('\n').length + ' 段');

  /* ---- 无目录 EPUB：toc 缺省，正文照常 ---- */
  const bn = await parseEpub(await buildNoToc(), 'plain.epub');
  check('无目录 EPUB 不产出 toc 字段', bn.toc === undefined, JSON.stringify(bn.toc));
  check('无目录 EPUB 正文可读', bn.text.includes('序章') && bn.text.includes('正文乙'));

  console.log('\n' + (failed ? failed + ' 项失败' : '全部通过'));
  process.exit(failed ? 1 : 0);
})().catch(err => { console.error('测试异常：', err && err.stack || err); process.exit(1); });
