/**
 * 确认框与模型名称下拉的静态契约。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/dialog-confirm.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const src = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'renderer', 'src');

function sourceFiles(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(full);
    return /\.(tsx|ts|mjs|js)$/.test(entry.name) ? [full] : [];
  });
}

test('渲染端不再弹出 window.confirm', () => {
  const hits = sourceFiles(src).filter((file) => fs.readFileSync(file, 'utf8').includes('window.confirm('));
  assert.deepEqual(hits.map((file) => path.relative(src, file)), []);
});

test('模型名称按子串筛选，读取成功后自动展开', () => {
  const page = fs.readFileSync(path.join(src, 'pages', 'PlatformPage.tsx'), 'utf8');
  assert.match(page, /filterOption=/);
  assert.match(page, /onOpenChange=\{setModelOpen\}/);
  assert.match(page, /setModelOpen\(true\)/);
});
