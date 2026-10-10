import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { readLogTail } from '../main/log-reader.js';

const MAX_BYTES = 256 * 1024;
const LF = String.fromCharCode(10);
const CRLF = String.fromCharCode(13, 10);

async function fixture(t, data) {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'renpybox-log-reader-'));
  t.after(() => rm(dir, { recursive: true, force: true }));
  const filename = path.join(dir, 'desktop.log');
  if (data !== undefined) await writeFile(filename, data);
  return filename;
}

test('Chinese diagnostics and multiline errors retain exact content without modifying the file', async (t) => {
  const text = [
    '2026-10-10 [ERROR] 无法读取项目：测试游戏',
    'Traceback (most recent call last):',
    '  File "backend.py", line 42, in load_project',
    '    raise ValueError("配置不存在")',
    'ValueError: 配置不存在',
    '',
  ].join(CRLF);
  const filename = await fixture(t, text);
  const before = await stat(filename);
  assert.deepEqual(await readLogTail(filename), { text, truncated: false });
  assert.deepEqual(await readFile(filename), Buffer.from(text));
  assert.equal((await stat(filename)).mtimeMs, before.mtimeMs);
});

test('missing log returns empty state without creating a file', async (t) => {
  const filename = await fixture(t);
  assert.deepEqual(await readLogTail(filename), { text: '', truncated: false });
  await assert.rejects(stat(filename), { code: 'ENOENT' });
});

test('empty log returns an untruncated empty state', async (t) => {
  const filename = await fixture(t, '');
  assert.deepEqual(await readLogTail(filename), { text: '', truncated: false });
});

test('exactly 2000 lines retain their final newline without reporting truncation', async (t) => {
  const text = Array.from({ length: 2000 }, (_, i) => 'line ' + i).join(LF) + LF;
  assert.deepEqual(await readLogTail(await fixture(t, text)), { text, truncated: false });
});

for (const ending of ['', LF]) {
  test('more than 2000 lines retain only the last 2000, final newline=' + Boolean(ending), async (t) => {
    const lines = Array.from({ length: 2025 }, (_, i) => '日志 ' + String(i).padStart(4, '0'));
    const filename = await fixture(t, lines.join(LF) + ending);
    assert.deepEqual(await readLogTail(filename), {
      text: lines.slice(-2000).join(LF) + ending, truncated: true,
    });
  });
}

test('byte-limited Chinese logs begin with a complete record and preserve CRLF without corruption', async (t) => {
  const lines = Array.from({ length: 110 }, (_, i) =>
    '记录编号=' + String(i).padStart(4, '0') + ' ' + '中文日志'.repeat(220) + CRLF);
  const data = Buffer.from(lines.join(''));
  const cutByte = data[data.length - MAX_BYTES];
  assert.equal(cutByte & 0xc0, 0x80, 'fixture must cut inside a UTF-8 character');
  const filename = await fixture(t, data);
  const result = await readLogTail(filename);
  const fullLinesInLimit = Math.floor(MAX_BYTES / Buffer.byteLength(lines[0]));
  assert.deepEqual(result, { text: lines.slice(-fullLinesInLimit).join(''), truncated: true });
  assert.ok(!result.text.includes('�'));
  assert.ok(Buffer.byteLength(result.text) <= MAX_BYTES);
  assert.deepEqual(await readFile(filename), data);
});

test('oversized single-line log never starts or ends with an incomplete UTF-8 character', async (t) => {
  const filename = await fixture(t, '中'.repeat(100000));
  assert.deepEqual(await readLogTail(filename), {
    text: '中'.repeat(Math.floor(MAX_BYTES / 3)), truncated: true,
  });
});

test('byte window aligned to a record boundary retains the complete first record', async (t) => {
  const first = '首条完整记录' + LF;
  const last = LF + '最后一条' + LF;
  const tail = first + 'x'.repeat(MAX_BYTES - Buffer.byteLength(first) - Buffer.byteLength(last)) + last;
  assert.equal(Buffer.byteLength(tail), MAX_BYTES);
  const filename = await fixture(t, 'old record' + LF + tail);
  const result = await readLogTail(filename);
  assert.equal(result.truncated, true);
  assert.ok(result.text.startsWith(first), 'complete first record at exact byte boundary was dropped');
  assert.equal(result.text, tail);
});

for (const partialBytes of [1, 2]) {
  test('in-progress UTF-8 write omits an incomplete final character of ' + partialBytes + ' bytes', async (t) => {
    const complete = '运行记录' + LF + '正在写入：';
    const chinese = Buffer.from('中');
    const filename = await fixture(t, Buffer.concat([Buffer.from(complete), chinese.subarray(0, partialBytes)]));
    assert.deepEqual(await readLogTail(filename), { text: complete, truncated: false });
    await writeFile(filename, complete + '中');
    assert.deepEqual(await readLogTail(filename), { text: complete + '中', truncated: false });
  });
}
