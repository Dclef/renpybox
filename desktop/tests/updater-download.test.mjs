import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdtemp, readFile, readdir, rm, stat, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { downloadInstaller } from '../main/updater-download.js';

const PAYLOAD = Buffer.from('renpybox-installer-payload');
const DIGEST = createHash('sha256').update(PAYLOAD).digest('hex');
const EXPECTED_DIGEST = 'sha256:' + DIGEST;
const EXPECTED_SIZE = PAYLOAD.length;
const HEAD = PAYLOAD.subarray(0, 10);
const TAIL = PAYLOAD.subarray(10);

const respond = (body, { status = 200, headers } = {}) => new Response(body, {
  status,
  headers: headers ?? { 'content-length': String(EXPECTED_SIZE) },
});

/** 手工构造响应：只提供实现真正读取的字段，便于控制 range 头与流中断。 */
const rawResponse = ({ status = 200, headers = {}, stream }) => ({
  ok: status >= 200 && status < 300,
  status,
  headers: new Headers(headers),
  body: stream,
});

const streamOf = chunks => new ReadableStream({
  start(controller) {
    for (const chunk of chunks) controller.enqueue(new Uint8Array(chunk));
    controller.close();
  },
});

/** 先给出一段数据再报错，模拟下载途中的 ERR_CONNECTION_CLOSED。 */
const brokenStream = prefix => {
  let step = 0;
  return new ReadableStream({
    pull(controller) {
      if (step === 0) {
        step = 1;
        if (prefix && prefix.length) controller.enqueue(new Uint8Array(prefix));
        return;
      }
      controller.error(Object.assign(new Error('net::ERR_CONNECTION_CLOSED'), { code: 'ERR_CONNECTION_CLOSED' }));
    },
  });
};

const sizeOf = async file => (await stat(file).catch(() => null))?.size ?? 0;

const partialOf = destination => destination + '.part';

async function workdir(run) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'renpybox-download-'));
  try {
    return await run(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test('缺少发布校验值或大小无效时直接拒绝，不产生任何文件', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: 'md5:whatever',
        fetchImpl: async () => { throw new Error('不应发起下载'); },
      }),
      error => error.retryable === false && /SHA-256/.test(error.message),
    );
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: 0,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => { throw new Error('不应发起下载'); },
      }),
      error => error.retryable === false && /大小无效/.test(error.message),
    );
    assert.equal(existsSync(destination), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('下载内容大小与发布资产不一致时丢弃临时文件', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => respond(PAYLOAD, { headers: { 'content-length': String(EXPECTED_SIZE + 1) } }),
      }),
      /长度/,
    );
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE + 1,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => respond(PAYLOAD, { headers: {} }),
      }),
      /文件大小与发布资产不一致/,
    );
    assert.equal(existsSync(destination), false);
    assert.equal(existsSync(partialOf(destination)), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('SHA-256 不匹配时丢弃安装包', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: 'sha256:' + '0'.repeat(64),
        fetchImpl: async () => respond(PAYLOAD),
      }),
      error => error.retryable === false && /校验失败/.test(error.message),
    );
    assert.equal(existsSync(destination), false);
    assert.equal(existsSync(partialOf(destination)), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('校验通过后才发布安装包，并报告进度', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'nested', 'installer.exe');
    const progress = [];
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      onProgress: event => progress.push(event),
      fetchImpl: async () => respond(PAYLOAD),
    });
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
    assert.deepEqual(progress, [{ received: EXPECTED_SIZE, total: EXPECTED_SIZE }]);
    assert.deepEqual(await readdir(path.dirname(destination)), ['installer.exe']);
  });
});

test('HTTP 失败直接放弃该地址且不留文件', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => respond('rate limited', { status: 403, headers: {} }),
      }),
      error => error.retryable === false && /GitHub 返回 403/.test(error.message),
    );
    assert.equal(existsSync(destination), false);
    assert.equal(existsSync(partialOf(destination)), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('取消前未发起请求时不留文件', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const controller = new AbortController();
    controller.abort();
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        signal: controller.signal,
        fetchImpl: async () => { throw new Error('取消后不应发起下载'); },
      }),
      error => error?.name === 'AbortError',
    );
    assert.equal(existsSync(destination), false);
    assert.deepEqual(await readdir(directory), []);
  });
});

test('下载途中取消保留 .part 供续传', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    const controller = new AbortController();
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        signal: controller.signal,
        onProgress: () => controller.abort(),
        fetchImpl: async () => rawResponse({
          headers: { 'content-length': String(EXPECTED_SIZE) },
          stream: streamOf([PAYLOAD]),
        }),
      }),
      error => error?.name === 'AbortError',
    );
    assert.equal(existsSync(destination), false);
    assert.equal(existsSync(partial), true, '取消后必须保留 .part，下次自动续传');
  });
});

test('预置半截 .part 时带 Range 续传，进度不丢已有字节', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    await writeFile(partial, HEAD);
    const requests = [];
    const progress = [];
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      onProgress: event => progress.push(event),
      fetchImpl: async (url, init = {}) => {
        requests.push({ url, headers: init.headers ?? {} });
        return rawResponse({
          status: 206,
          headers: { 'content-range': 'bytes ' + HEAD.length + '-' + (EXPECTED_SIZE - 1) + '/' + EXPECTED_SIZE },
          stream: streamOf([TAIL]),
        });
      },
    });
    assert.equal(requests.length, 1);
    assert.equal(requests[0].headers.range, 'bytes=' + HEAD.length + '-');
    assert.equal(requests[0].headers['user-agent'], 'RenpyBox');
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
    assert.deepEqual(progress, [{ received: EXPECTED_SIZE, total: EXPECTED_SIZE }]);
    assert.equal(existsSync(partial), false);
  });
});

test('服务器忽略 Range 回 200 时从零重下', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    await writeFile(partial, HEAD);
    const requests = [];
    const progress = [];
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      onProgress: event => progress.push(event),
      fetchImpl: async (url, init = {}) => {
        requests.push({ url, headers: init.headers ?? {} });
        return respond(PAYLOAD);
      },
    });
    assert.equal(requests[0].headers.range, 'bytes=' + HEAD.length + '-');
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
    assert.deepEqual(progress, [{ received: EXPECTED_SIZE, total: EXPECTED_SIZE }]);
  });
});

test('连接中途断开保留 .part，第二次调用续传成功', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    await writeFile(partial, HEAD);
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => rawResponse({
          status: 206,
          headers: { 'content-range': 'bytes ' + HEAD.length + '-' + (EXPECTED_SIZE - 1) + '/' + EXPECTED_SIZE },
          stream: brokenStream(TAIL.subarray(0, 4)),
        }),
      }),
      error => error.retryable === true,
    );
    assert.equal(existsSync(partial), true, '网络中断后必须保留 .part');
    assert.ok(await sizeOf(partial) >= HEAD.length, '已下载的前缀不能被截断');

    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: async (url, init = {}) => {
        const offset = await sizeOf(partial);
        if (offset <= 0) return respond(PAYLOAD);
        const headers = { 'content-range': 'bytes ' + offset + '-' + (EXPECTED_SIZE - 1) + '/' + EXPECTED_SIZE };
        if (init.headers?.range) headers['content-range'] = headers['content-range'];
        return rawResponse({ status: 206, headers, stream: streamOf([PAYLOAD.subarray(offset)]) });
      },
    });
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
    assert.equal(existsSync(partial), false);
  });
});

test('.part 超过发布资产大小时丢弃重下', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    await writeFile(partial, Buffer.concat([PAYLOAD, Buffer.from('extra')]));
    const requests = [];
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: async (url, init = {}) => {
        requests.push(init.headers ?? {});
        return respond(PAYLOAD);
      },
    });
    assert.equal(requests[0].range, undefined, '超大 .part 必须丢弃，不带 Range 重下');
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
  });
});

test('.part 长度已满但哈希错误时丢弃重下', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    await writeFile(partial, Buffer.alloc(EXPECTED_SIZE, 0x61));
    const requests = [];
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: async (url, init = {}) => {
        requests.push(init.headers ?? {});
        return respond(PAYLOAD);
      },
    });
    assert.equal(requests[0].range, undefined);
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
  });
});

test('目标文件已存在且校验通过时不发请求直接返回', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await writeFile(destination, PAYLOAD);
    let requests = 0;
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: async () => { requests += 1; throw new Error('已完成时不应发起下载'); },
    });
    assert.equal(requests, 0);
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
  });
});

test('目标文件校验不通过时删除后重新下载', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    await writeFile(destination, Buffer.alloc(EXPECTED_SIZE, 0x62));
    const result = await downloadInstaller('https://example.test/installer.exe', destination, {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: async () => respond(PAYLOAD),
    });
    assert.deepEqual(result, { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE });
    assert.deepEqual(await readFile(destination), PAYLOAD);
  });
});

test('206 的 content-range 与已下载进度不符时报可重试错误并保留 .part', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    await writeFile(partial, HEAD);
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => rawResponse({
          status: 206,
          headers: { 'content-range': 'bytes 4-' + (EXPECTED_SIZE - 1) + '/' + EXPECTED_SIZE },
          stream: streamOf([PAYLOAD.subarray(4)]),
        }),
      }),
      error => error.retryable === true && /续传区间/.test(error.message),
    );
    assert.equal(existsSync(partial), true);
    assert.equal(existsSync(destination), false);
  });
});

test('416 时丢弃 .part 并报可重试错误', async () => {
  await workdir(async directory => {
    const destination = path.join(directory, 'installer.exe');
    const partial = partialOf(destination);
    await writeFile(partial, HEAD);
    await assert.rejects(
      downloadInstaller('https://example.test/installer.exe', destination, {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: async () => rawResponse({ status: 416, stream: streamOf([]) }),
      }),
      error => error.retryable === true && /416/.test(error.message),
    );
    assert.equal(existsSync(partial), false);
    assert.deepEqual(await readdir(directory), []);
  });
});
