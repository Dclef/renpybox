/**
 * 工具详情页共享布局静态检查（不启动 Electron / 不 build）。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/tool-page-layout.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const css = fs.readFileSync(path.join(root, 'renderer/src/styles/app.css'), 'utf8');
const frame = fs.readFileSync(path.join(root, 'renderer/src/components/ToolPageFrame.tsx'), 'utf8');
const ui = fs.readFileSync(path.join(root, 'renderer/src/ui.tsx'), 'utf8');

test('ToolPageFrame 使用 rb-tool-page / rb-tool-panel 层次', () => {
  assert.match(frame, /rb-tool-page/);
  assert.match(frame, /rb-tool-panel/);
  assert.match(frame, /data-rb-tool-frame/);
});

test('SettingsGroup 保留 rb-settings-body', () => {
  assert.match(ui, /className="rb-settings-body"/);
});

test('SettingsGroup body 默认 16px + flex-wrap', () => {
  assert.match(css, /\.rb-settings-body\s*\{[^}]*padding:\s*16px/s);
  assert.match(css, /\.rb-settings-body\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(css, /\.rb-settings-body\s*\{[^}]*gap:\s*8px 16px/s);
});

test('checkbox 占满一行，避免横向挤成一排', () => {
  assert.match(css, /\.rb-settings-body\s*>\s*\.ant-checkbox-wrapper\s*\{[^}]*flex:\s*1 1 100%/s);
});

test('含 SettingCard 行时去掉 body 双份边距', () => {
  assert.match(css, /\.rb-settings-body:has\(>\s*\.rb-setting-row\)\s*\{[^}]*padding:\s*0/s);
});

test('tool-panel 滚动页统一 padding/gap', () => {
  assert.match(css, /\.rb-tool-panel\s*>\s*\.rb-page-scroll\s*\{[^}]*padding:\s*0 4px 16px/s);
  assert.match(css, /\.rb-tool-panel\s*>\s*\.rb-page-scroll\s*\{[^}]*gap:\s*12px/s);
});

test('详情页有 Qt 底色与卡片阴影层次', () => {
  assert.match(css, /\.rb-tool-page\s*\{[^}]*background:\s*var\(--rb-qt-page\)/s);
  assert.match(css, /\.rb-tool-page\s+\.rb-settings-group\s*\{[^}]*box-shadow:\s*var\(--rb-qt-shadow\)/s);
});

test('onekey/archive/asset body 规则保留且不叠双份', () => {
  assert.match(
    css,
    /:is\(\.rb-onekey-page,\s*\.rb-archive-page,\s*\.rb-asset-page\)\s+\.rb-settings-body\s*\{[^}]*padding:\s*16px/s,
  );
});

test('工具页短 Banner 不强制撑满', () => {
  assert.match(css, /\.rb-tool-panel\s*>\s*\.rb-page-scroll\s*>\s*\.banner\s*\{[^}]*width:\s*fit-content/s);
});
