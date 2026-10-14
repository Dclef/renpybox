import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { TOOL_REQUIRES_PROJECT } from '../renderer/src/toolRequiresProject.mjs';

/**
 * 2026-10-12 用户决策（只改新 UI）：
 * 门禁：推荐流程中的项目动作 + 术语表 / 禁翻表。
 * 一键翻译是选游戏目录入口，须保持 requiresProject=false；翻译方式工具一律可无项目打开。
 * Qt5 ToolRegistry 仍保留 11 个 requires_project=True，这是有意的偏差。
 */
const GATED_KEYS = [
  'continue_translation',
  'proofreading',
  'apply_translation',
  'font_replace',
  'add_language',
  'set_default_language',
  'local_glossary',
  'text_preserve',
];

const TRANSLATE_KEYS = [
  'rpy_extraction_settings',
  'extract_to_tl',
  'direct_rpy_translate',
  'hook_translate',
  'source_translate',
  'hook_supplement',
  'extract_json',
];

/** tools.ts 含 svg?raw，node:test 无法直接 import TOOL_SPECS，改为逐条读源码核对 registry 字段。 */
const toolsSrc = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../renderer/src/tools.ts'),
  'utf8',
);

/** 按 key: 'xxx' 切分每条 TOOL_SPECS 记录，读出该条的 group 与 requiresProject 结果。 */
function registryEntries() {
  const starts = [...toolsSrc.matchAll(/key:\s*'([a-z_]+)'/g)].map((match) => ({
    key: match[1],
    at: match.index,
  }));
  const entries = new Map();
  starts.forEach((entry, index) => {
    const slice = toolsSrc.slice(entry.at, index + 1 < starts.length ? starts[index + 1].at : toolsSrc.length);
    const literal = slice.match(/requiresProject:\s*(true|false)/);
    const indirect = slice.match(/requiresProject:\s*TOOL_REQUIRES_PROJECT\.([a-z_]+)/);
    const group = slice.match(/group:\s*'([a-z]+)'/);
    assert.ok(group, `TOOL_SPECS 缺少 ${entry.key} 的 group`);
    if (literal) {
      entries.set(entry.key, { group: group[1], requiresProject: literal[1] === 'true' });
    } else if (indirect) {
      entries.set(entry.key, { group: group[1], requiresProject: TOOL_REQUIRES_PROJECT[indirect[1]] === true });
    } else {
      assert.fail(`TOOL_SPECS 缺少 ${entry.key} 的 requiresProject`);
    }
  });
  return entries;
}

test('registryEntries 读到全部 27 个工具', () => {
  assert.equal(registryEntries().size, 27);
});

test('门禁工具仅为推荐流程项目动作 + 术语表 / 禁翻表', () => {
  const gated = [...registryEntries().entries()]
    .filter(([, entry]) => entry.requiresProject)
    .map(([key]) => key)
    .sort();
  assert.deepEqual(gated, [...GATED_KEYS].sort());
});

test('带门禁的工具全部落在推荐流程分组', () => {
  for (const [key, entry] of registryEntries()) {
    if (entry.requiresProject) assert.equal(entry.group, 'flow', `${key} 带门禁但不在推荐流程`);
  }
  const flowKeys = [...registryEntries().entries()]
    .filter(([, entry]) => entry.group === 'flow')
    .map(([key]) => key);
  assert.deepEqual(flowKeys, [
    'continue_translation',
    'one_key_translate',
    'proofreading',
    'apply_translation',
    'font_replace',
    'add_language',
    'set_default_language',
    'local_glossary',
    'text_preserve',
  ]);
});

test('一键翻译保持为选项目入口（无门禁）', () => {
  const entry = registryEntries().get('one_key_translate');
  assert.ok(entry, 'missing one_key_translate');
  assert.equal(entry.group, 'flow');
  assert.equal(entry.requiresProject, false);
});

test('翻译方式 requiresProject 一律为 false（新 UI 有意与 Qt5 不同）', () => {
  for (const key of TRANSLATE_KEYS) {
    assert.ok(key in TOOL_REQUIRES_PROJECT, `missing ${key}`);
    assert.equal(TOOL_REQUIRES_PROJECT[key], false, key);
    assert.equal(registryEntries().get(key)?.requiresProject, false, key);
  }
});
