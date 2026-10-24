/**
 * 剧情蓝图：按章节看全部 label、真实翻译进度与分支。
 *
 * 两个视图共用同一份 `/api/story-blueprint` 数据：
 * - 「清单」是主线：一个 label 一行，右边点开是逐行原文/译文对照，够用来判断
 *   「这段剧情翻到哪了、哪句没翻」；进度来自应用翻译缓存，和校对台同一口径。
 * - 「关系图」是辅助：章节内的蛇形卡片与控制流连线，用来看分支结构。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button, Input, Segmented, Select, Space, Spin, Tag, Tooltip } from 'antd';
import { GitBranch, Maximize2, Minus, Network, Plus } from 'lucide-react';

import { getStoryBlueprint, getStoryBlueprintReadiness } from '../api';
import { useT } from '../i18n';
import type { TextKey } from '../i18n';
import type { AppState } from '../useAppState';
import type {
  StoryBlueprintChapter,
  StoryBlueprintReadiness,
  StoryBlueprintResponse,
  StoryBlueprintStage,
  StoryBlueprintStatus,
  View,
  Viewport,
} from '../types';
import { Banner, PageHeader } from '../ui';
import type { PageKey } from '../nav';
import { BlueprintCanvas } from './storyBlueprint/BlueprintCanvas';
import { LabelDetailPanel } from './storyBlueprint/LabelDetailPanel';
import { OutlineView } from './storyBlueprint/OutlineView';
import { resolveBlueprintErrorView } from './storyBlueprint/storyBlueprintErrorView.mjs';
import {
  buildSegments,
  centerOn,
  clampScale,
  clampView,
  colsForWidth,
  fitAllView,
  filterNodes,
  fitView,
  formatPercent,
  layoutNodes,
  visibleIds,
} from './storyBlueprint/storyBlueprintView.mjs';

const STATUS_KEYS = {
  done: 'story_blueprint_status_done',
  part: 'story_blueprint_status_part',
  todo: 'story_blueprint_status_todo',
} as const;

type Mode = 'outline' | 'map';

/** 体检没过时每种情况对应的引导：说清原因，并给一个能直接解决问题的按钮。 */
const BLOCKED_STAGE: Record<
  Exclude<StoryBlueprintStage, 'ready'>,
  { title: TextKey; body: TextKey; action: PageKey; actionLabel: TextKey }
> = {
  unbound: {
    title: 'story_blueprint_unbound_title',
    body: 'story_blueprint_unbound_body',
    action: 'project',
    actionLabel: 'story_blueprint_bind_project',
  },
  no_game: {
    title: 'story_blueprint_no_game_title',
    body: 'story_blueprint_no_game_body',
    action: 'project',
    actionLabel: 'story_blueprint_reselect',
  },
  packed: {
    title: 'story_blueprint_packed_title',
    body: 'story_blueprint_packed_body',
    action: 'pack-unpack',
    actionLabel: 'story_blueprint_packed_action',
  },
  no_script: {
    title: 'story_blueprint_no_script_title',
    body: 'story_blueprint_no_script_body',
    action: 'project',
    actionLabel: 'story_blueprint_reselect',
  },
};

export function StoryBlueprintPage(props: {
  state: AppState;
  onNavigate?: (page: PageKey) => void;
}) {
  const { onNavigate } = props;
  const t = useT();
  const [snapshot, setSnapshot] = useState<StoryBlueprintResponse | null>(null);
  const [loading, setLoading] = useState(true);
  /** 原始错误（ApiError / Error / 任意值）：交给 resolveBlueprintErrorView 决定怎么显示。 */
  const [error, setError] = useState<unknown>(null);
  const [readiness, setReadiness] = useState<StoryBlueprintReadiness | null>(null);
  const [mode, setMode] = useState<Mode>('outline');
  const [chapterId, setChapterId] = useState('');
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<StoryBlueprintStatus | ''>('');
  const [view, setView] = useState<View>({ x: 0, y: 0, scale: 1 });
  const [viewport, setViewport] = useState<Viewport>({ width: 0, height: 0 });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [focusId, setFocusId] = useState<string | null>(null);
  const fittedRef = useRef('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setReadiness(null);
    try {
      // 先体检再扫全量：没绑工程/没解包时扫描必然空跑一遍，还看不出原因。
      const state = await getStoryBlueprintReadiness();
      setReadiness(state);
      if (state.stage !== 'ready') {
        setSnapshot(null);
        setLoading(false);
        return;
      }
      const data = await getStoryBlueprint();
      setSnapshot(data);
      setChapterId((previous) => {
        if (previous && data.chapters.some((chapter) => chapter.id === previous)) return previous;
        return largestChapter(data.chapters);
      });
    } catch (cause) {
      // readiness 与 snapshot 共用这个兜底：任何一个失败都进错误态，
      // 由下面的 errorView 分流成「接口缺失引导卡」或「原样报错」。
      setSnapshot(null);
      setError(cause);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const chapters = snapshot?.chapters ?? [];
  const activeChapter = chapters.find((chapter) => chapter.id === chapterId) ?? chapters[0];
  const chapterNodes = useMemo(
    () => (snapshot ? snapshot.nodes.filter((node) => node.chapter === activeChapter?.id) : []),
    [snapshot, activeChapter?.id],
  );
  const filtering = query.trim() !== '' || statusFilter !== '';
  const filteredNodes = useMemo(
    () => (filtering ? chapterNodes.filter((node) => filterNodes([node], { query, status: statusFilter }).ids.size > 0) : chapterNodes),
    [chapterNodes, query, statusFilter, filtering],
  );
  const filteredIds = useMemo(
    () => (filtering ? new Set(filteredNodes.map((node) => node.id)) : null),
    [filteredNodes, filtering],
  );

  // 列数跟着视口宽度走：卡片始终以 1:1 铺满，不再把整章缩小塞进视口。
  const columns = viewport.width > 0 ? colsForWidth(viewport.width) : 8;
  const layout = useMemo(() => layoutNodes(chapterNodes, { cols: columns }), [chapterNodes, columns]);
  const chapterIds = useMemo(() => new Set(chapterNodes.map((node) => node.id)), [chapterNodes]);
  const chapterEdges = useMemo(
    () =>
      snapshot
        ? snapshot.edges.filter((edge) => chapterIds.has(edge.from) && chapterIds.has(edge.to))
        : [],
    [snapshot, chapterIds],
  );
  const segments = useMemo(
    () => buildSegments(chapterNodes, chapterEdges, layout.positions),
    [chapterNodes, chapterEdges, layout.positions],
  );
  const externalOut = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const edge of snapshot?.edges ?? []) {
      if (!chapterIds.has(edge.from) || chapterIds.has(edge.to)) continue;
      counts[edge.from] = (counts[edge.from] ?? 0) + 1;
    }
    return counts;
  }, [snapshot, chapterIds]);

  const culledIds = useMemo(
    () => (viewport.width > 0 && viewport.height > 0 ? visibleIds(layout.positions, view, viewport) : null),
    [layout.positions, view, viewport],
  );
  const visible = filteredIds ?? culledIds;

  // 切章节或第一次量到视口时适应屏幕；用户后续的平移缩放不被覆盖。
  useEffect(() => {
    if (mode !== 'map' || chapterNodes.length === 0 || viewport.width <= 0) return;
    const key = `${activeChapter?.id}|${viewport.width}x${viewport.height}`;
    if (fittedRef.current === key) return;
    fittedRef.current = key;
    setView(fitView(layout.bounds, viewport));
  }, [mode, activeChapter?.id, chapterNodes.length, layout.bounds, viewport]);

  // 详情里点了跳转：同章节居中（关系图）或直接选中；跨章节先切章节。
  useEffect(() => {
    if (!focusId) return;
    const target = snapshot?.nodes.find((node) => node.id === focusId);
    if (!target) {
      setFocusId(null);
      return;
    }
    if (target.chapter !== activeChapter?.id) {
      setChapterId(target.chapter);
      return;
    }
    if (mode === 'map') {
      const position = layout.positions[focusId];
      if (!position) return;
      setView(clampView(centerOn(position, viewport, Math.max(0.9, view.scale)), layout.bounds, viewport));
    }
    setSelectedId(focusId);
    setFocusId(null);
  }, [focusId, snapshot, activeChapter?.id, layout.positions, viewport, mode, view.scale, layout.bounds]);

  const selected = snapshot?.nodes.find((node) => node.id === selectedId) ?? null;
  /**
   * 错误态分流：后端没有剧情蓝图接口（旧进程 / 没重启）时给中文引导卡，
   * 别的错误保持原样把后端原文上屏 —— 真实原因不能被文案盖掉。
   */
  const errorView = resolveBlueprintErrorView(error);
  /** 体检没过时，页面不画空图，而是说清楚卡在哪一步、点哪里能解决。 */
  const blocked = readiness && readiness.stage !== 'ready' ? BLOCKED_STAGE[readiness.stage] : null;
  const fromCache = snapshot?.stats.progress_source === 'cache';
  const chapterDone = (chapter: StoryBlueprintChapter) => chapter.progress;
  const chapterLabel = (chapter: StoryBlueprintChapter) =>
    `${chapter.id}（${chapter.labels} · ${formatPercent(chapterDone(chapter), chapter.say)}）`;

  const zoomBy = (factor: number) => {
    setView((previous) => {
      const scale = clampScale(previous.scale * factor);
      if (scale === previous.scale) return previous;
      const ratio = scale / previous.scale;
      const centerX = viewport.width / 2;
      const centerY = viewport.height / 2;
      return clampView(
        {
          x: centerX - (centerX - previous.x) * ratio,
          y: centerY - (centerY - previous.y) * ratio,
          scale,
        },
        layout.bounds,
        viewport,
      );
    });
  };

  const selectChapter = (id: string) => {
    setChapterId(id);
    setSelectedId(null);
    setFocusId(null);
    fittedRef.current = '';
  };

  const statsText = t(fromCache ? 'story_blueprint_stats_cache' : 'story_blueprint_stats')
    .replace('{chapters}', String(snapshot?.stats.chapters ?? 0))
    .replace('{labels}', String(snapshot?.stats.labels ?? 0))
    .replace('{say}', String(snapshot?.stats.say_lines ?? 0))
    .replace('{zh}', String(fromCache ? snapshot?.stats.cache_lines ?? 0 : snapshot?.stats.zh_lines ?? 0));

  return (
    <div className="rb-page rb-blueprint">
      <PageHeader title={t('app_story_blueprint_page')} description={t('story_blueprint_page_desc')} />

      {loading ? (
        <div className="rb-blueprint-state">
          <Spin size="small" />
          <span>{t('story_blueprint_loading')}</span>
        </div>
      ) : errorView ? (
        errorView.kind === 'api_missing' ? (
          <div className="rb-blueprint-state">
            <strong>{t(errorView.titleKey)}</strong>
            <p>{t(errorView.bodyKey)}</p>
            <Button onClick={() => void load()}>{t('story_blueprint_retry')}</Button>
          </div>
        ) : (
          <div className="rb-blueprint-state">
            <Banner tone="warning">{errorView.message}</Banner>
            <Button onClick={() => void load()}>{t('story_blueprint_retry')}</Button>
          </div>
        )
      ) : blocked ? (
        <div className="rb-blueprint-state">
          <strong>{t(blocked.title)}</strong>
          <p>{t(blocked.body).replace('{rpa}', String(readiness?.rpa_files ?? 0))}</p>
          <Space>
            <Button type="primary" onClick={() => onNavigate?.(blocked.action)}>
              {t(blocked.actionLabel)}
            </Button>
            <Button onClick={() => void load()}>{t('story_blueprint_retry')}</Button>
          </Space>
        </div>
      ) : snapshot && activeChapter ? (
        <div className={`rb-blueprint-body${selected ? ' has-drawer' : ''}`}>
          <aside className="rb-blueprint-side">
            <p className="rb-blueprint-overview">
              {statsText}
              <span className="rb-blueprint-source">
                {fromCache ? t('story_blueprint_progress_cache') : t('story_blueprint_progress_tl')}
              </span>
            </p>
            <ul className="rb-blueprint-chapters">
              {chapters.map((chapter) => (
                <li key={chapter.id}>
                  <button
                    type="button"
                    className="rb-blueprint-chapter"
                    data-active={chapter.id === activeChapter.id || undefined}
                    title={chapterLabel(chapter)}
                    onClick={() => selectChapter(chapter.id)}
                  >
                    <span className="rb-blueprint-chapter-name">{chapter.id}</span>
                    <span className="rb-blueprint-chapter-meta">
                      {chapter.labels} · {formatPercent(chapterDone(chapter), chapter.say)}
                    </span>
                    <span className="rb-blueprint-chapter-bar" aria-hidden>
                      <span
                        style={{ width: `${chapter.say > 0 ? (chapterDone(chapter) / chapter.say) * 100 : 0}%` }}
                      />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          <section className="rb-blueprint-main">
            <div className="rb-blueprint-toolbar">
              <Segmented
                size="small"
                value={mode}
                onChange={(value) => setMode(value as Mode)}
                options={[
                  { value: 'outline', label: t('story_blueprint_view_outline'), icon: <GitBranch size={13} /> },
                  { value: 'map', label: t('story_blueprint_view_map'), icon: <Network size={13} /> },
                ]}
              />
              <Input
                allowClear
                value={query}
                placeholder={t('story_blueprint_search_placeholder')}
                onChange={(event) => setQuery(event.target.value)}
              />
              <Select
                value={statusFilter}
                onChange={(value) => setStatusFilter(value as StoryBlueprintStatus | '')}
                options={[
                  { value: '', label: t('story_blueprint_all_status') },
                  { value: 'done', label: t('story_blueprint_status_done') },
                  { value: 'part', label: t('story_blueprint_status_part') },
                  { value: 'todo', label: t('story_blueprint_status_todo') },
                ]}
              />
              <Select
                value={activeChapter.id}
                onChange={selectChapter}
                options={chapters.map((chapter) => ({ value: chapter.id, label: chapterLabel(chapter) }))}
              />
              {mode === 'map' ? (
                <>
                  <Space size={4}>
                    <Tooltip title={t('story_blueprint_fit_all')}>
                      <Button
                        icon={<Maximize2 size={15} />}
                        onClick={() => setView(fitAllView(layout.bounds, viewport))}
                      />
                    </Tooltip>
                    <Tooltip title={t('story_blueprint_fit')}>
                      <Button size="small" type="text" onClick={() => setView(fitView(layout.bounds, viewport))}>
                        1:1
                      </Button>
                    </Tooltip>
                    <Tooltip title={t('story_blueprint_zoom_out')}>
                      <Button icon={<Minus size={15} />} onClick={() => zoomBy(1 / 1.2)} />
                    </Tooltip>
                    <Tooltip title={t('story_blueprint_zoom_in')}>
                      <Button icon={<Plus size={15} />} onClick={() => zoomBy(1.2)} />
                    </Tooltip>
                    <span className="rb-blueprint-zoom">{Math.round(view.scale * 100)}%</span>
                  </Space>
                  <div className="rb-blueprint-legend">
                    <span data-kind="menu">{t('story_blueprint_legend_menu')}</span>
                    <span data-kind="jump">{t('story_blueprint_legend_jump')}</span>
                  </div>
                </>
              ) : (
                <span className="rb-blueprint-toolbar-note">
                  {t('story_blueprint_list_count')
                    .replace('{shown}', String(filteredNodes.length))
                    .replace('{total}', String(chapterNodes.length))}
                </span>
              )}
            </div>

            {chapterNodes.length === 0 ? (
              <div className="rb-blueprint-state">{t('story_blueprint_empty_chapter')}</div>
            ) : mode === 'outline' ? (
              <>
                <div className="rb-outline-hint">{t('story_blueprint_outline_hint')}</div>
                <OutlineView
                  nodes={filteredNodes}
                  allNodes={snapshot.nodes}
                  edges={snapshot.edges}
                  chapters={chapters}
                  selectedId={selectedId}
                  onSelect={(id) => setSelectedId(id)}
                  onNavigate={(chapter, id) => {
                    if (chapter !== activeChapter?.id) setChapterId(chapter);
                    setSelectedId(id);
                    setFocusId(id);
                  }}
                />
              </>
            ) : (
              <BlueprintCanvas
                nodes={chapterNodes}
                segments={segments}
                positions={layout.positions}
                bounds={layout.bounds}
                visible={visible}
                externalOut={externalOut}
                view={view}
                onViewChange={setView}
                onViewport={setViewport}
                onOpenNode={(id) => setSelectedId(id)}
                activeId={selectedId}
                statusLabel={(status) => t(STATUS_KEYS[status])}
              />
            )}
          </section>

          {selected ? (
            <LabelDetailPanel
              node={selected}
              nodes={snapshot.nodes}
              edges={snapshot.edges}
              onClose={() => setSelectedId(null)}
              onOpen={(id) => setFocusId(id)}
            />
          ) : null}
        </div>
      ) : (
        <div className="rb-blueprint-state">
          <Tag>{t('story_blueprint_empty_chapter')}</Tag>
        </div>
      )}
    </div>
  );
}

function largestChapter(chapters: StoryBlueprintChapter[]): string {
  let best = chapters[0]?.id ?? '';
  let size = -1;
  for (const chapter of chapters) {
    // 默认落在「台词最多」的章节：工具文件（script/bol/bom 之类）label 可能更多，
    // 但对汉化者来说没有剧情价值。
    const weight = chapter.say > 0 ? chapter.say : chapter.labels;
    if (weight > size) {
      size = weight;
      best = chapter.id;
    }
  }
  return best;
}
