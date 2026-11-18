'use strict';
/* Electron 冒烟测试共用基建（纯 Node + Electron，无业务断言）：
   makeLogger  双写日志（控制台 + .tmp-check/<name>.log）与 PASS/FAIL 计数
   makeEval    渲染进程求值：executeJavaScript 在 webContents 已销毁 / 渲染卡死时可能永不
               resolve，一次这样的调用就会把 waitFor 整体吊死——统一销毁检查 + 超时兜底
   waitFor     状态轮询（替代固定 sleep）：每次探测调用都有独立超时
   armWatchdog 看门狗：任何原因吊死都必须在预算内给出结论并退出
   guard/bounded 透传 safe-stdio（断管防 EPIPE 死循环、父进程死亡后孤儿自杀）
   约定：新测试脚本一律基于本模块，禁止裸 executeJavaScript、裸 console.log。 */
const fs = require('fs');
const path = require('path');
const { guard, bounded } = require('./safe-stdio');

const wait = ms => new Promise(r => setTimeout(r, ms));

function makeLogger(logName) {
  const logFile = path.join(__dirname, '..', '.tmp-check', logName);
  const lines = [];
  const say = line => {
    lines.push(line);
    try { console.log(line); } catch {}
    try { fs.mkdirSync(path.dirname(logFile), { recursive: true }); fs.writeFileSync(logFile, lines.join('\n') + '\n'); } catch {}
  };
  let failed = 0;
  const check = (name, ok, extra) => {
    if (!ok) failed++;
    say((ok ? 'PASS  ' : 'FAIL  ') + name + (extra === undefined ? '' : '   [' + extra + ']'));
  };
  return { say, check, get failed() { return failed; }, logFile };
}

function makeEval(getWin, ms = 2000) {
  return (code, timeout = ms) => {
    const w = getWin();
    if (!w || w.isDestroyed() || w.webContents.isDestroyed()) return Promise.resolve(false);
    return bounded(() => w.webContents.executeJavaScript(code, true), timeout);
  };
}

/* 等状态而不是睡固定时长：窗口 resize / 重建的完成时机不稳定，固定 wait 会造成假失败 */
async function waitFor(fn, timeout = 2500, step = 100, perCallMs = 2000) {
  const end = Date.now() + timeout;
  do {
    const v = await bounded(fn, perCallMs, false);
    if (v) return v;
    await wait(step);
  } while (Date.now() < end);
  return null;
}

function armWatchdog(say, app, ms = 180000) {
  const t = setTimeout(() => { say('FAIL  看门狗超时（' + ms + 'ms），测试未完成，强制退出'); app.exit(3); }, ms);
  t.unref();
  return t;
}

module.exports = { guard, bounded, wait, makeLogger, makeEval, waitFor, armWatchdog };
