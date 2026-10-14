import assert from 'node:assert/strict';
import test from 'node:test';

import { languageFromTlPath, toolStatusInfo } from '../renderer/src/agentView.mjs';

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
