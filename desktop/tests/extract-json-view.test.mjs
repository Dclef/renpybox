import assert from 'node:assert/strict';
import test from 'node:test';

import {
  exportJsonReady,
  extractJsonStatusPath,
  extractJsonStatusTone,
  formatPreviewSummary,
  importJsonReady,
  resolveGameFile,
} from '../renderer/src/extractJsonView.mjs';

test('游戏文件回落默认根目录', () => {
  assert.equal(resolveGameFile('', 'C:/Demo'), 'C:/Demo');
  assert.equal(resolveGameFile('  D:/game.exe  ', 'C:/Demo'), 'D:/game.exe');
});

test('JSON statusPath 带手动目标与语言', () => {
  assert.equal(
    extractJsonStatusPath({ gameFile: 'D:/Other/game.exe', language: 'chinese' }),
    '/api/extract-json?language=chinese&game_file=D%3A%2FOther%2Fgame.exe',
  );
  assert.equal(
    extractJsonStatusPath({ gameFile: '', language: 'japanese', defaultRoot: '' }),
    '/api/extract-json?language=japanese',
  );
});

test('JSON 终态色调：部分写入/失败不用绿色', () => {
  assert.equal(
    extractJsonStatusTone({ job: { status: 'done' }, result: { success: true } }),
    'success',
  );
  assert.equal(
    extractJsonStatusTone({ job: { status: 'done' }, result: { success: false, partial: true } }),
    'warning',
  );
  assert.equal(
    extractJsonStatusTone({ job: { status: 'cancelled' }, result: { written: true, partial: true } }),
    'warning',
  );
  assert.equal(
    extractJsonStatusTone({ job: { status: 'failed' }, result: { written: true } }),
    'warning',
  );
});

test('导出/导入就绪预检', () => {
  assert.equal(exportJsonReady({ gameFile: '', outputPath: 'a.json', defaultRoot: 'C:/Demo' }), true);
  assert.equal(exportJsonReady({ gameFile: '', outputPath: '', defaultRoot: 'C:/Demo' }), false);
  assert.equal(importJsonReady({ gameFile: 'C:/Demo', jsonPath: 'a.json' }), true);
  assert.equal(importJsonReady({ gameFile: 'C:/Demo', jsonPath: '' }), false);
});

test('预览摘要占位', () => {
  assert.equal(
    formatPreviewSummary('文件{file_count}/条目{entry_count}', { fileCount: 2, entryCount: 9 }),
    '文件2/条目9',
  );
});
