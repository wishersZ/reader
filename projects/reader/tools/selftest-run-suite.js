'use strict';
/* run-suite 运行台账守卫的纯 Node 自测（不需要 git / Electron / 提权）。
   用 NR_FP 固定指纹、NR_LEDGER 指向临时台账，验证五个行为：
   RUN→记录、同状态→SKIP（且不新增台账）、指纹变化→RUN、失败→允许重跑、FORCE→强制、stats 可读。
   子进程输出用文件重定向而非管道，受限沙箱也可运行。 */
const assert = require('assert');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawnSync } = require('child_process');

const RUN_SUITE = path.join(__dirname, 'run-suite.js');
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'run-suite-selftest-'));
const ledger = path.join(tmp, 'ledger.json');
let seq = 0;

function run(envPatch, args) {
  const out = path.join(tmp, 'out' + (++seq) + '.txt');
  const fd = fs.openSync(out, 'w');
  const base = { ...process.env };
  delete base.FORCE; delete base.NR_FP; delete base.NR_LEDGER;   // 隔离外部干扰
  const r = spawnSync(process.execPath, [RUN_SUITE, ...args], {
    env: { ...base, NR_FP: 'fp-test', NR_LEDGER: ledger, ...envPatch },
    stdio: ['ignore', fd, fd],
    cwd: path.join(__dirname, '..'),
    windowsHide: true
  });
  fs.closeSync(fd);
  return { code: r.status, text: fs.readFileSync(out, 'utf8') };
}
const rows = () => JSON.parse(fs.readFileSync(ledger, 'utf8'));

// 被测命令：立即成功 / 立即失败（无管道）
const OK = ['--', process.execPath, '-e', 'process.exit(0)'];
const BAD = ['--', process.execPath, '-e', 'process.exit(7)'];

let r;
// 1) 首次运行 → RUN + PASS + 台账 1 行
r = run({}, ['demo', ...OK]);
assert.ok(r.text.includes('[RUN ] demo'), '首次应 RUN：' + r.text);
assert.ok(r.text.includes('[DONE] demo：PASS'), '首次应 PASS：' + r.text);
assert.strictEqual(r.code, 0, '首次退出码应为 0');
assert.strictEqual(rows().length, 1, '首次应写 1 行台账');

// 2) 同状态再跑 → SKIP，且不新增台账
r = run({}, ['demo', ...OK]);
assert.ok(r.text.includes('[SKIP] demo'), '同状态应 SKIP：' + r.text);
assert.strictEqual(r.code, 0, 'SKIP 退出码应为 0');
assert.strictEqual(rows().length, 1, 'SKIP 不应新增台账');

// 3) 指纹变化 → RUN
r = run({ NR_FP: 'fp-other' }, ['demo', ...OK]);
assert.ok(r.text.includes('[RUN ] demo'), '指纹变化应 RUN：' + r.text);
assert.strictEqual(rows().length, 2, '应新增 1 行台账');

// 4) 失败 → 允许同状态重跑（不 SKIP）
r = run({}, ['demo2', ...BAD]);
assert.ok(r.text.includes('[RUN ] demo2'), '失败首次应 RUN');
assert.ok(r.text.includes('[DONE] demo2：FAIL(7)'), '应记录 FAIL(7)：' + r.text);
assert.strictEqual(r.code, 7, '退出码应透传 7');
r = run({}, ['demo2', ...BAD]);
assert.ok(r.text.includes('[RUN ] demo2'), '失败后同状态应允许重跑：' + r.text);

// 5) FORCE=1 强制重跑已通过的套件
r = run({ FORCE: '1' }, ['demo', ...OK]);
assert.ok(r.text.includes('[RUN ] demo'), 'FORCE 应强制 RUN：' + r.text);

// 6) stats 能读出最近记录
r = run({}, ['stats', '--json']);
const list = JSON.parse(r.text.trim());
const demo = list.find(x => x.suite === 'demo');
const demo2 = list.find(x => x.suite === 'demo2');
assert.ok(demo && demo.ok === true, 'stats 应显示 demo 通过的最近记录');
assert.ok(demo2 && demo2.ok === false && demo2.exit === 7, 'stats 应显示 demo2 失败记录');

fs.rmSync(tmp, { recursive: true, force: true });
console.log('selftest-run-suite: ALL PASS');
