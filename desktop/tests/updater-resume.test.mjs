import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { downloadWithMirrors } from '../main/updater.js';

const ASSET = 'https://github.com/dclef/renpybox/releases/download/v0.9.9/RenpyBox-0.9.9-x64.exe';
const MIRROR_FAST = 'https://fastgit.cc/' + ASSET;
const MIRROR_CORS = 'https://cors.isteed.cc/' + ASSET;
const MIRROR_DIRECT = ASSET;
const PAYLOAD = Buffer.from('renpybox-installer-payload');
const EXPECTED_SIZE = PAYLOAD.length;
const EXPECTED_DIGEST = 'sha256:' + createHash('sha256').update(PAYLOAD).digest('hex');

const networkError = message => Object.assign(new Error(message ?? 'net::ERR_CONNECTION_CLOSED'), { kind: 'download', retryable: true });
const fatalError = message => Object.assign(new Error(message ?? 'GitHub 返回 404'), { kind: 'download', retryable: false });
const okResponse = () => new Response(PAYLOAD, { status: 200, headers: { 'content-length': String(EXPECTED_SIZE) } });
/** 卡死的候选：fetch 挂住不返回，只有 inner signal abort 才结束（模拟首字节超时）。 */
const stalledFetch = () => (_url, init = {}) => new Promise((_resolve, reject) => {
  const rejectAbort = () => reject(Object.assign(new Error('The operation was aborted'), { name: 'AbortError' }));
  if (init.signal?.aborted) rejectAbort();
  else init.signal?.addEventListener?.('abort', rejectAbort, { once: true });
});

async function workdir(run) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'renpybox-resume-'));
  try {
    return await run(path.join(directory, 'installer.exe'));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

/** 按顺序吐出预设结果（Error 则抛错，响应对象则直接返回，函数则调用它），并记录 url 与退避时长。 */
function fixture(outcomes) {
  const calls = [];
  const sleeps = [];
  let index = 0;
  return {
    calls,
    sleeps,
    fetchImpl: async (url, init) => {
      calls.push(url);
      const outcome = outcomes[Math.min(index, outcomes.length - 1)];
      index += 1;
      const value = typeof outcome === 'function' ? await outcome(url, init) : outcome;
      if (value instanceof Error) throw value;
      return value;
    },
    sleepImpl: async ms => { sleeps.push(ms); },
  };
}

test('网络错误自动退避重试：同一候选最多 2 次，退避 1s', async () => {
  await workdir(async destination => {
    const f = fixture([networkError(), okResponse()]);
    const result = await downloadWithMirrors(ASSET, destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: f.fetchImpl,
      sleepImpl: f.sleepImpl,
    });
    assert.equal(result.size, EXPECTED_SIZE);
    assert.deepEqual(f.calls, [MIRROR_FAST, MIRROR_FAST], '第一次失败后在同一候选上重试');
    assert.deepEqual(f.sleeps, [1000]);
  });
});

test('同一候选两次都失败就换下一个候选，每次候选取一次退避', async () => {
  await workdir(async destination => {
    const f = fixture([networkError(), networkError(), networkError(), okResponse()]);
    const result = await downloadWithMirrors(ASSET, destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: f.fetchImpl,
      sleepImpl: f.sleepImpl,
    });
    assert.equal(result.size, EXPECTED_SIZE);
    assert.deepEqual(f.calls, [MIRROR_FAST, MIRROR_FAST, MIRROR_CORS, MIRROR_CORS]);
    // 每个候选最多 2 次尝试 → 每个候选只发生一次退避（attempt=1 时为 1s）。
    assert.deepEqual(f.sleeps, [1000, 1000]);
  });
});

test('首字节超时的候选立即换下一个，不占用重试次数', async () => {
  await workdir(async destination => {
    const calls = [];
    const stalls = [];
    const fetchImpl = async (url, init) => {
      calls.push(url);
      if (url.startsWith('https://fastgit.cc/')) {
        stalls.push(url);
        return stalledFetch()(url, init);
      }
      return okResponse();
    };
    const result = await downloadWithMirrors(ASSET, destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl,
      sleepImpl: async () => {},
      stallTimeoutMs: 20,
    });
    assert.equal(result.size, EXPECTED_SIZE);
    assert.equal(stalls.length, 1, '卡死的候选只试一次就放弃');
    assert.deepEqual(calls, [MIRROR_FAST, MIRROR_CORS], '不再对卡死的候选重试');
  });
});

test('stall 换候选后仍然把进度透传给调用方', async () => {
  await workdir(async destination => {
    const progress = [];
    const fetchImpl = async (url, init) => (url.startsWith('https://fastgit.cc/')
      ? stalledFetch()(url, init)
      : okResponse());
    await downloadWithMirrors(ASSET, destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl,
      sleepImpl: async () => {},
      stallTimeoutMs: 20,
      onProgress: event => progress.push(event),
    });
    assert.deepEqual(progress, [{ received: EXPECTED_SIZE, total: EXPECTED_SIZE }]);
  });
});

test('不可重试错误（retryable:false）立刻换下一个候选，不退避', async () => {
  await workdir(async destination => {
    const f = fixture([fatalError(), okResponse()]);
    const result = await downloadWithMirrors(ASSET, destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: f.fetchImpl,
      sleepImpl: f.sleepImpl,
    });
    assert.equal(result.size, EXPECTED_SIZE);
    assert.deepEqual(f.calls, [MIRROR_FAST, MIRROR_CORS]);
    assert.deepEqual(f.sleeps, []);
  });
});

test('用户取消（外层 signal）立即抛 AbortError，不重试也不换候选', async () => {
  await workdir(async destination => {
    const controller = new AbortController();
    const calls = [];
    // 下载途中的信号：外层 abort 通过内部 controller 转发，不会重试。
    const fetchImpl = async (url, init = {}) => {
      calls.push(url);
      controller.abort();
      return stalledFetch()(url, init);
    };
    await assert.rejects(
      downloadWithMirrors(ASSET, destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl,
        sleepImpl: async () => {},
        signal: controller.signal,
        stallTimeoutMs: 5000,
      }),
      error => error?.name === 'AbortError',
    );
    assert.deepEqual(calls, [MIRROR_FAST], '取消后不再尝试任何候选');
  });
});

test('全部候选失败时抛最后一个错误', async () => {
  await workdir(async destination => {
    const calls = [];
    const sleeps = [];
    const errors = [];
    const fetchImpl = async url => {
      calls.push(url);
      const error = networkError('第 ' + calls.length + ' 次失败');
      errors.push(error);
      throw error;
    };
    await assert.rejects(
      downloadWithMirrors(ASSET, destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl,
        sleepImpl: async ms => { sleeps.push(ms); },
      }),
      error => error === errors[errors.length - 1] && /第 6 次失败/.test(error.message),
    );
    assert.equal(calls.length, 6, '3 个候选 × 每个 2 次');
    assert.deepEqual([...new Set(calls)], [MIRROR_FAST, MIRROR_CORS, MIRROR_DIRECT]);
    assert.deepEqual(sleeps, [1000, 1000, 1000], '每个候选内部退避一次');
  });
});

test('非 GitHub 地址只有直连一个候选，重试 2 次后失败', async () => {
  await workdir(async destination => {
    const calls = [];
    const sleeps = [];
    const fetchImpl = async url => {
      calls.push(url);
      throw networkError('连接被重置');
    };
    await assert.rejects(
      downloadWithMirrors('https://example.test/x.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl,
        sleepImpl: async ms => { sleeps.push(ms); },
      }),
      /连接被重置/,
    );
    assert.deepEqual(calls, ['https://example.test/x.exe', 'https://example.test/x.exe']);
    assert.deepEqual(sleeps, [1000]);
  });
});
