/**
 * 更新镜像与提示逻辑。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/updater-mirror.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';

import { downloadCandidates, mirrorUrls } from '../main/updater-mirror.js';
import { latestChangelogSection, shouldAnnounceUpdate, shouldOfferUpdate } from '../renderer/src/updateNotice.mjs';

const ASSET = 'https://github.com/dclef/renpybox/releases/download/v0.9.2/RenpyBox-0.9.2-x64.exe';

test('只对 GitHub Release 下载地址生成镜像，其它 url 原样跳过', () => {
  assert.deepEqual(mirrorUrls(ASSET), [
    `https://ghfast.top/${ASSET}`,
    `https://gh-proxy.com/${ASSET}`,
  ]);
  // API 查询与普通网页不套镜像
  assert.deepEqual(mirrorUrls('https://api.github.com/repos/dclef/renpybox/releases'), []);
  assert.deepEqual(mirrorUrls('https://github.com/dclef/renpybox'), []);
  assert.deepEqual(mirrorUrls('http://github.com/a/b/releases/download/v1/x.exe'), []);
  assert.deepEqual(mirrorUrls(''), []);
  assert.deepEqual(mirrorUrls(null), []);
});

test('下载候选直连优先、镜像兜底，且不重复', () => {
  const candidates = downloadCandidates(ASSET);
  assert.equal(candidates[0], ASSET);
  assert.equal(candidates.length, 3);
  assert.equal(new Set(candidates).size, 3);
  // 非 GitHub 地址只有自己一个候选
  assert.deepEqual(downloadCandidates('https://example.test/x.exe'), ['https://example.test/x.exe']);
});

test('更新日志只取第一个版本段落', () => {
  const markdown = '# 更新日志\n\n## v0.9.2 - 2026-10-18\n- 修 A\n- 修 B\n\n## v0.9.1 - 2026-10-17\n- 旧项\n';
  const section = latestChangelogSection(markdown);
  assert.match(section, /^## v0\.9\.2/);
  assert.match(section, /修 A/);
  assert.doesNotMatch(section, /v0\.9\.1/);
  assert.equal(latestChangelogSection('没有标题'), '没有标题');
  assert.equal(latestChangelogSection(''), '');
});

test('发现新版本的弹窗条件', () => {
  const base = { packaged: true, status: 'available', version: '0.9.2' };
  assert.equal(shouldOfferUpdate(base), true);
  assert.equal(shouldOfferUpdate({ ...base, status: 'latest' }), false);
  assert.equal(shouldOfferUpdate({ ...base, packaged: false }), false, '开发模式不弹');
  assert.equal(shouldOfferUpdate({ ...base, version: '' }), false);
  assert.equal(shouldOfferUpdate(null), false);
  // 用户点过「稍后再说」的版本不再弹，换版本照弹
  assert.equal(shouldOfferUpdate(base, '0.9.2'), false);
  assert.equal(shouldOfferUpdate(base, '0.9.1'), true);
});

test('更新完成提示：首次运行不弹，版本变化才弹', () => {
  assert.equal(shouldAnnounceUpdate('', '0.9.2'), false, '首次运行没有历史版本');
  assert.equal(shouldAnnounceUpdate('0.9.2', '0.9.2'), false);
  assert.equal(shouldAnnounceUpdate('0.9.1', '0.9.2'), true);
  assert.equal(shouldAnnounceUpdate(null, '0.9.2'), false);
  assert.equal(shouldAnnounceUpdate('0.9.1', ''), false);
});
