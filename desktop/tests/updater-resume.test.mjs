import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { downloadWithMirrors } from '../main/updater.js';

const ASSET = 'https://github.com/dclef/renpybox/releases/download/v0.9.9/RenpyBox-0.9.9-x64.exe';
const MIRROR_DIRECT = ASSET;
const MIRROR_FAST = 'https://ghfast.top/' + ASSET;
const MIRROR_PROXY = 'https://gh-proxy.com/' + ASSET;
const PAYLOAD = Buffer.from('renpybox-installer-payload');
const EXPECTED_SIZE = PAYLOAD.length;
const EXPECTED_DIGEST = 'sha256:' + createHash('sha256').update(PAYLOAD).digest('hex');

const networkError = message => Object.assign(new Error(message ?? 'net::ERR_CONNECTION_CLOSED'), { kind: 'download', retryable: true });
const fatalError = message => Object.assign(new Error(message ?? 'GitHub 返回 404'), { kind: 'download', retryable: false });
const okResponse = () => new Response(PAYLOAD, { status: 200, headers: { 'content-length': String(EXPECTED_SIZE) } });

async function workdir(run) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'renpybox-resume-'));
  try {
    return await run(path.join(directory, 'installer.exe'));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

/** 按顺序吐出预设结果（Error 则抛错，响应对象则直接返回），并记录 url 与退避时长。 */
function fixture(outcomes) {
  const calls = [];
  const sleeps = [];
  let index = 0;
  return {
    calls,
    sleeps,
    fetchImpl: async url => {
      calls.push(url);
      const outcome = outcomes[Math.min(index, outcomes.length - 1)];
      index += 1;
      if (outcome instanceof Error) throw outcome;
      return outcome;
    },
    sleepImpl: async ms => { sleeps.push(ms); },
  };
}

test('网络错误自动退避重试：同一候选最多 3 次，退避 1s/2s', async () => {
  await workdir(async destination => {
    const f = fixture([networkError(), networkError(), okResponse()]);
    const result = await downloadWithMirrors(ASSET, destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: f.fetchImpl,
      sleepImpl: f.sleepImpl,
    });
    assert.equal(result.size, EXPECTED_SIZE);
    assert.equal(result.total, EXPECTED_SIZE);
    assert.equal(f.calls.length, 3, '第三次尝试才成功');
    assert.deepEqual(f.calls, [MIRROR_DIRECT, MIRROR_DIRECT, MIRROR_DIRECT], '退避重试不应中途换候选');
    assert.deepEqual(f.sleeps, [1000, 2000]);
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
    assert.deepEqual(f.calls, [MIRROR_DIRECT, MIRROR_FAST]);
    assert.deepEqual(f.sleeps, []);
  });
});

test('用户取消（AbortError）立即抛出，不重试也不换镜像', async () => {
  await workdir(async destination => {
    const f = fixture([Object.assign(new Error('The operation was aborted'), { name: 'AbortError' })]);
    await assert.rejects(
      downloadWithMirrors(ASSET, destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: f.fetchImpl,
        sleepImpl: f.sleepImpl,
      }),
      error => error?.name === 'AbortError',
    );
    assert.equal(f.calls.length, 1);
    assert.deepEqual(f.sleeps, []);
  });
});

test('三个候选全部失败时抛最后一个错误', async () => {
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
      error => error === errors[errors.length - 1] && /第 9 次失败/.test(error.message),
    );
    assert.equal(calls.length, 9, '3 个候选 × 每个 3 次');
    assert.deepEqual([...new Set(calls)], [MIRROR_DIRECT, MIRROR_FAST, MIRROR_PROXY]);
    assert.deepEqual(sleeps, [1000, 2000, 1000, 2000, 1000, 2000]);
  });
});

test('非 GitHub 地址只有直连一个候选，重试 3 次后失败', async () => {
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
    assert.deepEqual(calls, ['https://example.test/x.exe', 'https://example.test/x.exe', 'https://example.test/x.exe']);
    assert.deepEqual(sleeps, [1000, 2000]);
  });
});

