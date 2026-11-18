'use strict';
/* 测试运行守卫：根治"同一代码状态反复跑全量"。
   代码状态指纹 = HEAD + 工作区改动(git diff HEAD) + 未跟踪文件内容。
   同一状态下某套件已通过时默认 SKIP（不再启动 Electron）；FORCE=1 强制重跑。
   台账：.tmp-check/run-ledger.json（git 忽略），同时记录实测耗时，统计不再需要额外跑。

   用法：
     node tools/run-suite.js <suite> -- <command...>
     node tools/run-suite.js stats [--json]
   示例（package.json 已接入，直接 npm run test:window 即可）：
     node tools/run-suite.js window -- node tools/with-electron.js tools/test-window-modes.js
   FORCE（PowerShell）：$env:FORCE='1'; npm test
*/
const { execFileSync, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
require('./safe-stdio').guard(() => {});

const ROOT = path.join(__dirname, '..');
const LEDGER = process.env.NR_LEDGER || path.join(ROOT, '.tmp-check', 'run-ledger.json');
const MAX_ROWS = 120;
/* NR_FP / NR_LEDGER 仅供 tools/selftest-run-suite.js 做隔离测试（固定指纹、临时台账），
   正常运行不要设置。 */

function git(args) {
  try {
    return execFileSync('git', args, { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, stdio: ['ignore', 'pipe', 'ignore'] });
  } catch { return null; }
}

function fingerprint() {
  const head = git(['rev-parse', 'HEAD']);
  const diff = git(['diff', 'HEAD', '--binary']);
  if (head == null || diff == null) return 'nogit-' + Date.now();   // 无 git 时不跳过，永远真跑
  const h = crypto.createHash('sha256').update(head).update(diff);
  const untracked = (git(['ls-files', '--others', '--exclude-standard']) || '')
    .split('\n').map(s => s.trim()).filter(Boolean).sort();
  for (const rel of untracked) {
    h.update(rel);
    try { h.update(fs.readFileSync(path.join(ROOT, rel))); } catch { h.update('unreadable'); }
  }
  return h.digest('hex');
}

function loadLedger() {
  try { const v = JSON.parse(fs.readFileSync(LEDGER, 'utf8')); return Array.isArray(v) ? v : []; } catch { return []; }
}
function saveLedger(rows) {
  try { fs.mkdirSync(path.dirname(LEDGER), { recursive: true }); fs.writeFileSync(LEDGER, JSON.stringify(rows.slice(-MAX_ROWS), null, 1)); } catch {}
}

const [,, suite, ...rest] = process.argv;
if (!suite || suite === '--help' || suite === '-h') {
  console.log('用法：node tools/run-suite.js <suite> -- <command...> | stats [--json]');
  process.exit(2);
}

/* ---- stats：读台账出统计表（零额外运行） ---- */
if (suite === 'stats') {
  const last = new Map();
  for (const r of loadLedger()) last.set(r.suite, r);   // 后写覆盖先写
  const list = [...last.values()].sort((a, b) => String(a.suite).localeCompare(String(b.suite)));
  if (rest.includes('--json')) { console.log(JSON.stringify(list, null, 2)); process.exit(0); }
  const pad = (s, n) => String(s).padEnd(n);
  console.log(pad('suite', 8) + pad('state', 10) + pad('last run', 22) + pad('duration', 10) + 'result');
  let total = 0;
  for (const r of list) {
    total += r.ms || 0;
    console.log(pad(r.suite, 8) + pad(r.fp8, 10) + pad(new Date(r.ts).toLocaleString(), 22) + pad(((r.ms || 0) / 1000).toFixed(1) + 's', 10) + (r.ok ? 'PASS' : 'FAIL(' + r.exit + ')'));
  }
  console.log('最近各套件合计: ' + (total / 1000).toFixed(1) + 's');
  process.exit(0);
}

/* ---- 运行模式 ---- */
const sep = rest.indexOf('--');
if (sep < 0 || sep === rest.length - 1) {
  console.log('缺少 "-- <command...>"。示例：node tools/run-suite.js window -- node tools/with-electron.js tools/test-window-modes.js');
  process.exit(2);
}
const cmd = rest.slice(sep + 1);

const fp = process.env.NR_FP || fingerprint(), fp8 = fp.slice(0, 8);
const rows = loadLedger();
const prev = [...rows].reverse().find(r => r.suite === suite && r.fp === fp);
const force = String(process.env.FORCE || '') === '1';

if (prev && prev.ok && !force) {
  console.log('[SKIP] ' + suite + '：代码状态 ' + fp8 + ' 已于 ' + new Date(prev.ts).toLocaleString() +
    ' 通过（耗时 ' + ((prev.ms || 0) / 1000).toFixed(1) + 's），不重复跑。FORCE=1 可强制。');
  process.exit(0);
}

console.log('[RUN ] ' + suite + '：代码状态 ' + fp8 + '（' + (force ? 'FORCE 强制' : prev && !prev.ok ? '上次同状态失败，重跑' : '该状态未跑过') + '）');
const t0 = Date.now();
const r = spawnSync(cmd[0], cmd.slice(1), { cwd: ROOT, stdio: 'inherit', env: process.env });
const ms = Date.now() - t0;
const exit = r.error ? 1 : (r.status == null ? 1 : r.status);
if (r.error) console.error('[ERR ] 启动失败：' + r.error.message);
rows.push({ suite, fp, fp8, ts: Date.now(), ms, ok: exit === 0, exit });
saveLedger(rows);
console.log('[DONE] ' + suite + '：' + (exit === 0 ? 'PASS' : 'FAIL(' + exit + ')') + '，耗时 ' + (ms / 1000).toFixed(1) + 's');
process.exit(exit);
