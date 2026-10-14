export const DESKTOP_TAG_PATTERN = /^(?:RenpyBox_)?v?(\d+)\.(\d+)\.(\d+)(?:-newui\.(\d+))?$/;

/** 标签只是版本信息；是否属于桌面发布由对应版本的安装包决定。 */
export function parseDesktopVersion(value) {
  const match = DESKTOP_TAG_PATTERN.exec(String(value ?? '').trim());
  if (!match) return null;
  const version = { major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]), build: match[4] === undefined ? null : Number(match[4]) };
  return Object.values(version).every(part => part === null || Number.isSafeInteger(part)) ? version : null;
}

export function desktopVersionString(value) {
  const version = parseDesktopVersion(value);
  if (!version) return '';
  const core = `${version.major}.${version.minor}.${version.patch}`;
  return version.build === null ? core : `${core}-newui.${version.build}`;
}

export function compareDesktopVersions(left, right) {
  const a = parseDesktopVersion(left);
  const b = parseDesktopVersion(right);
  if (!a && !b) return 0;
  if (!a) return -1;
  if (!b) return 1;
  for (const key of ['major', 'minor', 'patch']) {
    if (a[key] !== b[key]) return a[key] > b[key] ? 1 : -1;
  }
  if (a.build === b.build) return 0;
  if (a.build === null) return 1;
  if (b.build === null) return -1;
  return a.build > b.build ? 1 : -1;
}

/** 必须属于同一个版本；ZIP、Qt 兼容包及误传的旧安装包均不参与更新。 */
export function selectInstallerAsset(release) {
  const version = desktopVersionString(release?.tag_name);
  if (!version) return null;
  const expectedName = `RenpyBox-NewUI-${version}-x64.exe`.toLowerCase();
  const assets = Array.isArray(release?.assets) ? release.assets : [];
  return assets.find(asset => (
    String(asset?.name ?? '').toLowerCase() === expectedName
    && Number.isSafeInteger(asset?.size) && asset.size > 0
    && /^https?:\/\//i.test(String(asset?.browser_download_url ?? ''))
  )) ?? null;
}

export function pickLatestRelease(releases, currentVersion) {
  const stable = parseDesktopVersion(currentVersion)?.build === null;
  const candidates = (Array.isArray(releases) ? releases : [])
    .filter(release => release && release.draft !== true)
    .filter(release => parseDesktopVersion(release.tag_name) && selectInstallerAsset(release))
    .filter(release => !stable || (release.prerelease !== true && parseDesktopVersion(release.tag_name).build === null))
    .filter(release => compareDesktopVersions(release.tag_name, currentVersion) > 0);
  return candidates.sort((a, b) => compareDesktopVersions(b.tag_name, a.tag_name))[0] ?? null;
}
