import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { createLogger } from '../main/logger.js';

test('desktop log keeps full errors, long context and Chinese text', (t) => {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'renpybox-log-test-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const log = createLogger(dir, { consoleOutput: false });
  const error = new Error('后端启动失败');
  const longMessage = 'context: ' + 'X'.repeat(600) + ' final detail';
  log.error('startup', error);
  log(longMessage);
  const content = readFileSync(log.path, 'utf8');
  assert.ok(content.includes(error.stack));
  assert.ok(content.includes(longMessage));
  assert.ok(content.includes('[ERROR]'));
});

test('concise console preserves diagnostic detail in the file', (t) => {
  const dir = mkdtempSync(path.join(os.tmpdir(), 'renpybox-log-test-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  const printed = [];
  t.mock.method(console, 'error', (line) => printed.push(line));
  t.mock.method(console, 'log', (line) => printed.push(line));
  const log = createLogger(dir);
  const error = new Error('missing backend');
  log.error(error);
  log.debug('probe diagnostics');
  assert.equal(printed.length, 1);
  assert.ok(printed[0].includes(error.message));
  assert.equal(printed[0].split(String.fromCharCode(10)).length, 1);
  const content = readFileSync(log.path, 'utf8');
  assert.ok(content.includes(error.stack));
  assert.ok(content.includes('probe diagnostics'));
});
