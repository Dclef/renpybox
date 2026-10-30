/**
 * 设置类输入框的提交时机：必须「本地草稿 + 失焦/回车提交」。
 *
 * 背景（2026-10-30 反馈）：设置页的数字输入框每敲一个字符就提交一次，
 * 提交会把该字段 PATCH 落盘并让外层进入 saving，控件随即 disabled，
 * 浏览器丢焦点 —— 表现为「输入一个字就得再点一下输入框」。
 * TextInput 在 0.9.x 已经改成草稿提交，NumberInput 漏了同一个修正。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/settings-input-focus.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const ui = fs.readFileSync(path.join(root, 'renderer/src/ui.tsx'), 'utf8');

/** 取出一个导出组件的源码块，避免整文件正则互相串台。 */
function block(name) {
  const start = ui.indexOf(`export function ${name}(`);
  assert.ok(start > 0, `找不到组件 ${name}`);
  const next = ui.indexOf('\nexport function ', start + 1);
  return ui.slice(start, next > 0 ? next : ui.length);
}

const numberInput = block('NumberInput');
const textInput = block('TextInput');
const settingsPage = fs.readFileSync(path.join(root, 'renderer/src/pages/SettingsPage.tsx'), 'utf8');
const appState = fs.readFileSync(path.join(root, 'renderer/src/useAppState.ts'), 'utf8');

test('NumberInput：敲字符只改本地草稿，不直接落盘', () => {
  // onChange 里不允许出现 onCommit —— 那是每敲一个字提交一次的老写法。
  // 只允许标记 focusedDirty（记录「用户确实改过」）。
  const body = numberInput.slice(numberInput.indexOf('onChange={'), numberInput.indexOf('onBlur={'));
  assert.ok(body, 'NumberInput 应有 onChange');
  assert.doesNotMatch(body, /onCommit/, 'NumberInput 的 onChange 不得直接提交');
  assert.match(body, /updateDraft/, 'NumberInput 的 onChange 只更新草稿');
  assert.match(body, /focusedDirty\.current = true/, 'onChange 标记用户确实改动过');
});

test('NumberInput：失焦与回车才提交，且钳制到 min/max', () => {
  assert.match(numberInput, /onBlur=\{\(\) => \{ focused\.current = false; commit\(\); focusedDirty\.current = false; \}\}/);
  assert.match(numberInput, /onPressEnter=\{commit\}/);
  assert.match(numberInput, /Math\.min\(max, Math\.max\(min, next\)\)/, '提交前按 min/max 钳制');
});

test('NumberInput：聚焦期间不用外部值覆盖草稿', () => {
  assert.match(numberInput, /if \(!focused\.current\) updateDraft/, '外部值只在未聚焦时同步回草稿');
});

test('NumberInput：onChange 同步写 ref，回车才提交最新值', () => {
  // antd 回车是「先 onChange 再 onPressEnter」，只靠渲染时赋值会提交旧值。
  assert.match(numberInput, /draftRef\.current = next;/, 'onChange 必须同步更新 ref');
  assert.match(numberInput, /const updateDraft = /, '统一走 updateDraft');
});

test('NumberInput：清空后离开回到上一个合法值，不写空值', () => {
  assert.match(numberInput, /if \(next === null \|\| !Number\.isFinite\(next\)\)/, '空/非法值不回写');
});

test('NumberInput：只点进去再离开不触发落盘', () => {
  // 历史越界值（下限 1 存了 0）不应因为一次 focus/blur 就被悄悄改写。
  assert.match(numberInput, /if \(edited && clamped !== value\) onCommit\(clamped\)/, '只有真的改过才提交');
});

test('TextInput：保持草稿提交，防止焦点被保存态抢走', () => {
  const body = textInput.slice(textInput.indexOf('onChange={'), textInput.indexOf('onBlur={'));
  assert.doesNotMatch(body, /onCommit/, 'TextInput 的 onChange 不得直接提交');
  assert.match(textInput, /onBlur=\{\(\) => \{ focused\.current = false; commit\(\); \}\}/);
});

test('设置页：文本类输入控件不再跟随 state.saving 禁用', () => {
  // 保存态禁用输入框 = 抢焦点，正是「打一个字得再点一下」的成因。
  // 开关/下拉是离散操作，不受影响，可以继续按 saving 禁用。
  for (const tag of ['TextInput', 'NumberInput', 'SelectInput', 'Input']) {
    // 只在同一个自闭合元素的范围内匹配，避免把相邻的 Switch 算进来。
    const re = new RegExp(`<${tag}\\b[\\s\\S]*?/>`, 'g');
    for (const [element] of settingsPage.matchAll(re)) {
      assert.doesNotMatch(
        element,
        /disabled=\{state\.saving\}/,
        `${tag} 不得跟随 state.saving 禁用（会抢走焦点）：${element.slice(0, 120)}`,
      );
    }
  }
  assert.match(settingsPage, /disabled = false/, 'SpecCard 的 disabled 应缺省为 false');
});

test('保存设置：PATCH 串行排队，并在响应里保留更新的字段', () => {
  // 不能并发 PATCH：早发晚到的整份 values 会把后改的字段回滚。
  assert.match(appState, /saveChain/, '应有串行保存队列');
  assert.match(appState, /saveLatestByKey/, '应按字段记录最新提交，防止旧响应回滚');
  assert.match(appState, /if \(entry\.seq > seq\) values\[key\] = entry\.value;/, '后提交的字段以本地值为准');
});
