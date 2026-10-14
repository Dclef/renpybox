import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { once } from 'node:events';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

const consoleUrl = new URL('../main/stdio-console.js', import.meta.url).href;
const loggerUrl = new URL('../main/logger.js', import.meta.url).href;

for (const stream of ['stdout', 'stderr']) {
  test(`closed ${stream} pipe keeps process alive and full diagnostics in the file`, { timeout: 10_000 }, async (t) => {
    const dir = mkdtempSync(path.join(os.tmpdir(), 'renpybox-pipe-test-'));
    const source = `
      import ${JSON.stringify(consoleUrl)};
      import { createLogger } from ${JSON.stringify(loggerUrl)};
      const log = createLogger(${JSON.stringify(dir)});
      process.send('ready');
      process.once('message', () => {
        process.${stream}.once('error', (error) => {
          log.error(new Error('断管道后完整诊断仍可保存'));
          process.send(error.code);
          process.disconnect();
        });
        process.${stream}.write('pipe probe'.repeat(8192));
      });
    `;
    const child = spawn(process.execPath, ['--input-type=module', '-e', source], {
      stdio: ['ignore', 'pipe', 'pipe', 'ipc'], windowsHide: true,
    });
    t.after(() => {
      if (child.exitCode === null) child.kill();
      rmSync(dir, { recursive: true, force: true });
    });
    const messages = [];
    let output = '';
    child.stdout.on('data', chunk => { output += chunk; });
    child.stderr.on('data', chunk => { output += chunk; });
    child.on('message', message => {
      messages.push(message);
      if (message === 'ready') {
        child[stream].destroy();
        child.send('write');
      }
    });
    const [code, signal] = await once(child, 'close');
    assert.equal(code, 0, output);
    assert.equal(signal, null);
    assert.deepEqual(messages, ['ready', 'EPIPE']);
    assert.match(readFileSync(path.join(dir, 'desktop.log'), 'utf8'), /\[ERROR\] Error: 断管道后完整诊断仍可保存\r?\n\s+at/);
  });
}

test('standard stream errors other than EPIPE remain fatal', () => {
  const result = spawnSync(process.execPath, ['--input-type=module', '-e', `
    import ${JSON.stringify(consoleUrl)};
    process.stdout.emit('error', Object.assign(new Error('unexpected stdio failure'), { code: 'EIO' }));
  `], { encoding: 'utf8', windowsHide: true, timeout: 10_000 });
  assert.ifError(result.error);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /unexpected stdio failure/);
});
