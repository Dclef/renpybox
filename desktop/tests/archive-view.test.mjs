import assert from 'node:assert/strict';
import test from 'node:test';

import { archiveJobCancellable, derivePackOutput, isGameFolder, resolvePackOutput } from '../renderer/src/archiveView.mjs';

test('只有打包任务显示和执行取消，与 Qt5 一致', () => {
  assert.equal(archiveJobCancellable({ kind: 'archive_pack' }), true);
  for (const kind of ['archive_unpack', 'archive_decompile', 'archive_cleanup_temp', 'archive_cleanup_rpyc']) {
    assert.equal(archiveJobCancellable({ kind }), false, kind);
  }
  assert.equal(archiveJobCancellable(null), false);
});

test('整个 game 目录不推导项目根 game.rpa', () => {
  assert.equal(isGameFolder('C:\\Games\\Demo\\game\\'), true);
  assert.equal(isGameFolder('C:/Games/Demo/GAME'), true);
  assert.equal(isGameFolder('C:/Games/Demo/game/images'), false);
  assert.equal(derivePackOutput('C:\\Games\\Demo\\game'), '');
  assert.equal(derivePackOutput('C:\\Games\\Demo\\game\\images'), 'C:\\Games\\Demo\\game\\images.rpa');
  assert.equal(derivePackOutput('C:/Games/Demo/game/images/'), 'C:/Games/Demo/game/images.rpa');
  assert.equal(derivePackOutput('C:'), '');
  assert.equal(derivePackOutput(''), '');
});

test('相对输出落在源目录同级，绝对路径原样保留', () => {
  assert.equal(resolvePackOutput('C:\\Games\\Demo\\game\\images', 'pics.rpa'), 'C:\\Games\\Demo\\game\\pics.rpa');
  assert.equal(resolvePackOutput('C:\\Games\\Demo\\game', 'patch.rpa'), 'C:\\Games\\Demo\\patch.rpa');
  assert.equal(resolvePackOutput('C:\\Games\\Demo\\game', 'D:\\out\\a.rpa'), 'D:\\out\\a.rpa');
  assert.equal(resolvePackOutput('C:\\Games\\Demo\\game', '   '), '');
});
