const JSZip = require('jszip');
const fs = require('fs');
(async () => {
  const z = new JSZip();
  z.file('mimetype', 'application/epub+zip');
  z.file('META-INF/container.xml', `<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>`);
  z.file('OEBPS/content.opf', `<?xml version="1.0"?><package xmlns:dc="http://purl.org/dc/elements/1.1/"><metadata><dc:title>测试电子书</dc:title><dc:creator>测试作者</dc:creator></metadata><manifest><item id="c1" href="chapter1.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="c1"/></spine></package>`);
  z.file('OEBPS/chapter1.xhtml', `<html xmlns="http://www.w3.org/1999/xhtml"><body><h1>第一章 开始</h1><p>这是第一段正文。</p><p>这是第二段正文。</p></body></html>`);
  fs.writeFileSync(process.argv[2] || 'test.epub', await z.generateAsync({ type: 'nodebuffer' }));
})();
