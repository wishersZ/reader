const JSZip = require('jszip');
const { XMLParser } = require('fast-xml-parser');
const cheerio = require('cheerio');
const fs = require('fs');
const path = require('path');
(async () => {
  const file = process.argv[2] || path.join(process.env.TEMP, 'yuedu-test.epub');
  const zip = await JSZip.loadAsync(fs.readFileSync(file));
  const parser = new XMLParser({ ignoreAttributes: false, attributeNamePrefix: '@_', isArray: name => ['rootfile', 'item', 'itemref'].includes(name) });
  const container = parser.parse(await zip.file('META-INF/container.xml').async('string'));
  const opfPath = container.container.rootfiles.rootfile[0]['@_full-path'];
  const pkg = parser.parse(await zip.file(opfPath).async('string')).package;
  const items = Object.fromEntries(pkg.manifest.item.map(item => [item['@_id'], item]));
  const href = items[pkg.spine.itemref[0]['@_idref']]['@_href'];
  const html = await zip.file('OEBPS/' + href).async('string');
  const $ = cheerio.load(html);
  const paragraphs = $('body').find('h1,h2,h3,h4,h5,h6,p,li,blockquote,pre').map((_, el) => $(el).text().trim()).get();
  console.log(JSON.stringify({ title: pkg.metadata['dc:title'], author: pkg.metadata['dc:creator'], paragraphs }));
})();
