import assert from 'node:assert/strict';
import test from 'node:test';

import { resolveGraphBlocked, scanBlockedHint } from '../renderer/src/pages/workbench/graphBlocked.mjs';

const ready = (patch) => ({ stage: 'ready', rpy_files: 74, rpa_files: 6, ...patch });

test('体检结果还没回来也要给出扫描入口', () => {
  for (const value of [null, undefined, {}, { stage: '' }, { stage: 42 }]) {
    const card = resolveGraphBlocked(value);
    assert.equal(card.stage, 'unknown');
    assert.equal(card.action, 'scan');
    assert.match(card.detail, /扫描/);
  }
});

test('未绑定 / 没有 game 目录：去绑定工程', () => {
  for (const stage of ['unbound', 'no_game']) {
    const card = resolveGraphBlocked({ stage });
    assert.equal(card.stage, stage);
    assert.equal(card.action, 'bind');
    assert.equal(card.actionLabel, '去绑定工程');
  }
});

test('只有 .rpa 没解包：去解包，并报出包数量', () => {
  const card = resolveGraphBlocked({ stage: 'packed', rpy_files: 0, rpa_files: 6 });
  assert.equal(card.action, 'unpack');
  assert.equal(card.actionLabel, '去解包');
  assert.match(card.detail, /6 个 .rpa/);
});

test('既没 rpy 也没 rpa：仍然让人回去重选目录', () => {
  const card = resolveGraphBlocked({ stage: 'no_script', rpy_files: 0, rpa_files: 0 });
  assert.equal(card.action, 'bind');
  assert.equal(card.actionLabel, '重新选目录');
});

test('工程就绪但没扫过：直接扫，并说清不需要世界观和翻译', () => {
  const card = resolveGraphBlocked(ready());
  assert.equal(card.stage, 'ready');
  assert.equal(card.action, 'scan');
  assert.equal(card.actionLabel, '扫描角色');
  assert.match(card.detail, /74 个脚本/);
  // 关系图谱是纯规则挖掘，这两句是它的真实前提，必须写进文案里。
  assert.match(card.detail, /不需要先翻译/);
  assert.match(card.detail, /不用先生成世界观/);
});

test('rpa/rpy 计数缺失时按 0 处理，不出现 NaN', () => {
  assert.doesNotMatch(resolveGraphBlocked({ stage: 'packed' }).detail, /NaN/);
  assert.doesNotMatch(resolveGraphBlocked({ stage: 'ready' }).detail, /NaN/);
  assert.doesNotMatch(resolveGraphBlocked({ stage: 'packed', rpa_files: 'x' }).detail, /NaN/);
});

test('扫描可用时没有提示，不可用时才解释按钮为什么灰', () => {
  assert.equal(scanBlockedHint(true), '');
  assert.match(scanBlockedHint(false), /引擎正忙/);
});
