/**
 * 翻译任务页 —— 替代 TranslationPage.py 的运行时部分。
 *
 * 布局按实测几何复原（页宽 1183、nav=48 时）：
 *   header 1183x32  @ (24, 18)   标题 18px 粗体 + 说明 + 右侧「打开平行校对台」32px 按钮
 *   KPI 条 1183x88  @ (24, 62)   三张 386 宽的高 88 KPI 卡
 *   网格   1183x523 @ (24, 162)  280x248 进度环卡 + 889x248 吞吐卡 + 1183x261 流水卡
 *   命令栏 1231x58  @ (0, 703)   钉在页面底部、在滚动区之外；按钮高 34
 *
 * 保留 PyQt 页的决策逻辑：开始前引擎必须 IDLE 且无 stop_barrier、
 * ASSETS_MISSING 时交给用户选择「打开工作台 / 仍然继续」、停止前确认、
 * 进度读取应用级快照，切页和任务结束后仍保留统计、
 * preparing 阶段显示不确定进度。
 * 不做的是流水的逐行虚拟化（等校对页迁移时一起做）。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  IconCalories,
  IconChevronRight,
  IconDocument,
  IconFolder,
  IconIot,
  IconPlay,
  IconRotate,
  IconShare,
  IconStop,
  IconSync,
} from '../icons';
import { ProgressRing } from '../ProgressRing';
import type { StartableProjectStatus, TranslationUpdateData } from '../types';
import { Dialog, Empty } from '../ui';
import type { AppState } from '../useAppState';
import { Waveform } from '../Waveform';

const STATUS_TEXT: Record<string, string> = {
  IDLE: '无任务',
  TESTING: '测试中',
  TRANSLATING: '翻译中',
  QUALITY: '质量处理中',
  AGENT: 'Agent 操作中',
  STOPPING: '停止中',
};

const PHASE_TEXT: Record<string, string> = {
  preparing: '预处理中',
  reading: '正在读取翻译输入目录',
  writing: '正在写入翻译缓存',
};

/** 波形采样节拍：对齐 WaveformWidget 的 refresh_rate = 2（500ms） */
const SAMPLE_INTERVAL_MS = 500;
const WAVE_COLUMNS = 50;

/** 文案格式照 LocalizerZH：{H}时 {M}分 {S}秒 / {M}分 {S}秒 / {S}秒 */
function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '—';
  const total = Math.floor(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}时 ${m}分 ${s}秒`;
  if (m > 0) return `${m}分 ${s}秒`;
  return `${s}秒`;
}

type KpiAccent = 'accent' | 'success' | 'warning' | 'info';

/** KPI 卡：38x38 图标块 + 标题/趋势行 + 20px 粗体数值 + 说明 */
function KpiCard(props: {
  icon: React.ReactNode;
  accent: KpiAccent;
  title: string;
  value: string;
  unit?: string;
  trend?: string;
  detail?: string;
}) {
  const { icon, accent, title, value, unit, trend, detail } = props;
  return (
    <section className="card kpi-card">
      <div className="kpi-icon" data-accent={accent}>
        {icon}
      </div>
      <div className="kpi-content">
        <div className="kpi-label-row">
          <span className="kpi-title">{title}</span>
          {trend ? (
            <span className="kpi-trend" data-accent={accent}>
              {trend}
            </span>
          ) : null}
        </div>
        <div className="kpi-value-row">
          <span className="kpi-value">{value}</span>
          {unit ? <span className="kpi-unit">{unit}</span> : null}
        </div>
        {detail ? <div className="kpi-detail">{detail}</div> : null}
      </div>
    </section>
  );
}

export function TranslationPage(props: {
  state: AppState;
  onOpenWorkbench: () => void;
  onOpenProofreading: () => void;
  onOpenProject: () => void;
  onOpenPlatform: () => void;
}) {
  const { state, onOpenWorkbench, onOpenProofreading, onOpenProject, onOpenPlatform } = props;
  const progress = state.translation.progress as TranslationUpdateData;
  const [samples, setSamples] = useState<number[]>([]);
  const [confirmStop, setConfirmStop] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  const [assetsMissing, setAssetsMissing] = useState(false);
  const [busy, setBusy] = useState(false);
  const lastSampleAt = useRef(0);

  const status = state.translation.engine_status;
  const running = state.translation.running.running;
  const max = state.translation.running.max;
  const isTranslating = status === 'TRANSLATING';
  const isStopping = status === 'STOPPING' || state.translation.stop_barrier;

  const sourceLanguage = String(state.settings?.values.source_language ?? '');
  const targetLanguage = String(state.settings?.values.target_language ?? '');
  const inputFolder = String(state.settings?.values.input_folder ?? '');
  const platforms = state.settings?.values.platforms;
  const activePlatform = Array.isArray(platforms)
    ? platforms.find((platform) => platform.id === Number(state.settings?.values.activate_platform ?? -1))
    : undefined;
  const platformName = String(activePlatform?.name || '选择翻译接口');

  // 进度由应用级状态合并；这里只在下一轮开始时清除上一轮波形。
  useEffect(() => {
    return state.subscribe((message) => {
      if (message.event === 'TRANSLATION_START') {
        setSamples([]);
        lastSampleAt.current = 0;
      }
    });
  }, [state.subscribe]);

  // 轮询补一次 running 计数：running/max 不在事件流里，引擎在跑时定时对齐。
  useEffect(() => {
    if (!isTranslating && !isStopping) return;
    const timer = window.setInterval(() => {
      void state.reloadTranslation();
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isTranslating, isStopping, state.reloadTranslation]);

  const line = Number(progress.line ?? 0);
  const totalLine = Number(progress.total_line ?? 0);
  const percent = totalLine > 0 ? Math.min(1, line / totalLine) : 0;
  const preparing = progress.phase === 'preparing' || (isTranslating && line === 0);
  const message = progress.message ?? PHASE_TEXT[progress.phase ?? ''] ?? '';

  const inputTokens = Number(progress.total_input_tokens ?? 0);
  const outputTokens = Number(progress.total_output_tokens ?? 0);
  const elapsed = Number(progress.time ?? 0);
  const remaining = totalLine > line && elapsed > 0 ? (elapsed / Math.max(line, 1)) * (totalLine - line) : 0;
  const failed = Number(progress.failed_line_count ?? 0);
  const batches = Number(progress.processed_batches ?? 0);
  const requestCount = Number(progress.request_count ?? 0);
  const totalLatency = Number(progress.total_latency_ms ?? 0);
  const averageLatency = requestCount > 0 ? totalLatency / requestCount / 1000 : 0;
  // 新版吞吐是 TranslationMetrics.snapshot() 字典，不能直接 Number()。
  const rawThroughput = state.translation.progress.throughput;
  const metrics = rawThroughput && typeof rawThroughput === 'object'
    && 'schema_version' in rawThroughput && rawThroughput.schema_version === 1
    ? rawThroughput as Record<string, unknown>
    : null;
  const metricsElapsed = Number(metrics?.elapsed_seconds ?? elapsed);
  const throughput = metrics
    ? (metricsElapsed > 0 ? Number(metrics.output_tokens ?? 0) / metricsElapsed : 0)
    : (typeof rawThroughput === 'number' ? rawThroughput : (elapsed > 0 ? outputTokens / elapsed : 0));
  const effectiveRate = Number(metrics?.effective_items_per_minute ?? (elapsed > 0 ? line * 60 / elapsed : 0));
  const peak = samples.length > 0 ? Math.max(...samples) : 0;
  const cacheRate = Number(progress.cache_hit_rate ?? 0);
  const cachedLineCount = Number(progress.cached_line_count ?? 0);
  const canStart = status === 'IDLE' && !isStopping && !state.translation.single_tasks;

  // 波形按 500ms 从共享快照采样，避免把每一条进度消息都画成一根柱。
  useEffect(() => {
    if (!('throughput' in progress) && !('total_output_tokens' in progress)) return;
    const now = Date.now();
    if (now - lastSampleAt.current < SAMPLE_INTERVAL_MS) return;
    lastSampleAt.current = now;
    setSamples((prev) => [...prev, Number.isFinite(throughput) ? throughput : 0].slice(-WAVE_COLUMNS));
  }, [progress, throughput]);

  const linesDetail = `${line.toLocaleString()} / ${totalLine.toLocaleString()} 行`;
  const headerDescription =
    status === 'IDLE'
      ? '实时查看翻译进度、吞吐和可恢复操作'
      : `当前翻译任务 · 源语言 ${sourceLanguage} ➔ 目标语言 ${targetLanguage} · 线程池 ${running}/${max}`;

  const recentItems = useMemo(() => {
    const raw = progress.recent_items;
    return Array.isArray(raw) ? (raw as Record<string, unknown>[]).slice(0, 40) : [];
  }, [progress.recent_items]);

  const start = useCallback(
    async (projectStatus: StartableProjectStatus, preflightConfirmed = false) => {
      setBusy(true);
      try {
        const response = await state.startTranslation(projectStatus, preflightConfirmed);
        if (!response.accepted && response.reason === 'ASSETS_MISSING') {
          setAssetsMissing(true);
        }
      } finally {
        setBusy(false);
      }
    },
    [state],
  );

  const onStop = useCallback(async () => {
    setConfirmStop(false);
    setBusy(true);
    try {
      await state.stopTranslation();
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [state]);

  const onEstimate = useCallback(async () => {
    setBusy(true);
    try {
      const result = await state.estimateTokens();
      if (!result) return;
      state.pushToast(
        'info',
        `估算：原文 ${result.total_source_tokens} tokens，输入约 ${result.estimated_input_tokens}，` +
          `输出约 ${result.estimated_output_tokens}，${result.batch_count} 个批次，待译 ${result.untranslated_count} 条`,
      );
    } catch (error) {
      state.pushToast('warning', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [state]);

  const commandDisabled = busy || !state.ready;
  const statusLabel = isStopping ? '正在停止' : preparing ? '正在准备'
    : status !== 'IDLE' ? STATUS_TEXT[status] ?? status
    : totalLine > 0 ? line >= totalLine && failed === 0 ? '已完成' : '可继续' : '待开始';

  return (
    <div className="translation-layout">
      <div className="translation-scroll">
        <header className="translation-header">
          <div className="translation-header-text">
            <div className="translation-heading">
              <h1 className="translation-header-title">翻译任务</h1>
              <span className="task-state" data-active={isTranslating} data-warning={isStopping || failed > 0} role="status">{statusLabel}</span>
            </div>
            <p className="translation-header-desc">{headerDescription}</p>
          </div>
          <button
            type="button"
            className="btn"
            onClick={onOpenProofreading}
          >
            <IconDocument size={15} />
            打开平行校对台
          </button>
        </header>

        <div className="task-context">
          <button type="button" className="task-context-button task-input" title={inputFolder || '选择翻译输入目录'} aria-label="配置翻译输入目录" onClick={onOpenProject}>
            <IconFolder size={15} />
            <span>{inputFolder || '选择翻译输入目录'}</span>
          </button>
          <span className="task-language-pair" aria-label={`原文 ${sourceLanguage || '未设置'}，译文 ${targetLanguage || '未设置'}`}>
            {sourceLanguage || '原文'}<IconChevronRight size={12} />{targetLanguage || '译文'}
          </span>
          <button type="button" className="task-context-button task-platform" title={activePlatform?.model && activePlatform.model !== 'no_model_required' ? `${platformName} · ${activePlatform.model}` : platformName} aria-label="配置翻译接口" onClick={onOpenPlatform}>
            <IconIot size={15} />
            <span>{platformName}</span>
            <IconChevronRight size={12} />
          </button>
        </div>

        <div className="kpi-strip">
          <KpiCard
            icon={<IconDocument size={20} />}
            accent={failed > 0 ? 'warning' : 'accent'}
            title="翻译进度"
            value={(percent * 100).toFixed(1)}
            unit="%"
            trend={failed > 0 ? `${failed} 行失败` : undefined}
            detail={linesDetail}
          />
          <KpiCard
            icon={<IconCalories size={20} />}
            accent="info"
            title="实时吞吐"
            value={throughput.toFixed(2)}
            unit="Token/s"
            detail={`有效翻译速度 ${effectiveRate.toFixed(1)} 条/分`}
          />
          <KpiCard
            icon={<IconShare size={20} />}
            accent="success"
            title="累计消耗"
            value={(inputTokens + outputTokens).toLocaleString()}
            unit="Token"
            detail={`输出: ${outputTokens.toLocaleString()} · 输入: ${inputTokens.toLocaleString()}`}
          />
        </div>

        <div className="dashboard-grid">
          <section className="card progress-card">
            <h2 className="card-title">翻译完成度</h2>
            <div className="progress-ring-slot">
              <ProgressRing
                value={percent * 10000}
                size={136}
                stroke={7}
                lines={[`${(percent * 100).toFixed(1)}%`, `${line.toLocaleString()} / ${totalLine.toLocaleString()}`]}
              />
            </div>
            <div className="pill-row">
              <span className="badge" data-tone="success">
                已译 {line.toLocaleString()}
              </span>
              <span className="badge" data-tone="info" title="任务开始前已有译文的占比。0% 不影响译文和进度自动保存；暂停后可继续任务。">
                {cachedLineCount > 0 ? `已有 ${cachedLineCount}` : '已有 —'}
              </span>
              <span className="badge" data-tone="warning">
                待译 {Math.max(0, totalLine - line).toLocaleString()}
              </span>
            </div>
            <div className="hero-meta">
              <span>已用: {formatDuration(elapsed)}</span>
              <span className="hero-remaining">剩余约: {remaining > 0 ? formatDuration(remaining) : '—'}</span>
            </div>
          </section>

          <section className="card throughput-card">
            <header className="card-header">
              <h2 className="card-title">吞吐趋势</h2>
              <span className="card-description">峰值 {peak.toFixed(2)} Token/s</span>
            </header>
            <Waveform points={samples} columns={WAVE_COLUMNS} height={132} />
            <div className="chart-caption"><span>最近 {WAVE_COLUMNS} 次采样</span><span>最新</span></div>
            <div className="throughput-stats">
              <span>
                均值吞吐 <b>{throughput.toFixed(2)}</b>
              </span>
              <span>
                已处理批次 <b>{batches.toLocaleString()}</b>
              </span>
              <span>
                已有译文占比 <b>{(cacheRate > 1 ? cacheRate : cacheRate * 100).toFixed(1)}%</b>
              </span>
              <span>
                平均请求耗时 <b>{averageLatency > 0 ? `${averageLatency.toFixed(2)}s` : '—'}</b>
              </span>
            </div>
          </section>

          <section className="card feed-card">
            <header className="card-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <h2 className="card-title">实时翻译流水</h2>
                <span className="feed-card-badge">{recentItems.length} 条记录</span>
              </div>
              <span className="card-description">自动追踪引擎吐出的最新对白</span>
            </header>
            {recentItems.length > 0 ? (
              <div className="feed-scroll">
                <table className="table">
                  <thead>
                    <tr>
                      <th>时间</th>
                      <th>原文 <span className="table-header-tag">{sourceLanguage}</span></th>
                      <th>译文 <span className="table-header-tag table-header-tag-accent">{targetLanguage}</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentItems.map((item, index) => (
                      // 流水行没有稳定 id，用序号做 key（每次更新整体重排）
                      <tr key={index} data-latest={index === 0 ? 'true' : undefined}>
                        <td className="feed-time">
                          <span className="feed-time-wrap">
                            {String(item.time ?? item.timestamp ?? '')}
                          </span>
                        </td>
                        <td className="feed-source">{String(item.src ?? item.source ?? '')}</td>
                        <td className="feed-target">{String(item.dst ?? item.target ?? '')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty>
                <div className="translation-empty-content">
                  <IconDocument size={28} />
                  <strong>{isTranslating ? '正在等待第一批译文' : '暂无翻译流水'}</strong>
                  <span>{message || '开始翻译后，原文与译文会显示在这里。'}</span>
                </div>
              </Empty>
            )}
          </section>
        </div>
      </div>

      {/* 命令栏在滚动区之外、钉在页面底部（对齐 CommandBarCard 的 58px） */}
      <footer className="translation-footer">
        <div className="command-bar">
          <button
            type="button"
            className="btn btn-primary"
            disabled={commandDisabled || !canStart || isTranslating}
            onClick={() => setConfirmReset(true)}
          >
            <IconPlay size={15} />
            开始翻译
          </button>
          <button
            type="button"
            className="btn"
            disabled={commandDisabled || !canStart}
            onClick={() => void start('TRANSLATING')}
          >
            <IconRotate size={15} />
            继续任务
          </button>
          <span className="command-separator" />
          <button
            type="button"
            className="btn btn-danger"
            disabled={commandDisabled || !isTranslating}
            onClick={() => setConfirmStop(true)}
          >
            <IconStop size={15} />
            停止
          </button>
          <button type="button" className="btn" disabled={commandDisabled} onClick={() => void onEstimate()}>
            <IconCalories size={15} />
            估算 Token
          </button>
          <span className="command-separator" />
          <button
            type="button"
            className="btn"
            disabled={commandDisabled}
            onClick={() =>
              void state.retryFailedTranslations().catch((error: unknown) => {
                state.pushToast('warning', error instanceof Error ? error.message : String(error));
              })
            }
          >
            <IconSync size={15} />
            重翻失败项
          </button>
          <button
            type="button"
            className="btn"
            disabled={commandDisabled || isTranslating}
            onClick={() =>
              void state.exportTranslation().catch((error: unknown) => {
                state.pushToast('warning', error instanceof Error ? error.message : String(error));
              })
            }
          >
            <IconShare size={15} />
            写入译文文件
          </button>
          <span className="command-bar-spacer" />
          {preparing ? <span className="command-spinner" aria-label="处理中" /> : null}
          <span className="command-caption">
            {statusLabel}
            {isTranslating ? ` · ${running}/${max}` : ''}
          </span>
        </div>
      </footer>

      {confirmStop ? (
        <Dialog
          title="提醒"
          confirmText="确认"
          cancelText="取消"
          onConfirm={() => void onStop()}
          onCancel={() => setConfirmStop(false)}
        >
          <p>停止的翻译任务可以随时继续翻译，是否确定停止任务 … ？</p>
        </Dialog>
      ) : null}

      {confirmReset ? (
        <Dialog
          title="提醒"
          confirmText="确认"
          cancelText="取消"
          onConfirm={() => {
            setConfirmReset(false);
            void start('UNTRANSLATED');
          }}
          onCancel={() => setConfirmReset(false)}
        >
          <p>将重置尚未完成的翻译任务，是否确认开始新的翻译任务 … ？</p>
        </Dialog>
      ) : null}

      {assetsMissing ? (
        <Dialog
          title="当前项目没有可用资产"
          confirmText="仍然继续"
          cancelText="取消"
          extraText="打开工作台"
          onExtra={() => {
            setAssetsMissing(false);
            onOpenWorkbench();
          }}
          onConfirm={() => {
            setAssetsMissing(false);
            void start('UNTRANSLATED', true);
          }}
          onCancel={() => setAssetsMissing(false)}
        >
          <p>未找到已启用且有效的世界观、角色卡、术语或禁翻项。可以先打开工作台完善项目资产，也可以仍然继续本次翻译。</p>
        </Dialog>
      ) : null}
    </div>
  );
}
