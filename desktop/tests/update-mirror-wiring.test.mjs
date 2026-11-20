import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { createDesktopUpdater, downloadWithMirrors, readUpdateMirrors } from '../main/updater.js';

const ASSET = 'https://github.com/dclef/renpybox/releases/download/v0.9.9/RenpyBox-0.9.9-x64.exe';
const PAYLOAD = Buffer.from('renpybox-installer-payload');
const EXPECTED_SIZE = PAYLOAD.length;
const EXPECTED_DIGEST = 'sha256:' + createHash('sha256').update(PAYLOAD).digest('hex');
const okResponse = () => new Response(PAYLOAD, { status: 200, headers: { 'content-length': String(EXPECTED_SIZE) } });

async function workdir(run) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'renpybox-wiring-'));
  try {
    return await run(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

async function configFile(directory, name, payload) {
  const file = path.join(directory, name);
  await writeFile(file, typeof payload === 'string' ? payload : JSON.stringify(payload), 'utf8');
  return file;
}

/** 记录 fetchImpl 收到的候选顺序；收到第一个候选就返回成功，后续候选不会被请求。 */
function recorder() {
  const calls = [];
  return {
    calls,
    fetchImpl: async (url) => { calls.push(url); return okResponse(); },
    sleepImpl: async () => {},
  };
}

// ---------- readUpdateMirrors ----------

test('readUpdateMirrors 返回清理后的镜像前缀列表', async () => {
  await workdir(async directory => {
    const file = await configFile(directory, 'config.json', {
      update_mirror_urls: ['  https://a.example/  ', 'http://b.example/', 'https://c.example/'],
    });
    assert.deepEqual(readUpdateMirrors(file, readFileSync), [
      'https://a.example/',
      'http://b.example/',
      'https://c.example/',
    ]);
  });
});

test('readUpdateMirrors 对缺失/空白/损坏的配置一律返回 null', async () => {
  await workdir(async directory => {
    const empty = await configFile(directory, 'a.json', {});
    const notArray = await configFile(directory, 'b.json', { update_mirror_urls: 'https://a.example/' });
    const allInvalid = await configFile(directory, 'c.json', { update_mirror_urls: [1, null, {}, ''] });
    const noProtocol = await configFile(directory, 'd.json', {
      update_mirror_urls: ['a.example/', 'https://b.example', '   ', 'ftp://c.example/'],
    });
    const broken = await configFile(directory, 'e.json', '{ 坏 json');

    for (const file of [empty, notArray, allInvalid, noProtocol, broken]) {
      assert.equal(readUpdateMirrors(file, readFileSync), null, file);
    }
    assert.equal(readUpdateMirrors(path.join(directory, 'missing.json'), readFileSync), null);
    assert.equal(readUpdateMirrors('', readFileSync), null);
  });
});

test('readUpdateMirrors 混入非法项时只保留合法项', async () => {
  await workdir(async directory => {
    const file = await configFile(directory, 'config.json', {
      update_mirror_urls: ['https://ok.example/', 'ftp://bad.example/', 'https://no-slash.example', 42],
    });
    assert.deepEqual(readUpdateMirrors(file, readFileSync), ['https://ok.example/']);
  });
});

// ---------- downloadWithMirrors 的 mirrors 选项 ----------

test('传自定义 mirrors 时第一个候选来自用户配置', async () => {
  await workdir(async directory => {
    const rec = recorder();
    await downloadWithMirrors(ASSET, path.join(directory, 'installer.exe'), {
      expectedSize: EXPECTED_SIZE,
      expectedDigest: EXPECTED_DIGEST,
      fetchImpl: rec.fetchImpl,
      sleepImpl: rec.sleepImpl,
      mirrors: ['https://my.mirror/'],
    });
    assert.deepEqual(rec.calls, ['https://my.mirror/' + ASSET]);
  });
});

test('mirrors 为 null/空数组/非数组时回退内置默认镜像，而不是只剩直连', async () => {
  await workdir(async directory => {
    for (const [index, mirrors] of [null, [], 'not-an-array'].entries()) {
      const rec = recorder();
      await downloadWithMirrors(ASSET, path.join(directory, 'installer-' + index + '.exe'), {
        expectedSize: EXPECTED_SIZE,
        expectedDigest: EXPECTED_DIGEST,
        fetchImpl: rec.fetchImpl,
        sleepImpl: rec.sleepImpl,
        mirrors,
      });
      assert.deepEqual(rec.calls, ['https://fastgit.cc/' + ASSET]);
    }
  });
});

// ---------- createDesktopUpdater 的 mirrorsFor ----------

function updaterFixture(tempDir, extra = {}) {
  return createDesktopUpdater({
    packaged: true,
    version: '0.9.0',
    tempDir,
    log: Object.assign(() => {}, { error: () => {} }),
    requestJson: async () => [{
      tag_name: 'v0.9.9',
      html_url: 'https://github.com/example/renpybox/releases/tag/v0.9.9',
      body: 'notes',
      draft: false,
      prerelease: false,
      assets: [{ name: 'RenpyBox-0.9.9-x64.exe', size: EXPECTED_SIZE, digest: EXPECTED_DIGEST, browser_download_url: ASSET }],
    }],
    ...extra,
  });
}

test('createDesktopUpdater 注入 mirrorsFor 后实际下载走用户镜像', async () => {
  await workdir(async directory => {
    const rec = recorder();
    const updater = updaterFixture(path.join(directory, 'update'), {
      mirrorsFor: () => ['https://my.mirror/'],
      fetchImpl: rec.fetchImpl,
    });
    await updater.check();
    const done = await updater.download();
    assert.equal(done.status, 'downloaded');
    assert.equal(rec.calls[0], 'https://my.mirror/' + ASSET, '第一跳必须是用户配置的镜像');
  });
});

test('注入自定义 downloadFile 时同样收到 mirrorsFor 的值（不许静默丢配置）', async () => {
  await workdir(async directory => {
    const seen = [];
    const updater = updaterFixture(path.join(directory, 'update'), {
      mirrorsFor: () => ['https://my.mirror/'],
      // 调用方自己实现下载：mirrors 必须由 fetchAsset 传进来，
      // 不能依赖默认 downloadFile 的包装（那层在注入时会被整个替换掉）。
      downloadFile: async (url, destination, options = {}) => {
        seen.push({ url, mirrors: options.mirrors });
        return { path: destination, size: EXPECTED_SIZE, total: EXPECTED_SIZE };
      },
    });
    await updater.check();
    assert.equal((await updater.download()).status, 'downloaded');
    assert.deepEqual(seen, [{ url: ASSET, mirrors: ['https://my.mirror/'] }]);
  });
});

test('mirrorsFor 返回 null 时下载回退内置默认镜像', async () => {
  await workdir(async directory => {
    const rec = recorder();
    const updater = updaterFixture(path.join(directory, 'update'), { fetchImpl: rec.fetchImpl });
    await updater.check();
    await updater.download();
    assert.deepEqual(rec.calls, ['https://fastgit.cc/' + ASSET]);
  });
});

test('每次下载都重新调用 mirrorsFor，改完设置无需重启', async () => {
  await workdir(async directory => {
    const mirrors = [['https://first.example/'], ['https://second.example/']];
    let reads = 0;
    let round = 1;
    const calls = [];
    // 用默认下载实现（真 downloadWithMirrors），只替换 fetchImpl：
    // 第一轮全部失败逼出 error，第二轮换配置成功后第一跳就该换镜像。
    const updater = updaterFixture(path.join(directory, 'update'), {
      mirrorsFor: () => mirrors[Math.min(reads++, mirrors.length - 1)],
      fetchImpl: async (url) => {
        calls.push(url);
        if (round === 1) throw Object.assign(new Error('net::ERR_CONNECTION_CLOSED'), { kind: 'download' });
        return okResponse();
      },
      sleepImpl: async () => {},
    });
    await updater.check();
    assert.equal((await updater.download()).status, 'error');
    const firstRound = calls.slice();
    round = 2;
    reads = 1;
    calls.length = 0;
    await updater.check();
    assert.equal((await updater.download()).status, 'downloaded');
    assert.equal(firstRound[0], 'https://first.example/' + ASSET, '第一轮用第一个镜像');
    assert.equal(calls[0], 'https://second.example/' + ASSET, '第二轮必须重新读配置并换镜像');
  });
});
