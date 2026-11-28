/**
 * Agent 提取执行反馈：独立子组件，自带 useState 折叠状态。
 * 只读取 job 的 result.extraction_progress / warnings 做只读展示，
 * 绝不 setRows / setDirty / 保存；父组件 hooks 顺序完全不变。
 * data-testid 供隔离 Electron 布局验收量测（124/5/119 场景）。
 */
import { useEffect, useState, type ReactNode } from 'react';
import { Button, Popover, Progress, Tag } from 'antd';

import {
  checkpointFeedback,
  fillTemplate,
  formatSeconds,
  jobProgressPercent,
  jobElapsedSeconds,
  normalizeExtractionProgress,
  warningDigest,
  warningHeadline,
  type WarningDigest,
} from '../glossaryView.mjs';
import type { TextKey } from '../i18n';
import { feedbackPhase, previewLabels } from '../glossaryPreview.mjs';
import { classifyWarning, type WarningKind } from '../glossaryImport.mjs';
import '../styles/agentExtractionFeedback.css';

type T = (key: TextKey) => string;

const PHASE_KEYS: Record<string, TextKey> = {
  collecting: 'lexicon_extract_phase_collecting',
  extracting: 'lexicon_extract_phase_extracting',
  aggregating: 'lexicon_extract_phase_aggregating',
  completed: 'lexicon_extract_phase_completed',
};

export interface AgentExtractionFeedbackProps {
  /** 当前 job.result（含 extraction_progress / warnings / message） */
  result: unknown;
  /** job.progress，0..1 小数 */
  progressFraction?: number;
  createdAt?: number;
  updatedAt?: number;
  active: boolean;
  cancelling: boolean;
  /** 扫描完成时持久的警告文本（glossaryScanOutcome 产出） */
  warningText?: string;
  jobStatus?: string;
  language?: string | null;
  previewAdd?: { label: string; reason: string; note: string; onAdd: () => void };
  t: T;
}

/** 明细在浮层中滚动，展开不改变表格可用高度。状态只属于子组件。 */
function FeedbackDisclosure({ open, onOpenChange, label, testId, children }: {
  open: boolean; onOpenChange: (open: boolean) => void; label: string; testId: string; children: ReactNode;
}) {
  return (
    <Popover trigger="click" placement="bottomRight" open={open} onOpenChange={onOpenChange}
      content={<div className="rb-agent-feedback-detail-panel">{children}</div>}>
      <button type="button" className="rb-agent-feedback-toggle" data-testid={testId} aria-expanded={open}>
        {label}
      </button>
    </Popover>
  );
}

/** 保持父页 hooks、表格节点和草稿生命周期不变；运行时只把闲置操作收进浮层。 */
export function GlossaryTaskControls({ active, search, stop, children, t }: {
  active: boolean; search: ReactNode; stop: ReactNode; children: ReactNode; t: T;
}) {
  const [open, setOpen] = useState(false);
  useEffect(() => { setOpen(false); }, [active]);
  return (
    <div className="rb-glossary-task-controls" data-testid="glossary-task-controls" data-active={active ? 'true' : 'false'}>
      {!active ? <div className="rb-glossary-idle-actions" data-testid="glossary-idle-actions">{children}</div> : null}
      <div className="rb-glossary-live-toolbar" data-testid="glossary-live-toolbar">
        {search}
        {active ? stop : null}
        <Popover trigger="click" placement="bottomRight" open={open} onOpenChange={setOpen}
          content={<div className="rb-glossary-actions-panel" data-testid="glossary-running-actions" onClick={(event) => {
            const action = (event.target as HTMLElement).closest('button, [role="menuitem"], input');
            if (!action || action.hasAttribute('disabled') || action.getAttribute('aria-disabled') === 'true') return;
            if (action.classList.contains('ant-dropdown-trigger') || action.getAttribute('aria-haspopup') === 'menu') return;
            setOpen(false);
          }}>
            {active ? <p className="rb-agent-feedback-note">{t('lexicon_running_readonly')}</p> : null}
            {children}
          </div>}>
          <Button className="rb-glossary-secondary-toggle" data-testid="glossary-running-actions-toggle" aria-expanded={open}>{t('lexicon_running_other_actions')}</Button>
        </Popover>
      </div>
    </div>
  );
}

const WARNING_KIND_KEY: Record<WarningKind, TextKey> = {
  rate: 'lexicon_warn_kind_rate',
  timeout: 'lexicon_warn_kind_timeout',
  connection: 'lexicon_warn_kind_connection',
  request: 'lexicon_warn_kind_request',
  cancel: 'lexicon_warn_kind_cancel',
  other: 'lexicon_warn_kind_other',
};

function WarningList({ digest, t }: { digest: WarningDigest; t: T }) {
  const [expanded, setExpanded] = useState(false);
  if (!digest.total) return null;

  return (
    <section className="rb-agent-feedback-warnings" data-testid="agent-feedback-warnings"
      data-warning-total={digest.total} data-expanded={expanded ? 'true' : 'false'}>
      <FeedbackDisclosure open={expanded} onOpenChange={setExpanded} testId="agent-feedback-warning-toggle"
        label={expanded ? t('lexicon_warning_hide') : fillTemplate(t('lexicon_warning_show'), { count: digest.total })}>
        <ul className="rb-agent-feedback-warning-list" data-testid="agent-feedback-warning-list">
          {digest.items.map((line, index) => {
            const warning = classifyWarning(line);
            return (
              <li key={index} className="rb-agent-feedback-warning-item" data-kind={warning.kind}>
                <span className="rb-warning-kind">{t(WARNING_KIND_KEY[warning.kind])}</span>
                {warning.head ? <span className="rb-warning-head">{warning.head}</span> : null}
                <span className="rb-warning-detail">{warning.detail}</span>
              </li>
            );
          })}
        </ul>
        <p className="rb-agent-feedback-note">{t('lexicon_warning_note')}</p>
      </FeedbackDisclosure>
    </section>
  );
}

const CHECKPOINT_KEYS: Record<string, TextKey> = {
  new: 'lexicon_checkpoint_new', resumed: 'lexicon_checkpoint_resumed', complete: 'lexicon_checkpoint_complete',
  corrupt: 'lexicon_checkpoint_corrupt', incompatible: 'lexicon_checkpoint_incompatible',
  unavailable: 'lexicon_checkpoint_unavailable', superseded: 'lexicon_checkpoint_superseded',
};

function CheckpointFacts({ facts, t }: { facts: ReturnType<typeof checkpointFeedback>; t: T }) {
  return <>
    {facts.reusedChunks != null ? <span data-testid="agent-checkpoint-reused">{fillTemplate(t('lexicon_checkpoint_reused'), { count: facts.reusedChunks })}</span> : null}
    {facts.requestedChunks != null ? <span data-testid="agent-checkpoint-requested">{fillTemplate(t('lexicon_checkpoint_requested'), { count: facts.requestedChunks })}</span> : null}
    {facts.status ? <span data-testid="agent-checkpoint-status">{t(CHECKPOINT_KEYS[facts.status])}</span> : null}
  </>;
}

export function AgentExtractionFeedback(props: AgentExtractionFeedbackProps) {
  const { result, progressFraction, active, cancelling, warningText = '', t } = props;
  const [previewOpen, setPreviewOpen] = useState(false);
  const [activeOpen, setActiveOpen] = useState(false);

  const r = result && typeof result === 'object' && !Array.isArray(result)
    ? (result as Record<string, unknown>)
    : {};
  const view = normalizeExtractionProgress(r.extraction_progress);
  const checkpoint = checkpointFeedback(r);
  const hasCheckpointFacts = checkpoint.reusedChunks != null || checkpoint.requestedChunks != null || Boolean(checkpoint.status);
  const warnings = Array.isArray(r.warnings) ? (r.warnings as unknown[]) : [];
  // 结构化 warnings 已含全部原因，持久文本中的摘要不再重复计作一条警告。
  const digest = warningDigest(warnings, warnings.length ? '' : warningText);
  const headline = warningHeadline(view, digest, r);
  const legacyElapsed = jobElapsedSeconds(props.createdAt, props.updatedAt);
  const percent = jobProgressPercent(progressFraction);
  const terminal = !active && props.jobStatus === 'cancelled';
  const message = terminal ? previewLabels(props.language).cancelMessage : String(r.message ?? '').trim() || (active ? t('lexicon_job_running') : '');
  const phase = feedbackPhase(props.jobStatus, active, cancelling, props.language) || (view ? t(PHASE_KEYS[view.phase] ?? PHASE_KEYS.extracting) : '');
  const candidateCaption = props.previewAdd && view ? (props.language === 'EN' ? `Extracted candidates: ${view.candidateCount}` : `已提取候选 ${view.candidateCount} 条`) : '';
  const showStructured = Boolean(view);
  const showWarningBanner = digest.total > 0 || headline.coverageIncomplete;

  if (!active && !showStructured && !showWarningBanner && !hasCheckpointFacts) return null;

  const warningHeadlineText = headline.hasChunkSummary
    ? fillTemplate(t('lexicon_warning_summary'), {
        successful: headline.successful,
        total: headline.total,
        count: headline.warningCount,
      })
    : fillTemplate(t('lexicon_warning_summary_simple'), { count: headline.warningCount });

  // 没有结构化字段的旧 job：继续显示 message + 整数进度 + 安全耗时提示
  const legacyNote = !showStructured ? t('lexicon_extract_legacy') : '';

  return (
    <div className="rb-agent-feedback" data-testid="agent-feedback" data-active={active ? 'true' : 'false'} data-structured={showStructured ? 'true' : 'false'}>
      {active || showStructured || message || hasCheckpointFacts ? (
        <div className="rb-agent-feedback-status" data-testid="agent-feedback-status">
          <div className="rb-agent-feedback-status-head">
            {active && cancelling && !showStructured ? <Tag>{t('lexicon_cancelling')}</Tag> : null}
            {showStructured ? <Tag data-testid="agent-feedback-phase" color={active ? 'processing' : undefined}>{phase}</Tag> : null}
            {message ? <span className="rb-agent-feedback-message" title={message}>{message}</span> : null}
          </div>
          {active ? (
            <div data-testid="agent-feedback-progress" data-percent={percent}>
              <Progress percent={percent} aria-label={t('lexicon_job_running')} />
            </div>
          ) : null}
          {showStructured ? (
            <>
              <div className="rb-agent-feedback-summary" data-testid="agent-feedback-summary">
                {fillTemplate(t('lexicon_extract_summary'), {
                  completed: view!.completedChunks,
                  total: view!.totalChunks,
                  successful: view!.successfulChunks,
                  failed: view!.failedChunks,
                  pending: view!.pendingChunks,
                })}
                {' · '}
                {fillTemplate(t('lexicon_extract_elapsed'), { seconds: formatSeconds(view!.elapsedSeconds) })}
              </div>
              <div className="rb-agent-feedback-detail-actions">
              <CheckpointFacts facts={checkpoint} t={t} />
              {active && view!.activeChunks.length ? (
                <FeedbackDisclosure open={activeOpen} onOpenChange={setActiveOpen} testId="agent-feedback-active-toggle"
                  label={fillTemplate(t('lexicon_extract_active_toggle'), { count: view!.activeChunks.length })}>
                <ul className="rb-agent-feedback-active" data-testid="agent-feedback-active">
                  {view!.activeChunks.map((chunk) => (
                    <li key={chunk.index}>
                      {fillTemplate(t('lexicon_extract_active'), {
                        index: chunk.index,
                        sources: chunk.sources.length ? chunk.sources.join(', ') : t('lexicon_extract_sources_unknown'),
                        seconds: formatSeconds(chunk.elapsedSeconds),
                      })}
                      {chunk.reasoning ? (
                        <details className="rb-agent-feedback-reasoning">
                          <summary>{t('lexicon_extract_reasoning')}</summary>
                          <div className="reasoning-text">{chunk.reasoning}</div>
                        </details>
                      ) : null}
                    </li>
                  ))}
                </ul>
                </FeedbackDisclosure>
              ) : null}
              <div className="rb-agent-feedback-counts">
                <span data-testid="agent-feedback-candidate-count" title={candidateCaption || fillTemplate(t('lexicon_extract_candidates'), { count: view!.candidateCount })}>
                  {candidateCaption || fillTemplate(t(active ? 'lexicon_extract_candidates_short' : 'lexicon_extract_candidates'), { count: view!.candidateCount })}
                </span>
                {view!.candidatesTruncated ? (
                  <span>{fillTemplate(t('lexicon_extract_candidates_more'), { count: Math.max(0, view!.candidateCount - view!.candidates.length) })}</span>
                ) : null}
              </div>
              {view!.candidates.length ? (
                <>
                  <FeedbackDisclosure open={previewOpen} onOpenChange={setPreviewOpen} testId="agent-feedback-preview-toggle"
                    label={previewOpen ? t('lexicon_extract_preview_hide') : t('lexicon_extract_preview')}>
                    <p className="rb-agent-feedback-note">{props.previewAdd?.note || fillTemplate(t('lexicon_extract_candidates'), { count: view!.candidateCount })}</p>
                    {props.previewAdd ? <div><Button data-testid="agent-feedback-add-preview" disabled={Boolean(props.previewAdd.reason)} onClick={props.previewAdd.onAdd}>{props.previewAdd.label}</Button>{props.previewAdd.reason ? <p className="rb-agent-feedback-note" data-testid="agent-feedback-add-reason" role="status">{props.previewAdd.reason}</p> : null}</div> : null}
                    <ul className="rb-agent-feedback-preview" data-testid="agent-feedback-preview">
                      {view!.candidates.map((candidate, index) => (
                        <li key={`${index}-${candidate.src}`}>
                          <strong>{candidate.src}</strong>
                          {candidate.type ? <span className="rb-agent-feedback-type">{candidate.type}</span> : null}
                          {candidate.source || candidate.line ? (
                            <span className="rb-agent-feedback-location">
                              {candidate.line > 0 ? fillTemplate(t('lexicon_extract_preview_location'), {
                                source: candidate.source || t('lexicon_extract_sources_unknown'),
                                line: candidate.line,
                              }) : candidate.source}
                            </span>
                          ) : null}
                          {candidate.evidence ? <span className="rb-agent-feedback-evidence">{candidate.evidence}</span> : null}
                        </li>
                      ))}
                    </ul>
                  </FeedbackDisclosure>
                </>
              ) : null}
              </div>
            </>
          ) : (
            <>
            <p className="rb-agent-feedback-note" data-testid="agent-feedback-legacy">
              {legacyNote}{' · '}
              {legacyElapsed == null ? t('lexicon_extract_elapsed_unknown') : fillTemplate(t('lexicon_extract_elapsed_snapshot'), { seconds: legacyElapsed })}
            </p>
            {hasCheckpointFacts ? <div className="rb-agent-feedback-detail-actions"><CheckpointFacts facts={checkpoint} t={t} /></div> : null}
            </>
          )}
        </div>
      ) : null}

      {showWarningBanner ? (
        <section className="rb-agent-feedback-warning" data-testid="agent-feedback-warning-banner">
          <div className="rb-agent-feedback-warning-head" data-testid="agent-feedback-warning-summary">
            <Tag color="warning">{warningHeadlineText}</Tag>
            {headline.coverageIncomplete ? (
              <span className="rb-agent-feedback-coverage" data-testid="agent-feedback-coverage">
                {t('lexicon_extract_coverage_incomplete')}
              </span>
            ) : null}
          </div>
          <WarningList digest={digest} t={t} />
        </section>
      ) : null}
    </div>
  );
}
