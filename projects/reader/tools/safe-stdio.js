'use strict';
/* 测试脚本共用防护（纯 Node，无需 Electron）：
   guard(notify)
     - console.log/error 写已断开的管道会同步抛 EPIPE，经 uncaughtException 再 log 形成死循环；
       这里统一吞掉写失败。
     - stdout/stderr 两个管道都断开 = 父进程已不在，测试继续跑只会孤儿化常驻，此时主动退出。
   bounded(fn, ms, fallback)
     - Electron 的 webContents.executeJavaScript 在目标已销毁 / 渲染进程卡死时可能永不 resolve，
       轮询里一次这样的调用就会把 waitFor 整体吊死；统一包一层超时兜底。 */
function guard(notify) {
  const broken = new Set();
  const note = m => { try { notify && notify(m); } catch {} };
  const onBroken = name => () => {
    if (broken.has(name)) return;
    broken.add(name);
    note('-- stdio 断开：' + name + '（父进程可能已不在）');
    if (broken.size >= 2) {
      note('-- stdout/stderr 均已断开，自行退出以避免孤儿进程');
      // 延迟到下一拍再退：当前还处在流错误的 emit 栈里，同步 process.exit 在退出刷新
      // 断管时 Windows 上会被信号杀（退出码拿不到 2）
      setImmediate(() => process.exit(2));
    }
  };
  try { process.stdout.on('error', onBroken('stdout')); } catch {}
  try { process.stderr.on('error', onBroken('stderr')); } catch {}
  const wrap = fn => (...args) => { try { fn(...args); } catch {} };
  console.log = wrap(console.log.bind(console));
  console.error = wrap(console.error.bind(console));
}

function bounded(fn, ms, fallback = false) {
  let req;
  try { req = fn(); } catch { return Promise.resolve(fallback); }
  if (!req || typeof req.then !== 'function') return Promise.resolve(req);
  return Promise.race([
    req.then(v => v).catch(() => fallback),
    new Promise(res => setTimeout(() => res(fallback), ms))
  ]);
}

module.exports = { guard, bounded };
