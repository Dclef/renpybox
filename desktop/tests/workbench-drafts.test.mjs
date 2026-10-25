import assert from 'node:assert/strict';
import test from 'node:test';

import { countInferablePairs, resolveAiAction, resolveDraftNotice } from '../renderer/src/pages/workbench/workbenchDrafts.mjs';

test('草稿为 0 时横幅不得再说「请审核后应用 N 张」', () => {
  for (const input of [
    { characters: 0, worldbook: 0 },
    { characters: 0, worldbook: 0, generatedCharacters: 2 },
    { characters: null, worldbook: undefined },
    {},
    undefined,
  ]) {
    const notice = resolveDraftNotice(input);
    assert.doesNotMatch(notice.message, /请审核后应用/, `仍然矛盾：${notice.message}`);
    assert.doesNotMatch(notice.message, /0 张/, `出现 0 张：${notice.message}`);
  }
});

test('刚扫出 2 张又应用掉：横幅改口说已应用，且不再要求审核', () => {
  const notice = resolveDraftNotice({ characters: 0, worldbook: 0, generatedCharacters: 2 });
  assert.equal(notice.visible, true);
  assert.equal(notice.tone, 'applied');
  assert.match(notice.message, /已全部应用到正式资料/);
  assert.doesNotMatch(notice.message, /请审核后应用/);
});

test('没有草稿也没有扫描记录：横幅直接收起', () => {
  const notice = resolveDraftNotice({ characters: 0, worldbook: 0 });
  assert.equal(notice.visible, false);
  assert.equal(notice.tone, 'none');
  assert.equal(notice.message, '');
});

test('草稿 > 0 时横幅按实时快照报数并提示审核', () => {
  const onlyCharacters = resolveDraftNotice({ characters: 2, worldbook: 0, generatedCharacters: 2 });
  assert.equal(onlyCharacters.visible, true);
  assert.equal(onlyCharacters.tone, 'pending');
  assert.match(onlyCharacters.message, /角色草稿 2 张/);
  assert.match(onlyCharacters.message, /请审核后应用/);
  // 世界观为 0 时不该出现「世界观草稿 0 项」这种废话。
  assert.doesNotMatch(onlyCharacters.message, /世界观草稿/);

  const both = resolveDraftNotice({ characters: 3, worldbook: 5 });
  assert.match(both.message, /世界观草稿 5 项/);
  assert.match(both.message, /角色草稿 3 张/);
});

test('计数是脏数据时按 0 处理，不出现 NaN / 负数', () => {
  const notice = resolveDraftNotice({ characters: 'x', worldbook: -3, generatedCharacters: NaN });
  assert.equal(notice.visible, false);
  assert.doesNotMatch(notice.message, /NaN/);
  const parsed = resolveDraftNotice({ characters: '2' });
  assert.match(parsed.message, /角色草稿 2 张/);
});

test('清洗按钮：无草稿时置灰，并在按钮旁给出可见原因', () => {
  const state = resolveAiAction({ mode: 'clean', count: 0 });
  assert.equal(state.blocked, true);
  assert.equal(state.label, 'AI 清洗角色');
  assert.match(state.hint, /没有待清洗的角色草稿/);
  assert.match(state.hint, /重新分析后会出现/);
});

test('复核按钮：无规则边时置灰，并指向手动补一条', () => {
  const state = resolveAiAction({ mode: 'review', count: 0 });
  assert.equal(state.blocked, true);
  assert.equal(state.label, 'AI 复核关系');
  assert.match(state.hint, /规则还没挖到关系证据/);
  assert.match(state.hint, /可在角色卡手动补一条/);
});

test('草稿 > 0 时按钮文案恢复「AI 清洗角色 · N」且可点', () => {
  const state = resolveAiAction({ mode: 'clean', count: 2 });
  assert.equal(state.blocked, false);
  assert.equal(state.label, 'AI 清洗角色 · 2');
  assert.equal(state.hint, '');
});

test('规则边 > 0 时按钮文案恢复「AI 复核关系 · N」且可点', () => {
  const state = resolveAiAction({ mode: 'review', count: 66 });
  assert.equal(state.blocked, false);
  assert.equal(state.label, 'AI 复核关系 · 66');
  assert.equal(state.hint, '');
});

test('有对象但被占用：仍然置灰，原因不是「没有草稿」', () => {
  const reviewing = resolveAiAction({ mode: 'clean', count: 2, reviewing: true });
  assert.equal(reviewing.blocked, true);
  assert.match(reviewing.hint, /模型正在处理/);
  assert.doesNotMatch(reviewing.hint, /没有待清洗/);

  const busy = resolveAiAction({ mode: 'review', count: 4, disabled: true });
  assert.equal(busy.blocked, true);
  assert.match(busy.hint, /未保存的改动或任务正忙/);
  assert.doesNotMatch(busy.hint, /关系证据/);
  // 兜底原因和数量文案不冲突：按钮上依然写着要处理几条。
  assert.equal(busy.label, 'AI 复核关系 · 4');
});

test('未知 mode 一律按清洗处理，脏计数不产生 NaN 文案', () => {
  const state = resolveAiAction({ mode: 'nope', count: 'x' });
  assert.equal(state.mode, 'clean');
  assert.equal(state.count, 0);
  assert.doesNotMatch(state.hint, /NaN/);
  assert.doesNotMatch(resolveAiAction(undefined).label, /NaN/);
});

test('推断按钮：无同场共现时置灰，并指向先扫描', () => {
  const state = resolveAiAction({ mode: 'infer', count: 0 });
  assert.equal(state.blocked, true);
  assert.equal(state.mode, 'infer');
  assert.equal(state.label, 'AI 推断关系');
  assert.match(state.hint, /没有同场记录/);
  assert.doesNotMatch(state.hint, /规则还没挖到/);
});

test('推断按钮：有可推断对时带「对」计数且可点', () => {
  const state = resolveAiAction({ mode: 'infer', count: 1 });
  assert.equal(state.blocked, false);
  assert.equal(state.label, 'AI 推断关系 · 1 对');
  assert.equal(state.hint, '');
});

test('可推断角色对：同场共现两侧各存一次，按无向对只算一对', () => {
  const characters = [
    { name: 'Sayaka', co_occurrence: { You: 66 }, relations: [] },
    { name: 'You', co_occurrence: { Sayaka: 66 }, relations: [] },
  ];
  assert.equal(countInferablePairs(characters), 1);
});

test('可推断角色对：人工/否决边挡路的对不算，未知角色与脏数据不算', () => {
  const characters = [
    { name: 'Sayaka', co_occurrence: { You: 66, Mika: 5, Nobody: 9 }, relations: [] },
    {
      name: 'You',
      co_occurrence: { Sayaka: 66 },
      relations: [{ target: 'Sayaka', source: 'manual', relation: '邻居' }],
    },
    { name: 'Mika', co_occurrence: { Sayaka: 5 }, relations: [] },
  ];
  // Sayaka/You 被人工边挡住；Sayaka/Mika 两侧都有记录，只算一对；Nobody 不在名册里。
  assert.equal(countInferablePairs(characters), 1);

  assert.equal(countInferablePairs([]), 0);
  assert.equal(countInferablePairs(undefined), 0);
  assert.equal(
    countInferablePairs([{ name: 'A', co_occurrence: { B: 'x' } }, { name: 'B', co_occurrence: {} }]),
    0,
  );
});

test('可推断角色对：已有 ai 边仍然算，允许用新资料重算', () => {
  const characters = [
    {
      name: 'Sayaka',
      co_occurrence: { You: 66 },
      relations: [{ target: 'You', source: 'ai', relation: '恋人' }],
    },
    { name: 'You', co_occurrence: { Sayaka: 66 }, relations: [{ target: 'Sayaka', source: 'ai', relation: '恋人' }] },
  ];
  assert.equal(countInferablePairs(characters), 1);
});
