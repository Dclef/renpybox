/**
 * GitHub 下载镜像候选。
 *
 * GitHub 的 Release 资产走 objects.githubusercontent.com，在国内经常
 * 连不上（表现为 fetch failed 或长时间挂起），而 api.github.com 本身
 * 往往是通的。所以只在「下载资产」这一步做镜像回退，接口查询保持直连。
 *
 * 只改写 github.com 的 release 下载地址；其它域名原样返回，避免把
 * 用户自己的镜像也套一层。镜像按顺序尝试，第一个成功即停止。
 */
export const GITHUB_DOWNLOAD_MIRRORS = Object.freeze([
  'https://ghfast.top/',
  'https://gh-proxy.com/',
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

/** 下载候选顺序：直连优先，其次镜像。去重后返回。 */
export function downloadCandidates(url, mirrors = GITHUB_DOWNLOAD_MIRRORS) {
  return [...new Set([url, ...mirrorUrls(url, mirrors)].filter(Boolean))];
}
