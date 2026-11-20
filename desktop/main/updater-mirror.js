/**
 * GitHub 下载镜像候选。
 *
 * GitHub 的 Release 资产走 objects.githubusercontent.com，在国内经常
 * 连不上（表现为 fetch failed 或长时间挂起），而 api.github.com 本身
 * 往往是通的。所以只在「下载资产」这一步做镜像回退，接口查询保持直连。
 *
 * 只改写 github.com 的 release 下载地址；其它域名原样返回，避免把
 * 用户自己的镜像也套一层。
 *
 * 默认只内置两条实测可用的加速镜像（2026-11-20 单机实测，235MB 完整包，
 * 单线程，SHA-256 校验）：fastgit.cc 7.4s(31.7MB/s) → cors.isteed.cc 10.0s(23.5MB/s)。
 * 同时实测淘汰：ghfast.top 90 秒 0 字节，ghproxy.net / gh-proxy.com 只有百来 KB/s，
 * 直连 objects.githubusercontent.com 20 秒超时 0 字节——都不再进默认清单。
 * 两条镜像都支持 Range（206 + Content-Range），续传可用。
 *
 * 用户可以在设置里自建/调整镜像列表，那份配置见 updateMirrorSettings。
 */
export const GITHUB_DOWNLOAD_MIRRORS = Object.freeze([
  'https://fastgit.cc/',
  'https://cors.isteed.cc/',
]);

/** 只对 GitHub Release 下载地址生成镜像候选，其它 url 返回空数组。 */
export function mirrorUrls(url, mirrors = GITHUB_DOWNLOAD_MIRRORS) {
  if (typeof url !== 'string' || !url) return [];
  let parsed;
  try { parsed = new URL(url); } catch { return []; }
  if (parsed.protocol !== 'https:') return [];
  if (parsed.hostname.toLowerCase() !== 'github.com') return [];
  if (!parsed.pathname.includes('/releases/download/')) return [];
  return mirrors.map(prefix => `${prefix}${url}`);
}

/**
 * 下载候选顺序：**镜像优先，直连兜底**。去重后返回。
 *
 * 直连 objects.githubusercontent.com 在国内常常挂满超时（实测 20 秒 0 字节），
 * 所以不再占第一位；它留在最后是为了镜像全部失效、或者用户自己挂了代理时
 * 仍有最后一条路。非 GitHub 地址没有镜像，返回的只有它自己。
 */
export function downloadCandidates(url, mirrors = GITHUB_DOWNLOAD_MIRRORS) {
  return [...new Set([...mirrorUrls(url, mirrors), url].filter(Boolean))];
}
