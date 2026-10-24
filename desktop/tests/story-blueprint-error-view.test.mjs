/**
 * 剧情蓝图错误态的单元测试（不启动 Electron / 不 build）。
 *
 * 事故：桌面端打开剧情蓝图页，显示的是一句英文 `Not Found`。原因是那个 sidecar
 * 进程是旧代码起的，没有 story_blueprint 路由。汉化者不是程序员，看不懂。
 * 这里盯住三条：404 → 中文引导卡；非 404 → 原样报错；readyness 自身失败也一样。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/story-blueprint-error-view.test.mjs
 */
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  BLUEPRINT_API_MISSING_KEYS,
  isBlueprintApiMissing,
  resolveBlueprintErrorView,
} from '../renderer/src/pages/storyBlueprint/storyBlueprintErrorView.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const page = fs.readFileSync(path.join(root, 'renderer/src/pages/StoryBlueprintPage.tsx'), 'utf8');
const zh = fs.readFileSync(path.join(root, 'renderer/src/i18n/zh.ts'), 'utf8');
const en = fs.readFileSync(path.join(root, 'renderer/src/i18n/en.ts'), 'utf8');

/** 仿 ApiError：status + message，与 api.ts 抛出来的形状一致。 */
const apiError = (status, message) => {
  const error = new Error(message);
  error.name = 'ApiError';
  error.status = status;
  return error;
};

/** 从 i18n 表里取出某个键的字面量。 */
function textOf(source, key) {
  const match = source.match(new RegExp(`\\b${key}\\s*:\\s*(['"\`])([\\s\\S]*?)\\1`));
  assert.ok(match, `缺少 i18n 键：${key}`);
  return match[2];
}

test('404 判成接口缺失，不再把英文 Not Found 上屏', () => {
  const view = resolveBlueprintErrorView(apiError(404, 'Not Found'));
  assert.equal(view.kind, 'api_missing');
  // 引导卡走 i18n 键，消息本身必须清空：这是「不要裸显示英文」的硬要求。
  assert.equal(view.titleKey, 'story_blueprint_api_missing_title');
  assert.equal(view.bodyKey, 'story_blueprint_api_missing_body');
  assert.equal(view.message, '');
  assert.equal(isBlueprintApiMissing(apiError(404, 'Not Found')), true);
});

test('只有文案没有状态码时，靠 Not Found / 404 也能认出来', () => {
  for (const message of [
    'Not Found',
    'not found',
    '404 Not Found',
    '请求失败（HTTP 404）',
    '剧情蓝图接口 404',
  ]) {
    assert.equal(isBlueprintApiMissing(new Error(message)), true, message);
    assert.equal(resolveBlueprintErrorView(new Error(message)).kind, 'api_missing', message);
  }
  assert.equal(isBlueprintApiMissing('Not Found'), true);
});

test('非 404 保持原样：后端 detail 与状态码都不被吞掉', () => {
  const cases = [
    [apiError(500, '扫描失败：缺少 .rpy 源码'), '扫描失败：缺少 .rpy 源码'],
    [apiError(409, '引擎正忙'), '引擎正忙'],
    [new Error('Failed to fetch'), 'Failed to fetch'],
    [apiError(422, 'path: field required'), 'path: field required'],
  ];
  for (const [error, expected] of cases) {
    const view = resolveBlueprintErrorView(error);
    assert.equal(view.kind, 'other');
    assert.equal(view.message, expected);
    // 走原 Banner 分支时不应带引导卡文案。
    assert.equal(view.titleKey, null);
    assert.equal(view.bodyKey, null);
  }
});

test('没有错误时不进错误态', () => {
  for (const value of [null, undefined, '', false]) {
    assert.equal(resolveBlueprintErrorView(value), null);
    assert.equal(isBlueprintApiMissing(value), false);
  }
});

test('空消息的其它错误也给一句可读兜底，而不是空 Banner', () => {
  const view = resolveBlueprintErrorView(apiError(500, ''));
  assert.equal(view.kind, 'other');
  assert.ok(view.message.length > 0);
  assert.doesNotMatch(view.message, /Not Found/);
});

test('引导卡文案 zh / en 都有，且中文版是人话不是英文报错', () => {
  for (const key of Object.values(BLUEPRINT_API_MISSING_KEYS)) {
    const zhText = textOf(zh, key);
    const enText = textOf(en, key);
    assert.ok(zhText.length > 0, `zh 缺 ${key}`);
    assert.ok(enText.length > 0, `en 缺 ${key}`);
    assert.doesNotMatch(zhText, /Not Found/i);
    // 中文版必须有汉字，英文版必须没有汉字。
    assert.match(zhText, /[\u4e00-\u9fff]/);
    assert.doesNotMatch(enText, /[\u4e00-\u9fff]/);
  }
  // 中文正文要点出「旧版本 / 重启 / 升级」这三步，否则用户还是不知道做什么。
  const zhBody = textOf(zh, BLUEPRINT_API_MISSING_KEYS.body);
  assert.match(zhBody, /旧版本/);
  assert.match(zhBody, /重新打开|重启/);
  assert.match(zhBody, /升级/);
});

test('页面把错误交给可测的判定函数，并保留重试按钮', () => {
  assert.match(page, /resolveBlueprintErrorView\(error\)/);
  // 404 分支用 i18n 键渲染引导卡，而不是拼字符串。
  assert.match(page, /errorView\.kind === 'api_missing'[\s\S]{0,400}?t\(errorView\.titleKey\)/);
  assert.match(page, /errorView\.kind === 'api_missing'[\s\S]{0,400}?t\(errorView\.bodyKey\)/);
  // 两个分支都留着重试入口。
  assert.match(page, /story_blueprint_retry/);
  // readiness 与 snapshot 共用同一段 try/catch：任何一个失败都进错误态。
  assert.match(page, /getStoryBlueprintReadiness\(\)[\s\S]{0,600}?catch/);
  assert.doesNotMatch(page, /<Banner tone="warning">\{error\}<\/Banner>/);
});
