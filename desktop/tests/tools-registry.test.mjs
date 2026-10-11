import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { TOOL_REQUIRES_PROJECT } from '../renderer/src/toolRequiresProject.mjs';

const TRANSLATE_KEYS = [
  'rpy_extraction_settings',
  'extract_to_tl',
  'direct_rpy_translate',
  'hook_translate',
  'source_translate',
  'hook_supplement',
  'extract_json',
];

/** tools.ts 含 svg?raw，node:test 无法直接 import TOOL_SPECS，改为读源码核对 registry 字段。 */
const toolsSrc = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), '../renderer/src/tools.ts'),
  'utf8',
);

function registryRequiresProject(key) {
  const match = toolsSrc.match(
    new RegExp(`key:\\s*'${key}'[\\s\\S]*?requiresProject:\\s*(true|false)`),
  );
  assert.ok(match, `TOOL_SPECS 缺少 ${key}`);
  return match[1] === 'true';
}

test('翻译方式 requiresProject 与 Qt ToolRegistry 一致', () => {
  for (const key of TRANSLATE_KEYS) {
    assert.ok(key in TOOL_REQUIRES_PROJECT, `missing ${key}`);
  }
  assert.equal(TOOL_REQUIRES_PROJECT.hook_translate, true);
  assert.equal(TOOL_REQUIRES_PROJECT.source_translate, true);
  assert.equal(TOOL_REQUIRES_PROJECT.hook_supplement, true);
  assert.equal(TOOL_REQUIRES_PROJECT.rpy_extraction_settings, false);
  assert.equal(TOOL_REQUIRES_PROJECT.extract_to_tl, false);
  assert.equal(TOOL_REQUIRES_PROJECT.direct_rpy_translate, false);
  assert.equal(TOOL_REQUIRES_PROJECT.extract_json, false);
});

test('local_glossary.requiresProject === true', () => {
  assert.equal(registryRequiresProject('local_glossary'), true);
});
