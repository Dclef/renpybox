/**
 * 剧情蓝图画布：章节内全部 label 的蛇形卡片 + 控制流连线。
 *
 * 只渲染「视口 + buffer」内的卡片（positions 始终全量），平移/缩放时按需增删；
 * 连线随卡片一起视图口裁剪，避免 300+ 条 SVG 线段拖慢拖动。
 * 只画真实控制流：菜单选项 jump 是实线，label 结尾 jump 是虚线；跨章节边用强调色。
 */
import { useEffect, useRef } from 'react';

import { blueprintAssetUrl } from '../../api';
import { useT } from '../../i18n';
import type {
  Segment,
  StoryBlueprintNode,
  StoryBlueprintStatus,
  View,
  Viewport,
} from '../../types';
import { LAYOUT, clampScale, clampView, isPlaceholder, isShowImage, nodeHeading } from './storyBlueprintView.mjs';

interface Props {
  nodes: StoryBlueprintNode[];
  segments: Segment[];
  positions: Record<string, { x: number; y: number }>;
  bounds: { width: number; height: number };
  visible: Set<string> | null;
  externalOut?: Record<string, number>;
  view: View;
  onViewChange: (view: View) => void;
  onViewport: (viewport: Viewport) => void;
  onOpenNode: (id: string) => void;
  activeId: string | null;
  statusLabel: (status: StoryBlueprintStatus) => string;
}

const EDGE_COLOR: Record<Segment['kind'], string> = {
  menu: 'var(--rb-accent)',
  jump: 'var(--rb-text-tertiary)',
};

export function BlueprintCanvas(props: Props) {
  const { nodes, segments, positions, bounds, visible, externalOut, view, onViewChange, onViewport, onOpenNode, activeId, statusLabel } = props;
  const t = useT();
  const hostRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ pointerId: number; startX: number; startY: number; originX: number; originY: number } | null>(null);
  const viewRef = useRef(view);
  viewRef.current = view;
  const viewportRef = useRef({ width: 0, height: 0 });
  const boundsRef = useRef(bounds);
  boundsRef.current = bounds;

  // 视口尺寸交给页面做裁剪与「适应屏幕」；容器尺寸变化时重报。
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const report = () => {
      viewportRef.current = { width: host.clientWidth, height: host.clientHeight };
      onViewport({ width: host.clientWidth, height: host.clientHeight });
    };
    report();
    const observer = new ResizeObserver(report);
    observer.observe(host);
    return () => observer.disconnect();
  }, [onViewport]);

  // 滚轮必须非 passive 才能阻止页面滚动：原生监听，不用 React onWheel。
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const onWheel = (event: WheelEvent) => {
      // 默认：滚轮纵向平移（章节内容按 1:1 铺满，纵向滚动就是唯一自然的方向盘）。
      // 按住 Ctrl/⌘ 才是缩放；缩放始终以指针为中心，过 clampView 不会把内容推出视口。
      event.preventDefault();
      const current = viewRef.current;
      const rect = host.getBoundingClientRect();
      if (event.ctrlKey || event.metaKey) {
        const pointerX = event.clientX - rect.left;
        const pointerY = event.clientY - rect.top;
        const factor = Math.exp(-event.deltaY * 0.0016);
        const scale = clampScale(current.scale * factor);
        const ratio = scale / current.scale;
        onViewChange(
          clampView(
            {
              x: pointerX - (pointerX - current.x) * ratio,
              y: pointerY - (pointerY - current.y) * ratio,
              scale,
            },
            boundsRef.current,
            viewportRef.current,
          ),
        );
        return;
      }
      onViewChange(
        clampView(
          { x: current.x - event.deltaX, y: current.y - event.deltaY, scale: current.scale },
          boundsRef.current,
          viewportRef.current,
        ),
      );
    };
    host.addEventListener('wheel', onWheel, { passive: false });
    return () => host.removeEventListener('wheel', onWheel);
  }, [onViewChange]);

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    const target = event.target as HTMLElement;
    if (target.closest('[data-card]')) return;
    event.preventDefault();
    hostRef.current?.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      originX: view.x,
      originY: view.y,
    };
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    onViewChange(
      clampView(
        {
          x: drag.originX + event.clientX - drag.startX,
          y: drag.originY + event.clientY - drag.startY,
          scale: view.scale,
        },
        bounds,
        viewportRef.current,
      ),
    );
  };

  const endDrag = (event: React.PointerEvent<HTMLDivElement>) => {
    if (dragRef.current?.pointerId !== event.pointerId) return;
    dragRef.current = null;
    hostRef.current?.releasePointerCapture?.(event.pointerId);
  };

  const rendered = nodes.filter((node) => !visible || visible.has(node.id));

  return (
    <div
      className="rb-blueprint-canvas"
      ref={hostRef}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
    >
      <div
        className="rb-blueprint-stage"
        style={{
          width: Math.max(bounds.width, 1),
          height: Math.max(bounds.height, 1),
          transform: `translate(${view.x}px, ${view.y}px) scale(${view.scale})`,
        }}
      >
        <svg
          className="rb-blueprint-edges"
          width={Math.max(bounds.width, 1)}
          height={Math.max(bounds.height, 1)}
          aria-hidden
        >
          {segments.map((segment) => (
            <g key={segment.key} data-kind={segment.kind} data-cross={segment.cross || undefined}>
              <line
                x1={segment.x1}
                y1={segment.y1}
                x2={segment.x2}
                y2={segment.y2}
                stroke={segment.cross ? 'var(--rb-warning)' : EDGE_COLOR[segment.kind]}
                strokeWidth={segment.kind === 'menu' ? 1.6 : 1.2}
                strokeDasharray={segment.kind === 'jump' ? '5 4' : undefined}
                opacity={segment.kind === 'menu' ? 0.75 : 0.5}
              />
              {segment.kind === 'menu' && segment.option_zh ? (
                <text
                  x={(segment.x1 + segment.x2) / 2}
                  y={(segment.y1 + segment.y2) / 2 - 4}
                  textAnchor="middle"
                  className="rb-blueprint-edge-label"
                >
                  {truncate(segment.option_zh, 12)}
                </text>
              ) : null}
            </g>
          ))}
        </svg>

        {rendered.map((node) => {
          const position = positions[node.id];
          if (!position) return null;
          const status = node.status;
          const placeholder = isPlaceholder(node) || node.placeholder;
          const title = nodeHeading(node).title;
          return (
            <div
              key={node.id}
              data-card
              role="button"
              tabIndex={0}
              className="rb-blueprint-card"
              data-status={status}
              data-placeholder={placeholder || undefined}
              data-active={activeId === node.id || undefined}
              style={{
                left: position.x,
                top: position.y,
                width: LAYOUT.cardW,
                height: LAYOUT.cardH,
              }}
              onClick={(event) => {
                event.stopPropagation();
                onOpenNode(node.id);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter' || event.key === ' ') {
                  event.preventDefault();
                  onOpenNode(node.id);
                }
              }}
            >
              <div className="rb-blueprint-thumb">
                {node.image ? (
                  <img
                    src={blueprintAssetUrl(node.image.path)}
                    alt=""
                    loading="lazy"
                    decoding="async"
                    draggable={false}
                  />
                ) : view.scale >= 0.7 ? (
                  <span className="rb-blueprint-noimg">{t('story_blueprint_no_image')}</span>
                ) : null}
                {placeholder ? <span className="rb-blueprint-ghost">{t('story_blueprint_placeholder')}</span> : null}
                {isShowImage(node.image) ? (
                  <span
                    className="rb-blueprint-source"
                    title={t('story_blueprint_show_source_hint')}
                  >
                    {t('story_blueprint_show_source')}
                  </span>
                ) : null}
                {externalOut?.[node.id] ? (
                  <span className="rb-blueprint-exit" title={t('story_blueprint_exit_hint')}>
                    ⇢{externalOut[node.id]}
                  </span>
                ) : null}
                <span className="rb-blueprint-badge" data-status={status}>
                  {statusLabel(status)}
                </span>
              </div>
              <div className="rb-blueprint-card-body">
                <span className="rb-blueprint-card-title" title={title}>{title}</span>
                <span className="rb-blueprint-card-meta">
                  {node.file}:{node.line}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function truncate(text: string, limit: number): string {
  const value = String(text ?? '');
  return value.length <= limit ? value : `${value.slice(0, limit)}…`;
}
