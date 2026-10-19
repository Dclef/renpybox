import assert from 'node:assert/strict';
import test from 'node:test';

import { budgetParts, formatTokenCount, languageFromTlPath, metricsParts, selectableAgentPlatforms, stageKey, toolStatusInfo } from '../renderer/src/agentView.mjs';

test('工具卡片按状态与错误码区分取消、超时和失败', () => {
  assert.deepEqual(toolStatusInfo({ status: 'running' }), { label: '执行中', tone: 'running' });
  assert.deepEqual(toolStatusInfo({ status: 'done' }), { label: '已完成', tone: 'done' });
  assert.deepEqual(toolStatusInfo({ status: 'cancelled' }), { label: '已取消', tone: 'cancelled' });
  assert.deepEqual(toolStatusInfo({ status: 'failed', code: 'USER_CANCELLED' }), { label: '已取消', tone: 'cancelled' });
  assert.deepEqual(toolStatusInfo({ status: 'failed', code: 'CONFIRMATION_TIMEOUT' }), { label: '确认超时', tone: 'cancelled' });
  assert.deepEqual(toolStatusInfo({ status: 'failed', code: 'CONFIRMATION_STALE' }), { label: '项目已变化', tone: 'cancelled' });
  assert.deepEqual(toolStatusInfo({ status: 'failed', code: 'RPA_UNPACK_FAILED' }), { label: '失败', tone: 'failed' });
});

test('项目胶囊语言取 tl/<语言> 目录名', () => {
  assert.equal(languageFromTlPath('C:\\Games\\Demo\\game\\tl\\chinese'), 'chinese');
  assert.equal(languageFromTlPath('C:/Games/Demo/game/TL/schinese/sub'), 'schinese');
  assert.equal(languageFromTlPath('C:/Games/Demo/game/tl'), '');
  assert.equal(languageFromTlPath(''), '');
});

test('Agent 接口下拉排除不能调用工具的机翻格式', () => {
  const platforms = [
    { id: 1, api_format: 'OpenAI' },
    { id: 2, api_format: 'anthropic' },
    { id: 3, api_format: 'GoogleFree' },
    { id: 4, api_format: 'Bing' },
    { id: 5, api_format: 'SakuraLLM' },
    { id: 6 },
  ];
  assert.deepEqual(selectableAgentPlatforms(platforms).map((item) => item.id), [1, 2]);
  assert.deepEqual(selectableAgentPlatforms(null), []);
  assert.deepEqual(selectableAgentPlatforms(undefined), []);
});

test('阶段名映射到 i18n key，未知和空阶段不展示', () => {
  assert.equal(stageKey('detect'), 'agent_page_stage_detect');
  assert.equal(stageKey('translate'), 'agent_page_stage_translate');
  assert.equal(stageKey('done'), 'agent_page_stage_done');
  assert.equal(stageKey(''), '');
  assert.equal(stageKey(undefined), '');
  assert.equal(stageKey('mystery'), '');
});

test('token 数量按 K/M 压缩，0 和非法值为空', () => {
  assert.equal(formatTokenCount(200000), '200K');
  assert.equal(formatTokenCount(1000000), '1M');
  assert.equal(formatTokenCount(1500), '1.5K');
  assert.equal(formatTokenCount(0), '');
  assert.equal(formatTokenCount(undefined), '');
  assert.equal(formatTokenCount(Number.NaN), '');
  assert.equal(formatTokenCount(-1), '');
});

test('预算行只取上下文窗口和最大轮数', () => {
  assert.deepEqual(budgetParts({ context_window: 200000, max_iterations: 32 }), { context: '200K', iterations: '32' });
  assert.deepEqual(budgetParts({ context_window: 1500 }), { context: '1.5K', iterations: '' });
  assert.deepEqual(budgetParts({}), { context: '', iterations: '' });
  assert.deepEqual(budgetParts(undefined), { context: '', iterations: '' });
  assert.deepEqual(budgetParts({ context_window: 0, max_iterations: 0 }), { context: '', iterations: '' });
});

test('状态栏把轮次、步数、吞吐、token、缓存命中与上下文占比分开给出', () => {
  const parts = metricsParts({
    iterations: 25,
    steps: 2145,
    tokens_per_second: 221.4,
    total_tokens: 227_000_000,
    cache_hit_rate: 0.98,
    context_percent: 0.12,
  });

  assert.equal(parts.rounds, 25);
  assert.equal(parts.steps, 2145);
  assert.equal(parts.tokensPerSecond, 221.4);
  assert.equal(parts.totalTokens, '227M');
  assert.equal(parts.cacheHitPercent, 98);
  assert.equal(parts.contextPercent, 12);
  assert.equal(parts.hasData, true);
});

test('没有步数时只报轮次，缓存命中缺失时返回 null 而不是 0', () => {
  const parts = metricsParts({ iterations: 3, cache_hit_rate: null, context_percent: 0 });

  assert.equal(parts.rounds, 3);
  assert.equal(parts.steps, 0);
  assert.equal(parts.cacheHitPercent, null);
  assert.equal(parts.contextPercent, 0);
  assert.equal(parts.hasData, true);
});

test('空 metrics 不触发状态栏，避免显示 0 轮 0 步', () => {
  for (const value of [undefined, null, {}, 'x']) {
    const parts = metricsParts(value);
    assert.equal(parts.hasData, false);
    assert.equal(parts.rounds, 0);
    assert.equal(parts.cacheHitPercent, null);
  }
});

test('缓存命中率被夹在 0 到 1 之间', () => {
  assert.equal(metricsParts({ iterations: 1, cache_hit_rate: 1.5 }).cacheHitPercent, 100);
  assert.equal(metricsParts({ iterations: 1, cache_hit_rate: -0.2 }).cacheHitPercent, 0);
});

