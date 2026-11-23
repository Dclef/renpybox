import test from 'node:test';
import assert from 'node:assert/strict';

import { probeMirrors, probeTargetUrl, DEFAULT_PROBE_ASSET } from '../main/mirror-probe.js';

const okBody = new Uint8Array(1024);

function okResponse(status = 206) {
  return new Response(okBody, { status, headers: { 'content-length': String(okBody.byteLength) } });
}

test('probeTargetUrl：空前缀直连资产，其它前缀拼接', () => {
  assert.equal(probeTargetUrl(''), DEFAULT_PROBE_ASSET);
  assert.equal(probeTargetUrl('https://fastgit.cc/'), `https://fastgit.cc/${DEFAULT_PROBE_ASSET}`);
});

test('206 Range 成功返回延迟与速率', async () => {
  const result = await probeMirrors(['https://a.example/'], {
    fetchImpl: async (url, init) => {
      assert.match(url, /^https:\/\/a\.example\//);
      assert.equal(init.headers.Range, 'bytes=0-262143');
      return okResponse(206);
    },
    timeoutMs: 2000,
  });
  assert.equal(result.length, 1);
  assert.equal(result[0].ok, true);
  assert.ok(result[0].bytesPerSec > 0);
  assert.ok(result[0].latencyMs >= 0);
});

test('404 与 403 记为不可用', async () => {
  const result = await probeMirrors(['https://missing/', 'https://denied/'], {
    fetchImpl: async (url) => new Response(null, { status: url.includes('denied') ? 403 : 404 }),
    timeoutMs: 2000,
  });
  assert.equal(result.every((item) => item.ok === false && item.bytesPerSec === 0), true);
});

test('超时 abort 记为不可用且不抛', async () => {
  const result = await probeMirrors(['https://slow/'], {
    fetchImpl: (_url, init) => new Promise((_resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(new Error('aborted')));
    }),
    timeoutMs: 30,
  });
  assert.equal(result[0].ok, false);
  assert.equal(result[0].bytesPerSec, 0);
});

test('全部失败仍返回与输入等长的结果', async () => {
  const result = await probeMirrors(['https://a/', 'https://b/', ''], {
    fetchImpl: async () => { throw new Error('offline'); },
    timeoutMs: 200,
  });
  assert.equal(result.length, 3);
  assert.equal(result.every((item) => !item.ok), true);
});

test('并发探测：同时在途数等于候选数', async () => {
  let inflight = 0;
  let peak = 0;
  await probeMirrors(['https://a/', 'https://b/', ''], {
    fetchImpl: async () => {
      inflight += 1;
      peak = Math.max(peak, inflight);
      await new Promise((resolve) => setTimeout(resolve, 40));
      inflight -= 1;
      return okResponse();
    },
    timeoutMs: 2000,
  });
  assert.equal(peak, 3);
});
