import test from 'node:test';
import assert from 'node:assert/strict';
import {execFile} from 'node:child_process';
import {readdir} from 'node:fs/promises';
import path from 'node:path';
import {promisify} from 'node:util';
import {FRONTEND, SHOTS} from './support.mjs';

const exec = promisify(execFile);
const databases = async () => (await readdir(SHOTS).catch(error => {
 if(error.code === 'ENOENT') return [];
 throw error;
})).filter(name => name.startsWith('db-')).sort();

for(const [name, python, message] of [
 ['Python 不存在', path.join(SHOTS, 'missing-python'), '无法启动测试 Python'],
 ['夹具提前退出', process.execPath, '夹具服务提前退出'],
]) {
 test(`${name}时明确失败并清理临时数据库目录`, async () => {
  const before = await databases();
  // Run in a fresh process: an unhandled spawn error must fail this test, not be hidden.
  const code = `import assert from 'node:assert/strict';
   import {startFixture} from './e2e/support.mjs';
   await assert.rejects(startFixture(0), error => error.message.includes(${JSON.stringify(message)}));`;
  await exec(process.execPath, ['--input-type=module', '-e', code], {
   cwd: FRONTEND, env: {...process.env, SOLOMEAL_PYTHON: python}, timeout: 15_000,
   windowsHide: true,
  });
  assert.deepEqual(await databases(), before, '失败启动也不应遗留数据库目录');
 });
}
