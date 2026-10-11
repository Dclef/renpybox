import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FONT_BROWSE_LABEL,
  FONT_DEFAULT_LANGUAGE_LABEL,
  FONT_DEFAULT_LANGUAGE_VALUE,
  FONT_SCAN_NO_REFS_LABEL,
  FONT_SCAN_STALE_LABEL,
  FONT_GAME_DIR_EMPTY_LABEL,
  fontCopy,
  fontDetectedPlaceholder,
  fontGameDirReady,
  fontToolsGamePathPayload,
  fontToolsStatusPath,
  fontWriteNeedsRescan,
  formatFontBackupSideEffect,
  formatFontRestoreHint,
  formatFontScanSummary,
  replaceFontsReady,
  resolveFontInjectLanguage,
  resolveOriginalFonts,
} from '../renderer/src/fontReplaceView.mjs';

test('替换全部时使用检测列表', () => {
  assert.deepEqual(
    resolveOriginalFonts({
      replaceAll: true,
      selectedFont: 'a.ttf',
      originalFont: 'b.ttf',
      detected: ['a.ttf', 'c.otf'],
    }),
    ['a.ttf', 'c.otf'],
  );
});

test('手输原字体优先于检测选中', () => {
  assert.deepEqual(
    resolveOriginalFonts({
      replaceAll: false,
      selectedFont: 'a.ttf',
      originalFont: ' manual.ttf ',
      detected: ['a.ttf'],
    }),
    ['manual.ttf'],
  );
});

test('检测选中在未手输且未全部时生效', () => {
  assert.deepEqual(
    resolveOriginalFonts({
      replaceAll: false,
      selectedFont: 'gui/DejaVu.ttf',
      originalFont: '',
      detected: ['gui/DejaVu.ttf'],
    }),
    ['gui/DejaVu.ttf'],
  );
  assert.equal(
    replaceFontsReady({
      replaceAll: false,
      selectedFont: '',
      originalFont: '',
      detected: ['a.ttf'],
    }),
    false,
  );
});

test('扫描摘要区分引用与文件数量占位', () => {
  assert.equal(
    formatFontScanSummary('引用{font_count}/文件{font_file_count}/语言{lang_count}', {
      fontCount: 2,
      fontFileCount: 5,
      langCount: 3,
    }),
    '引用2/文件5/语言3',
  );
});

test('默认语言选项回落 chinese（对齐 Qt None→chinese）', () => {
  assert.equal(resolveFontInjectLanguage(FONT_DEFAULT_LANGUAGE_VALUE, '', 'chinese'), 'chinese');
  assert.equal(resolveFontInjectLanguage('', '', 'chinese'), 'chinese');
  assert.equal(resolveFontInjectLanguage('schinese', '', 'chinese'), 'schinese');
  assert.equal(resolveFontInjectLanguage(FONT_DEFAULT_LANGUAGE_VALUE, 'korean', 'chinese'), 'korean');
  assert.equal(fontCopy(FONT_DEFAULT_LANGUAGE_LABEL, 'ZH'), '默认语言 (全局替换)');
  assert.equal(fontCopy(FONT_DEFAULT_LANGUAGE_LABEL, 'EN'), 'Default Language (Global Replacement)');
  assert.equal(fontCopy(FONT_BROWSE_LABEL, 'EN'), 'Browse');
});

test('字体 statusPath / game_path 载荷：空输入显式空，绑定目录省略，手动目标带 query', () => {
  assert.equal(fontGameDirReady(''), false);
  assert.equal(fontGameDirReady('  '), false);
  assert.equal(fontGameDirReady('C:/game'), true);
  assert.equal(fontToolsStatusPath(''), '/api/font-tools?game_path=');
  assert.equal(
    fontToolsStatusPath('C:/other/game'),
    '/api/font-tools?game_path=C%3A%2Fother%2Fgame',
  );
  // 空输入必须显式带 game_path:''，禁止依赖省略回退 bound
  assert.deepEqual(fontToolsGamePathPayload('', 'C:/bound/game'), { game_path: '' });
  assert.deepEqual(fontToolsGamePathPayload('C:/bound/game', 'C:/bound/game'), {});
  assert.deepEqual(
    fontToolsGamePathPayload('C:/other/game', 'C:/bound/game'),
    { game_path: 'C:/other/game' },
  );
  assert.equal(fontCopy(FONT_GAME_DIR_EMPTY_LABEL, 'ZH'), '请先选择游戏目录');
  assert.equal(fontCopy(FONT_GAME_DIR_EMPTY_LABEL, 'EN'), 'Select the game folder first.');
});

test('无引用扫描占位区别于尚未扫描', () => {
  assert.equal(
    fontDetectedPlaceholder(
      { fontsScanned: false, scanStale: false, fontRefCount: 0 },
      { noRefs: fontCopy(FONT_SCAN_NO_REFS_LABEL, 'ZH'), notScanned: '尚未扫描或未检测到引用' },
    ),
    '尚未扫描或未检测到引用',
  );
  assert.equal(
    fontDetectedPlaceholder(
      { fontsScanned: true, scanStale: false, fontRefCount: 0 },
      { noRefs: fontCopy(FONT_SCAN_NO_REFS_LABEL, 'ZH'), notScanned: '尚未扫描或未检测到引用' },
    ),
    '扫描完成，未检测到字体引用',
  );
  assert.equal(
    fontDetectedPlaceholder(
      { fontsScanned: true, scanStale: false, fontRefCount: 2 },
      { noRefs: fontCopy(FONT_SCAN_NO_REFS_LABEL, 'ZH'), notScanned: '尚未扫描或未检测到引用' },
    ),
    undefined,
  );
  // scan-zero 不得在 EN 下误报未扫描
  assert.equal(
    fontDetectedPlaceholder(
      { fontsScanned: true, scanStale: false, fontRefCount: 0 },
      { noRefs: fontCopy(FONT_SCAN_NO_REFS_LABEL, 'EN'), notScanned: 'Not scanned yet' },
    ),
    'Scan complete: no font references detected',
  );
});

test('写入终态需重扫：done/failed + written 的 inject/replace', () => {
  assert.equal(
    fontWriteNeedsRescan({ status: 'done' }, { written: true, action: 'replace' }),
    true,
  );
  assert.equal(
    fontWriteNeedsRescan({ status: 'failed' }, { written: true, action: 'inject', partial: true }),
    true,
  );
  assert.equal(
    fontWriteNeedsRescan({ status: 'done' }, { written: false, action: 'replace' }),
    false,
  );
  assert.equal(
    fontWriteNeedsRescan({ status: 'failed' }, { written: false, action: 'replace' }),
    false,
  );
  assert.equal(fontCopy(FONT_SCAN_STALE_LABEL, 'EN').includes('outdated'), true);
});

test('恢复与备份副作用文案中英正确', () => {
  assert.equal(
    formatFontBackupSideEffect('C:/game/fonts_backup/x', 'ZH'),
    '备份：C:/game/fonts_backup/x',
  );
  assert.equal(
    formatFontBackupSideEffect('C:/game/fonts_backup/x', 'EN'),
    'Backup: C:/game/fonts_backup/x',
  );
  assert.equal(
    formatFontRestoreHint({ restored: true, message: 'ok' }, 'EN'),
    'Fully restored from backup',
  );
  assert.equal(
    formatFontRestoreHint(
      { restored: false, backup_path: 'C:/bak', message: '自动恢复未成功' },
      'ZH',
    ),
    '仅部分恢复，请检查备份路径',
  );
});
