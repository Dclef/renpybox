/**
 * 接口管理「从旧版导入」入口的静态契约（不启动 Electron / 不 build）。
 *
 * 背景：桌面版把配置放在 %APPDATA%\RenpyBox（旧版为 RenpyBox-newUI），Python / Qt5 版放在程序目录，
 * 升级后接口列表是空的，看起来像数据丢了。空状态必须给出「新增接口 / 从旧版导入」
 * 两个入口，且导入只能走后端 /api/platforms/import。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/platform-import-view.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const page = fs.readFileSync(path.join(root, 'renderer/src/pages/PlatformPage.tsx'), 'utf8');
const zh = fs.readFileSync(path.join(root, 'renderer/src/i18n/zh.ts'), 'utf8');
const en = fs.readFileSync(path.join(root, 'renderer/src/i18n/en.ts'), 'utf8');

/** 从 i18n 表里取出某个键的字面量，用于断言文案存在。 */
function textOf(source, key) {
  const match = source.match(new RegExp(`\\b${key}\\s*:\\s*(['"\`])([\\s\\S]*?)\\1`));
  assert.ok(match, `缺少 i18n 键：${key}`);
  return match[2];
}

test('空接口状态提供新增与导入两个入口', () => {
  assert.match(page, /platform_empty_title/);
  assert.match(page, /platform_empty_content/);
  assert.match(page, /platform_empty_search/);
  // 空状态里的两个按钮：新增接口 / 从旧版导入
  assert.match(page, /rb-empty-actions[\s\S]{0,600}?platform_add[\s\S]{0,400}?platform_import/);
});

test('「新增接口」菜单里也能进入导入', () => {
  assert.match(page, /key: 'import'[\s\S]{0,200}?platform_import/);
});

test('导入只提交路径，由后端读文件', () => {
  // 渲染层拿不到旧版文件内容，必须让 sidecar 去读
  assert.match(page, /'\/api\/platforms\/import'/);
  assert.match(page, /JSON\.stringify\(\{\s*path:/);
  // 不能把文件内容塞进请求体
  assert.doesNotMatch(page, /platforms\/import'[\s\S]{0,200}?content:/);
});

test('文件选择走 Electron 原生对话框', () => {
  assert.match(page, /window\.renpy\?\.pickFile\?\.\(/);
  assert.match(page, /extensions:\s*\['json'\]/);
});

test('导入结果分别提示新增与重复', () => {
  assert.match(page, /platform_import_done[\s\S]{0,200}?\{added\}/);
  assert.match(page, /platform_import_none[\s\S]{0,200}?\{skipped\}/);
});

test('中英文案同时存在且占位符一致', () => {
  const keys = [
    'platform_import',
    'platform_import_title',
    'platform_import_description',
    'platform_import_confirm',
    'platform_import_running',
    'platform_import_missing',
    'platform_import_pick',
    'platform_import_done',
    'platform_import_none',
    'platform_import_hint',
    'platform_empty_title',
    'platform_empty_content',
    'platform_empty_search',
  ];
  for (const key of keys) {
    const zhText = textOf(zh, key);
    const enText = textOf(en, key);
    assert.ok(zhText.length > 0, `${key} 中文文案为空`);
    assert.ok(enText.length > 0, `${key} 英文文案为空`);
    const placeholders = (value) => (value.match(/\{[a-z_]+\}/g) ?? []).sort();
    assert.deepEqual(placeholders(zhText), placeholders(enText), `${key} 占位符不一致`);
  }
});

test('导入对话框说明密钥会自动沿用', () => {
  const zhText = textOf(zh, 'platform_import_description');
  assert.match(zhText, /密钥/);
  const enText = textOf(en, 'platform_import_description');
  assert.match(enText, /Credential Manager/i);
});

test('空状态文案指向导入而不是让用户以为数据丢了', () => {
  assert.match(textOf(zh, 'platform_empty_content'), /从旧版导入/);
  assert.match(textOf(en, 'platform_empty_content'), /Import from older version/i);
});

test('导入入口在引擎忙碌时禁用', () => {
  // disabled 汇总了任务执行状态，导入按钮必须复用同一开关
  assert.match(page, /const disabled =[\s\S]{0,300}?state\.translation\.single_tasks/);
  // 空状态里的导入按钮受同一开关约束
  assert.match(page, /<Button icon=\{<Import[\s\S]{0,120}?disabled=\{disabled\}/);
});
