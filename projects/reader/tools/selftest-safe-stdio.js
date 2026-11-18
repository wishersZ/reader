'use strict';
/* safe-stdio 的纯 Node 自测（不需要 Electron，几秒跑完）：
   覆盖断管写不外抛、单向断开不退出、双向断开退出码 2、bounded 正常/拒绝/永不 resolve 三分支。
   用法：node tools/selftest-safe-stdio.js */
const assert = require('assert');
const { spawnSync } = require('child_process');
const { guard, bounded } = require('./safe-stdio');

(async () => {
  const notes = [];
  guard(m => notes.push(m));

  // 1) 底层写抛 EPIPE 风格的错误：console.log 不能把异常抛出来
  const origWrite = process.stdout.write.bind(process.stdout);
  process.stdout.write = () => { const e = new Error('EPIPE: broken pipe, write'); e.code = 'EPIPE'; throw e; };
  let escaped = null;
  try { console.log('should-not-escape'); } catch (e) { escaped = e; }
  process.stdout.write = origWrite;
  assert.strictEqual(escaped, null, 'console.log 异常外抛');

  // 2) 单向断开：记录但不退出
  process.stdout.emit('error', new Error('EPIPE'));
  assert.strictEqual(notes.filter(m => m.includes('stdout')).length, 1, '单向断开应有记录');

  // 3) bounded 三分支
  assert.strictEqual(await bounded(() => Promise.resolve(42), 300, 'FB'), 42, '正常 resolve');
  assert.strictEqual(await bounded(() => Promise.reject(new Error('x')), 300, 'FB'), 'FB', 'reject 兜底');
  const t0 = Date.now();
  assert.strictEqual(await bounded(() => new Promise(() => {}), 200, 'FB'), 'FB', '永不 resolve 兜底');
  assert.ok(Date.now() - t0 < 1000, '兜底太慢');

  // 4) 双向断开：子进程退出码 2；单向断开：子进程存活
  const childTwo = spawnSync(process.execPath, ['-e', `
    require(${JSON.stringify(__dirname + '/safe-stdio.js')}).guard(() => {});
    process.stdout.emit('error', new Error('EPIPE'));
    process.stderr.emit('error', new Error('EPIPE'));
    setTimeout(() => {}, 5000);
  `], { encoding: 'utf8' });
  assert.strictEqual(childTwo.status, 2, '双向断开应退出码 2，实际 ' + childTwo.status);

  const childOne = spawnSync(process.execPath, ['-e', `
    require(${JSON.stringify(__dirname + '/safe-stdio.js')}).guard(() => {});
    process.stdout.emit('error', new Error('EPIPE'));
    setTimeout(() => { console.log('still-alive'); }, 300);
  `], { encoding: 'utf8' });
  assert.strictEqual(childOne.status, 0, '单向断开不应退出');
  assert.ok(childOne.stdout.includes('still-alive'), '单向断开后进程仍存活');

  console.log('selftest-safe-stdio: ALL PASS');
})().catch(e => { console.error('selftest-safe-stdio: FAIL', e && e.message || e); process.exit(1); });
