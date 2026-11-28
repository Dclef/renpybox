import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import { readFileSync } from 'node:fs';
import { classifyWarning } from '../renderer/src/glossaryImport.mjs';
import { buildSync } from 'esbuild';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

// Compile the real component in memory; external React shares the test renderer's hooks.
const require = createRequire(import.meta.url);
const built = buildSync({
  stdin: {
    contents: "export { AgentExtractionFeedback, GlossaryTaskControls } from './renderer/src/pages/AgentExtractionFeedback'; export { ExtractionResumeOptions } from './renderer/src/pages/ExtractionScanDialog'; export { zh } from './renderer/src/i18n/zh'; export { en } from './renderer/src/i18n/en';",
    resolveDir: fileURLToPath(new URL('../', import.meta.url)),
    loader: 'ts',
  },
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
  jsx: 'automatic', loader: { '.css': 'empty' }, logLevel: 'silent',
});
const module = { exports: {} };
new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports);
const { AgentExtractionFeedback, GlossaryTaskControls, ExtractionResumeOptions, zh, en } = module.exports;
const render = (props = {}, dictionary = zh) => renderToStaticMarkup(createElement(AgentExtractionFeedback, {
  result: null, active: false, cancelling: false, t: key => dictionary[key], ...props,
}));

const progress = {
  phase: 'extracting', total_chunks: 124, completed_chunks: 4, successful_chunks: 4,
  failed_chunks: 0, pending_chunks: 116, elapsed_seconds: 100, candidate_count: 2,
  active_chunks: [{ index: 5, sources: ['story/chapter_01.rpy'], elapsed_seconds: 33 }],
  candidates: [{ src: 'preview-entity', type: 'name', source: 'characters.rpy', line: 3 }],
};

test('actual progress component renders 14% with matching aria integer and collapsed activity summary', () => {
  const html = render({ active: true, progressFraction: 0.14000000000000002, result: { extraction_progress: progress } });
  assert.match(html, /14%/);
  assert.match(html, /data-percent="14"/);
  assert.match(html, /aria-valuenow="14"/);
  assert.doesNotMatch(html, /14\.000000/);
  assert.ok(html.includes('分块 4/124'));
  assert.match(html, /成功 4/);
  assert.match(html, /失败 0/);
  assert.match(html, /活动来源（1）/);
  assert.match(html, /data-testid="agent-feedback-active-toggle"/);
  assert.doesNotMatch(html, /data-testid="agent-feedback-active"/);
  assert.ok(!html.includes('story/chapter_01.rpy'));
  assert.match(html, /候选预览/);
  assert.doesNotMatch(html, /data-testid="agent-feedback-warning-banner"/);
});

test('119 warnings render only compact summary and collapsed toggle, without duplicating result message', () => {
  const warnings = Array.from({ length: 119 }, (_, i) => 'chunk-failure-' + (i + 1));
  const html = render({ progressFraction: 1, warningText: '部分失败\n' + warnings.join('\n'), result: {
    message: '部分失败', status: 'partial', coverage_complete: false, warnings,
    extraction_progress: { ...progress, phase: 'completed', completed_chunks: 10, successful_chunks: 5, failed_chunks: 5, pending_chunks: 114, active_chunks: [], candidates: [] },
  } });
  assert.ok(html.includes('5/124 块成功，119 条警告'));
  assert.match(html, /data-warning-total="119"/);
  assert.match(html, /data-expanded="false"/);
  assert.match(html, /查看全部 119 条警告/);
  assert.match(html, /覆盖未完成/);
  assert.doesNotMatch(html, /chunk-failure-/);
  assert.doesNotMatch(html, /data-testid="agent-feedback-warning-list"/);
});

test('finished partial job retains stage, failure facts and preview without success progress or stale active chunks', () => {
  const html = render({ active: false, progressFraction: 1, result: {
    message: '部分完成', status: 'partial', coverage_complete: false, warnings: ['timeout'],
    extraction_progress: { ...progress, phase: 'completed', completed_chunks: 10, successful_chunks: 5, failed_chunks: 5, pending_chunks: 114 },
  } });
  assert.doesNotMatch(html, /data-testid="agent-feedback-progress"|role="progressbar"|ant-progress|100%/);
  assert.doesNotMatch(html, /data-testid="agent-feedback-active"/);
  assert.ok(!html.includes('story/chapter_01.rpy'));
  assert.ok(html.includes(zh.lexicon_extract_phase_completed));
  assert.ok(html.includes('5/124 块成功'));
  assert.ok(html.includes('失败 5'));
  assert.ok(html.includes('待处理 114'));
  assert.match(html, /覆盖未完成/);
  assert.match(html, /data-testid="agent-feedback-preview-toggle"/);
});

test('active cancelling job still renders integer 14% and collapsed activity access', () => {
  const html = render({ active: true, cancelling: true, progressFraction: 0.14, result: { extraction_progress: progress } });
  assert.match(html, /14%/);
  assert.match(html, /aria-valuenow="14"/);
  assert.match(html, /data-testid="agent-feedback-active-toggle"/);
  assert.doesNotMatch(html, /data-testid="agent-feedback-active"/);
  assert.ok(html.includes(zh.lexicon_cancelling));
});

test('legacy jobs retain message, integer percentage and safe timestamp elapsed fallback', () => {
  const html = render({ active: true, progressFraction: 0.14, createdAt: 1000, updatedAt: 1023.4, result: { message: 'Legacy message' } }, en);
  assert.match(html, /Legacy message/);
  assert.match(html, /14%/);
  assert.match(html, /Elapsed 23.4s as of the latest update/);
  assert.match(html, /data-structured="false"/);
  const missing = render({ active: true, result: {} }, en);
  assert.match(missing, /Elapsed time unavailable/);
  assert.doesNotMatch(missing, /NaN|Infinity/);
});

test('legacy final job still shows 5/124 and incomplete coverage without structured details', () => {
  const html = render({ result: { llm_chunks_total: 124, llm_chunks_success: 5, coverage_complete: false, warnings: ['timeout'], message: 'Finished' } }, en);
  assert.ok(html.includes('5/124 chunks succeeded, 1 warnings'));
  assert.match(html, /Coverage incomplete/);
});

test('read-only preview rendering never changes caller entries or candidate IDs', () => {
  const result = { entries: [{ src: 'saved draft', dst: 'manual value' }], candidate_ids: ['saved'], written: false, extraction_progress: progress };
  const before = structuredClone(result);
  const html = render({ active: true, result });
  assert.deepEqual(result, before);
  assert.match(html, /仅供预览，不写入词库/);
  assert.doesNotMatch(html, /preview-entity/); // collapsed until requested
});

test('cancel state and missing progress render safely without inventing coverage', () => {
  const html = render({ active: true, cancelling: true, result: {} });
  assert.match(html, /data-percent="0"/);
  assert.ok(html.includes(zh.lexicon_cancelling));
  assert.doesNotMatch(html, /NaN|Infinity|data-testid="agent-feedback-coverage"/);
});

test('warning and candidate details have bounded scroll regions scoped to the feedback component', () => {
  const css = readFileSync(new URL('../renderer/src/styles/agentExtractionFeedback.css', import.meta.url), 'utf8');
  for (const selector of ['rb-agent-feedback-warning-list', 'rb-agent-feedback-preview', 'rb-agent-feedback-active']) {
    const rule = css.split('.' + selector + ' {').at(-1)?.split('}')[0];
    assert.match(rule, /max-height:\s*\d+px/);
    assert.match(rule, /overflow-y:\s*auto/);
  }
  assert.match(css, /max-height:\s*min\(340px, 38vh\)/);
  assert.match(css, /scrollbar-color/);
  assert.match(css, /\.rb-agent-feedback-message\s*\{[^}]*(-webkit-line-clamp:\s*2|max-height:\s*\d+px)/);
  assert.match(css, /\.rb-agent-feedback\[data-active='true'\] \.rb-agent-feedback-message\s*\{[^}]*text-overflow:\s*ellipsis/);
  assert.match(css, /\.rb-banner-text\s*\{[^}]*max-height:\s*120px/);
  assert.match(css, /\.rb-banner-text\s*\{[^}]*overflow-y:\s*auto/);
  const feedback = readFileSync(new URL('../renderer/src/pages/AgentExtractionFeedback.tsx', import.meta.url), 'utf8');
  assert.match(feedback, /data-kind/);
  assert.match(feedback, /rb-warning-kind/);
  assert.equal(classifyWarning('第 1 块未能取得结果：RateLimitError 429 rate limit').kind, 'rate');
  assert.equal(classifyWarning('第 2 块：APITimeoutError 504 Read timed out').kind, 'timeout');
});

test('running toolbar retains search and stop while three idle operations stay in the closed popover', () => {
  let stopped = false;
  const html = renderToStaticMarkup(createElement(GlossaryTaskControls, {
    active: true, t: key => zh[key],
    search: createElement('input', { 'aria-label': 'search-glossary' }),
    stop: createElement('button', { 'data-testid': 'glossary-running-stop', onClick: () => { stopped = true; } }, '停止'),
    children: ['Import original', 'Save original', 'Edit original'].map(label => createElement('button', { key: label, disabled: true }, label)),
  }));
  assert.match(html, /aria-label="search-glossary"/);
  assert.match(html, /data-testid="glossary-running-stop"/);
  assert.match(html, /data-testid="glossary-running-actions-toggle"/);
  assert.match(html, /aria-expanded="false"/);
  assert.doesNotMatch(html, /Import original|Save original|Edit original|glossary-idle-actions/);
  assert.equal(stopped, false);
});

test('completed toolbar retains all original actions and exposes the short-window actions trigger', () => {
  const html = renderToStaticMarkup(createElement(GlossaryTaskControls, {
    active: false, t: key => en[key],
    search: createElement('input', { 'aria-label': 'search-glossary' }),
    stop: createElement('button', { 'data-testid': 'glossary-running-stop' }, 'Stop'),
    children: ['Import original', 'Save original', 'Edit original'].map(label => createElement('button', { key: label }, label)),
  }));
  for (const label of ['Import original', 'Save original', 'Edit original']) assert.ok(html.includes(label));
  assert.match(html, /glossary-idle-actions/);
  assert.match(html, /data-testid="glossary-running-actions-toggle"/);
  assert.doesNotMatch(html, /data-testid="glossary-running-stop"/);
});

test('short-window rules reduce actual default glossary controls instead of retaining the 55 percent scroll box', () => {
  const css = readFileSync(new URL('../renderer/src/styles/agentExtractionFeedback.css', import.meta.url), 'utf8');
  assert.ok(css.includes('@media (max-height: 820px)'));
  assert.match(css, /\.rb-glossary \.rb-glossary-idle-actions\s*\{\s*display:\s*none/);
  assert.match(css, /\.rb-glossary\[data-agent-running='true'\] > \.rb-lexicon-controls\s*\{[^}]*max-height:\s*none/);
  assert.match(css, /\.rb-glossary-actions-panel\s*\{[^}]*overflow-y:\s*auto/);
  assert.match(css, /\.rb-agent-feedback-detail-panel\s*\{[^}]*overflow-y:\s*auto/);
  assert.doesNotMatch(css, /\.rb-sheet\s*\{|\.ant-table-tbody\s*\{/);
});


test('old services get no resume options or recovery promises', () => {
  const html = renderToStaticMarkup(createElement(ExtractionResumeOptions, { supported: false, mode: 'resume', onChange() {}, t: key => zh[key] }));
  assert.equal(html, '');
  const legacy = render({ active: true, result: { extraction_progress: progress, resume_available: true } });
  assert.doesNotMatch(legacy, /agent-checkpoint-reused|agent-checkpoint-requested|agent-checkpoint-status|可恢复|可续/);
});

test('capable service offers conditional resume by default and an explicit restart', () => {
  const html = renderToStaticMarkup(createElement(ExtractionResumeOptions, { supported: true, mode: 'resume', onChange() {}, t: key => zh[key] }));
  assert.match(html, /data-testid="extraction-resume-options"/);
  assert.match(html, /checked="" value="resume"|value="resume" checked=""/);
  assert.match(html, /自动尝试继续未完成提取/);
  assert.match(html, /没有匹配记录或上次已全部完成/);
  assert.match(html, /重新开始，不复用检查点/);
  const restart = renderToStaticMarkup(createElement(ExtractionResumeOptions, { supported: true, mode: 'restart', onChange() {}, t: key => en[key] }));
  assert.match(restart, /checked="" value="restart"|value="restart" checked=""/);
});

test('provided reuse facts render without adding reused chunks twice or claiming a resumable cache exists', () => {
  const html = render({ active: true, result: { extraction_progress: { ...progress, completed_chunks: 7, successful_chunks: 7, reused_chunks: 5, requested_chunks: 3, checkpoint_status: 'resumed', resume_available: true } } });
  assert.ok(html.includes('分块 7/124'));
  assert.ok(html.includes('成功 7'));
  assert.ok(html.includes('复用 5 块'));
  assert.ok(html.includes('本轮请求 3 块'));
  assert.ok(html.includes('已续用检查点'));
  assert.doesNotMatch(html, /可恢复|可续缓存/);
});

