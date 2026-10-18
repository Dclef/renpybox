/**
 * 更新链路的网络出口。
 *
 * 这里的 fetch 会读应用设置里的「网络代理」（config.json 的 proxy_url /
 * proxy_enable）：Electron 主进程的更新请求不再无视这个开关。
 * 代理走 Electron session.setProxy，不需要额外依赖（undici 不会被
 * electron-builder 打进包里）。
 *
 * 说明：本文件依赖 electron，纯 node 测试不导入它；测试用注入的
 * fetchImpl 覆盖同样的逻辑分支。
 */

/** 从 config.json 读出代理设置；读不到就当作未启用。 */
export function readProxySettings(configPath, readFileSync) {
  if (!configPath) return { enabled: false, url: '' };
  try {
    const raw = readFileSync(configPath, 'utf8');
    const config = JSON.parse(raw);
    const url = typeof config?.proxy_url === 'string' ? config.proxy_url.trim() : '';
    return { enabled: config?.proxy_enable === true, url };
  } catch {
    return { enabled: false, url: '' };
  }
}

/**
 * 根据设置算出 Electron setProxy 需要的配置。
 *
 *   proxy_enable = false          → direct（不走代理）
 *   proxy_enable = true + 有地址  → 用用户填的地址
 *   proxy_enable = true + 空地址  → system（跟随系统代理）
 *
 * 第三条是用户明确要求的：地址留空就吃系统代理（Clash 之类开启「系统代理」
 * 后无需在应用里再抄一遍端口）。
 */
export function resolveProxyConfig({ enabled, url } = {}) {
  if (!enabled) return { mode: 'direct' };
  const target = typeof url === 'string' ? url.trim() : '';
  if (!target) return { mode: 'system' };
  // 允许用户只填 host:port；Electron 会把非 scheme 值当 HTTP 代理解析。
  return { proxyRules: /:\/\//.test(target) ? target : `http://${target}` };
}

/** 把配置归一成可比较的字符串，用于判断是否需要重新下发。 */
function proxyKey(config) {
  return JSON.stringify(config);
}

/**
 * 创建一个走代理（如已启用）的 Electron fetch。
 *
 * 返回的函数签名与全局 fetch 一致，可直接注入 updater。
 */
export function createElectronFetch({ electron, partition = 'renpy-update', proxyFor = () => ({ enabled: false, url: '' }), log = console } = {}) {
  const { session, net } = electron;
  // 只能等 app ready 之后才能 fromPartition；此处延迟到首次请求时创建。
  let updateSession = null;
  let appliedProxy = null;

  const ensureSession = () => {
    if (!updateSession) updateSession = session.fromPartition(partition);
    return updateSession;
  };

  async function applyProxy() {
    const target = ensureSession();
    const config = resolveProxyConfig(proxyFor() || {});
    const key = proxyKey(config);
    if (key === appliedProxy) return;
    appliedProxy = key;
    try {
      await target.setProxy(config);
    } catch (error) {
      log.error('[update] 应用代理设置失败', error);
      appliedProxy = null;
    }
  }

  return async function electronFetch(input, init = {}) {
    await applyProxy();
    return net.fetch(typeof input === 'string' ? input : String(input), { ...init, session: ensureSession() });
  };
}
