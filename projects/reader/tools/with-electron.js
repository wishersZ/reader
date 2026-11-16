'use strict';
/* 用真正的 Electron 主进程方式运行目标脚本。
   某些环境（如 CI / 沙箱）会设 ELECTRON_RUN_AS_NODE=1，导致 electron 退化成普通 Node、
   require('electron') 只剩一个路径字符串；这里剥离该变量后再启动。 */
const { spawnSync } = require('child_process');
const electronBin = require('electron');   // 在 Node 下 require('electron') 得到可执行文件路径
if (typeof electronBin !== 'string' || !electronBin) {
  console.error('无法定位 electron 可执行文件');
  process.exit(1);
}
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
const args = process.argv.slice(2);
if (!args.length) { console.error('用法：node tools/with-electron.js <脚本> [参数…]'); process.exit(1); }
const r = spawnSync(electronBin, args, { stdio: 'inherit', env, windowsHide: false });
if (r.error) { console.error('启动 electron 失败：' + r.error.message); process.exit(1); }
process.exit(r.status == null ? 1 : r.status);
