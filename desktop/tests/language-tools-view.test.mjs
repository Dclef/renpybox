import assert from 'node:assert/strict';
import test from 'node:test';

import {
  defaultLanguagePathReady,
  fontInjectLanguageReady,
  resolveTargetLanguage,
} from '../renderer/src/languageToolsView.mjs';

test('自定义语言名优先于下拉选择', () => {
  assert.equal(resolveTargetLanguage('chinese', 'schinese'), 'schinese');
  assert.equal(resolveTargetLanguage('chinese', '  '), 'chinese');
  assert.equal(resolveTargetLanguage('', '', 'chinese'), 'chinese');
  assert.equal(resolveTargetLanguage(null, null, 'korean'), 'korean');
});

test('默认语言要求 tl 列表中已有目标语言', () => {
  assert.equal(defaultLanguagePathReady('chinese', ['chinese', 'schinese']), true);
  assert.equal(defaultLanguagePathReady('japanese', ['chinese']), false);
  assert.equal(defaultLanguagePathReady('', ['chinese']), false);
  assert.equal(defaultLanguagePathReady('chinese', null), false);
});

test('字体注入只要非空语言名即可', () => {
  assert.equal(fontInjectLanguageReady('chinese'), true);
  assert.equal(fontInjectLanguageReady('  mylang  '), true);
  assert.equal(fontInjectLanguageReady(''), false);
  assert.equal(fontInjectLanguageReady('   '), false);
});
