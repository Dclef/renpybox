import assert from 'node:assert/strict';
import test from 'node:test';

import {
  defaultSourceFileOutputDir,
  defaultSourceOutputDir,
  decodeLangChoice,
  encodeLangChoice,
  normalizePath,
  sourceResumeView,
  toolboxOwnerKey,
  toolboxProjectRootFromGamePath,
  toolboxStartGate,
  toolboxTargetKeyFromGamePath,
  toolboxTlLanguageName,
  TOOLBOX_TRANSLATE_MODES,
  validateSourceLayout,
} from '../renderer/src/toolboxTranslateView.mjs';

test('目录模式默认输出为 input.parent / name_source_out', () => {
  assert.equal(
    defaultSourceOutputDir('E:\\games\\Demo\\game'),
    'E:\\games\\Demo\\game_source_out',
  );
  assert.equal(
    defaultSourceOutputDir('E:/games/Demo/game/'),
    'E:\\games\\Demo\\game_source_out',
  );
  assert.equal(defaultSourceOutputDir(''), '');
  assert.equal(defaultSourceOutputDir(null), '');
});

test('单文件模式默认输出为同目录/<stem>_source_out', () => {
  assert.equal(
    defaultSourceFileOutputDir('E:\\games\\Demo\\game\\story.rpy'),
    'E:\\games\\Demo\\game\\story_source_out',
  );
  assert.equal(
    defaultSourceFileOutputDir('E:/games/Demo/game/intro.rpy'),
    'E:\\games\\Demo\\game\\intro_source_out',
  );
  assert.equal(defaultSourceFileOutputDir(''), '');
  assert.equal(defaultSourceFileOutputDir('story.rpy'), '');
});

test('源码路径校验仍拒绝输入输出重叠', () => {
  const game = 'E:\\games\\Demo\\game';
  const out = defaultSourceOutputDir(game);
  assert.equal(normalizePath(out), 'E:\\games\\Demo\\game_source_out');
  assert.equal(validateSourceLayout(game, out).ok, true);
  assert.equal(validateSourceLayout(game, game).ok, false);
});

test('工具箱 mode 白名单含 supplement，不含 hook', () => {
  assert.deepEqual([...TOOLBOX_TRANSLATE_MODES], ['direct', 'source', 'supplement']);
});

test('语言选择编码/解码繁体标志', () => {
  assert.equal(encodeLangChoice('ZH', true), 'ZH:trad');
  assert.deepEqual(decodeLangChoice('ZH:trad'), { code: 'ZH', traditional: true });
  assert.deepEqual(decodeLangChoice('EN'), { code: 'EN', traditional: false });
});

test('direct 可不绑定项目，有 gamePath 即可启动预检通过', () => {
  const gate = toolboxStartGate({
    mode: 'direct',
    hasProject: false,
    linkOpen: true,
    engineBusy: false,
    gamePath: 'E:\\games\\Demo\\game.exe',
  });
  assert.equal(gate.canStart, true);
});

test('source 手动输出不被默认逻辑要求（仅校验路径）', () => {
  const gate = toolboxStartGate({
    mode: 'source',
    hasProject: false,
    linkOpen: true,
    engineBusy: false,
    inputFolder: 'E:\\games\\Demo\\game',
    outputFolder: 'E:\\games\\Demo\\custom_out',
  });
  assert.equal(gate.canStart, true);
});

test('owner key / tl 语言名辅助', () => {
  assert.equal(toolboxOwnerKey('E:\\games\\Demo', 'Chinese'), 'e:\\games\\demo|chinese');
  assert.equal(toolboxTlLanguageName('E:\\games\\Demo\\game\\tl\\japanese'), 'japanese');
  assert.equal(toolboxOwnerKey('', 'chinese'), '');
});

test('gamePath 规范化与后端 from_path 项目根对齐', () => {
  assert.equal(toolboxProjectRootFromGamePath('C:/Demo/game.exe'), 'C:\\Demo');
  assert.equal(toolboxProjectRootFromGamePath('C:\\Demo\\game.exe'), 'C:\\Demo');
  assert.equal(toolboxProjectRootFromGamePath('C:/Demo/game'), 'C:\\Demo');
  assert.equal(toolboxProjectRootFromGamePath('C:/Demo'), 'C:\\Demo');
  assert.equal(
    toolboxProjectRootFromGamePath('C:/Demo/game/tl/chinese'),
    'C:\\Demo',
  );
  assert.equal(
    toolboxTargetKeyFromGamePath('C:/late-persist-B/game.exe', 'chinese'),
    'c:\\late-persist-b|chinese',
  );
  assert.equal(
    toolboxTargetKeyFromGamePath('C:/late-persist-B', 'chinese'),
    'c:\\late-persist-b|chinese',
  );
  // 不得把任意无关路径当成可放行 target：仅规范根，不放宽匹配。
  assert.notEqual(
    toolboxTargetKeyFromGamePath('C:/late-persist-B/game.exe', 'chinese'),
    toolboxTargetKeyFromGamePath('C:/external-C', 'chinese'),
  );
  assert.equal(toolboxProjectRootFromGamePath(''), '');
});

test('sourceResumeView：无可续跑缓存时只能重新开始', () => {
  const view = sourceResumeView(null);
  assert.equal(view.canContinue, false);
  assert.equal(view.hint, '');
  assert.equal(sourceResumeView({ resumable: false, line: 3, total_line: 9 }).canContinue, false);
  assert.equal(sourceResumeView({}).canContinue, false);
});

test('sourceResumeView：有可续跑缓存时给出继续状态与进度', () => {
  const view = sourceResumeView({ resumable: true, line: 3, total_line: 9 });
  assert.equal(view.canContinue, true);
  assert.equal(view.percent, 33);
  assert.equal(view.line, 3);
  assert.equal(view.total, 9);
  assert.match(view.hint, /3\/9/);
});

test('sourceResumeView：行数缺失时仍可继续，不显示假进度', () => {
  const view = sourceResumeView({ resumable: true, line: 0, total_line: 0 });
  assert.equal(view.canContinue, true);
  assert.equal(view.percent, 0);
  assert.match(view.hint, /可继续翻译/);
  assert.doesNotMatch(view.hint, /0\/0/);
});
