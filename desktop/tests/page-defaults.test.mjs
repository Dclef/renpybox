/**
 * 绑定工程后各页面目录预填的静态契约。
 *
 * 规则：绑定/解析出工程后，工具页的目录框默认带出工程里的对应路径；
 * 用户始终可以手动改成别的目录，换工程时重新跟随。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/page-defaults.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const src = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'renderer', 'src');
const read = (...parts) => fs.readFileSync(path.join(src, ...parts), 'utf8');

test('游戏 mod：game 目录默认取工程的 game 目录，换工程重填', () => {
  const page = read('pages', 'GameModPage.tsx');
  assert.match(
    page,
    /const defaultGamePath = String\(state\.project\?\.renpy_game_folder \?\? state\.project\?\.renpy_project_path \?\? ''\);/,
  );
  assert.match(page, /useState\(defaultGamePath\)/);
  assert.match(page, /setGamePath\(defaultGamePath\)/);
  assert.match(page, /\}, \[defaultGamePath, suite\.identity\]\);/);
});

test('HTML 导入：源 TL 目录默认取工程的 tl/<语言> 目录', () => {
  const page = read('pages', 'HtmlImportPage.tsx');
  assert.match(page, /const defaultTlDir = String\(state\.project\?\.renpy_tl_folder \?\? ''\);/);
  assert.match(page, /useState\(defaultTlDir\)/);
  assert.match(page, /setTlDir\(defaultTlDir\)/);
  assert.match(page, /\}, \[defaultTlDir, suite\.identity\]\);/);
});

test('直接翻译 tl rpy：游戏目录取工程根，TL 父目录取 tl 的上一级', () => {
  const page = read('pages', 'DirectRpyTranslatePage.tsx');
  assert.match(page, /useState\(projectPath\)/);
  assert.match(page, /const defaultTlParent = useMemo\(\(\) => \{/);
  assert.match(page, /const cut = tl\.lastIndexOf\('\\\\'\);/);
  assert.match(page, /useState\(defaultTlParent\)/);
});

test('错误修复：后端无 tl 目录时退回工程的 tl 目录，且不覆盖用户已填值', () => {
  const page = read('pages', 'ErrorRepairPage.tsx');
  // 仍按身份只种一次，用户改过就不抢
  assert.match(page, /if \(!status \|\| seededRef\.current === suite\.identity\) return;/);
  assert.match(page, /setFolder\(\(current\) => \(current\.trim\(\) \? current : suggestedFolder\)\)/);
  // 后端算不出目录时用工程里记录的 tl/<语言>
  assert.match(page, /String\(state\.project\?\.renpy_tl_folder \?\? state\.settings\?\.values\?\.renpy_tl_folder \?\? ''\)/);
});
