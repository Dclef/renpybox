/**
 * 更新链路的代理出口与网络设置读取。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/updater-net.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { readFileSync } from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { createElectronFetch, readProxySettings, resolveProxyConfig } from '../main/updater-net.js';

async function workdir(run) {
  const directory = await mkdtemp(path.join(os.tmpdir(), 'renpybox-net-'));
  try {
    return await run(directory);
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

test('代理设置从 config.json 读取，缺文件或坏 JSON 都不抛错', async () => {
  await workdir(async directory => {
    const file = path.join(directory, 'config.json');
    assert.deepEqual(readProxySettings(file, readFileSync), { enabled: false, url: '' });
    await writeFile(file, JSON.stringify({ proxy_url: ' http://127.0.0.1:7890 ', proxy_enable: true }), 'utf8');
    assert.deepEqual(readProxySettings(file, readFileSync), { enabled: true, url: 'http://127.0.0.1:7890' });
    // 开关关掉时即使有地址也算未启用
    await writeFile(file, JSON.stringify({ proxy_url: 'http://127.0.0.1:7890', proxy_enable: false }), 'utf8');
    assert.equal(readProxySettings(file, readFileSync).enabled, false);
    await writeFile(file, '{ 坏 json', 'utf8');
    assert.deepEqual(readProxySettings(file, readFileSync), { enabled: false, url: '' });
    assert.deepEqual(readProxySettings('', readFileSync), { enabled: false, url: '' });
  });
});

/** 最小 electron 替身：记录 setProxy 与 net.fetch 的调用。 */
function fakeElectron() {
  const proxies = [];
  const fetches = [];
  const electron = {
    session: {
      fromPartition: () => ({
        setProxy: async (config) => { proxies.push(config); },
      }),
    },
    net: {
      fetch: async (url, init) => { fetches.push({ url, init }); return new Response('ok'); },
    },
  };
  return { electron, proxies, fetches };
}

test('启用代理时按 host:port 补 http:// 并下发给 session', async () => {
  const { electron, proxies, fetches } = fakeElectron();
  let settings = { enabled: true, url: '127.0.0.1:7890' };
  const fetchWithProxy = createElectronFetch({ electron, proxyFor: () => settings, log: { error() {} } });
  await fetchWithProxy('https://api.github.com/repos/dclef/renpybox/releases');
  assert.deepEqual(proxies, [{ proxyRules: 'http://127.0.0.1:7890' }]);
  assert.equal(fetches.length, 1);
  assert.ok(fetches[0].init.session, '必须使用带代理的 session');

  // 设置没变就不重复下发
  await fetchWithProxy('https://example.test/x');
  assert.equal(proxies.length, 1);

  // 关掉代理后回到 direct
  settings = { enabled: false, url: '127.0.0.1:7890' };
  await fetchWithProxy('https://example.test/y');
  assert.deepEqual(proxies[1], { mode: 'direct' });
});

test('代理设置已带 scheme 时不再补 http://', async () => {
  const { electron, proxies } = fakeElectron();
  const fetchWithProxy = createElectronFetch({
    electron,
    proxyFor: () => ({ enabled: true, url: 'socks5://127.0.0.1:1080' }),
    log: { error() {} },
  });
  await fetchWithProxy('https://example.test/x');
  assert.deepEqual(proxies, [{ proxyRules: 'socks5://127.0.0.1:1080' }]);
});

test('setProxy 抛错不阻断请求，只记日志', async () => {
  const errors = [];
  const electron = {
    session: { fromPartition: () => ({ setProxy: async () => { throw new Error('boom'); } }) },
    net: { fetch: async () => new Response('ok') },
  };
  const fetchWithProxy = createElectronFetch({
    electron,
    proxyFor: () => ({ enabled: true, url: 'http://127.0.0.1:7890' }),
    log: { error: (...args) => errors.push(args) },
  });
  const response = await fetchWithProxy('https://example.test/x');
  assert.equal(await response.text(), 'ok');
  assert.equal(errors.length, 1);
});

test('地址留空但开关打开时跟随系统代理', () => {
  // 用户要求：不用手抄 Clash 的端口，开开关 + 地址留空即可
  assert.deepEqual(resolveProxyConfig({ enabled: true, url: '' }), { mode: 'system' });
  assert.deepEqual(resolveProxyConfig({ enabled: true, url: '   ' }), { mode: 'system' });
  assert.deepEqual(resolveProxyConfig({ enabled: false, url: '' }), { mode: 'direct' });
  assert.deepEqual(resolveProxyConfig({}), { mode: 'direct' });
  assert.deepEqual(resolveProxyConfig({ enabled: true, url: '127.0.0.1:7890' }), { proxyRules: 'http://127.0.0.1:7890' });
  assert.deepEqual(resolveProxyConfig({ enabled: true, url: 'http://127.0.0.1:7890' }), { proxyRules: 'http://127.0.0.1:7890' });
});

test('开关打开且地址留空时下发 system 模式', async () => {
  const { electron, proxies } = fakeElectron();
  const fetchWithProxy = createElectronFetch({
    electron,
    proxyFor: () => ({ enabled: true, url: '' }),
    log: { error() {} },
  });
  await fetchWithProxy('https://example.test/x');
  assert.deepEqual(proxies, [{ mode: 'system' }]);
});
