/**
 * 关系时间线：伙伴 × 剧本文件的矩阵热力图。
 *
 * 回答的是「这条关系在哪一章出现、贯穿全篇还是只露过一面」，
 * 所以 X 轴是自然序排好的剧本文件、Y 轴是概览里同一批伙伴（同一顺序）。
 *
 * 用 SVG 而不是 CSS grid：格子数量是 26 行 × 最多 32 列，SVG 只发一个节点树、
 * 缩放时线框不糊，而且首现描边、悬停高亮这些都能直接用图形元素表达。
 */
import { useCallback, useMemo, useRef, useState } from 'react';

import { SvgAvatar } from './GraphAvatar';
import { categorySpec } from './relationGraph';
import {
  buildTimelineModel,
  type OverlayGroup,
  type OverlayPartner,
  type TimelineCell,
  type TimelineRow,
} from './relationOverlayView.mjs';

interface Props {
  groups: OverlayGroup[];
  partners: OverlayPartner[];
  showRejected: boolean;
  /** 选中的伙伴 id：与概览共用同一个 pick，右栏详情跟着切。 */
  selected: string | null;
  onPick: (id: string) => void;
}

interface TipState {
  left: number;
  top: number;
  cell: TimelineCell;
  partnerName: string;
}

/* ---- 矩阵几何：改这里就能整体调松紧 ---- */
const ROW_H = 20;
const HEAD_W = 172;
const COL_W = 46;
const TOP_H = 42;
const CELL = 17;
const TIP_WIDTH = 236;

/** 格子颜色深浅按 count / maxCount 开方，小数值也看得见。 */
function cellOpacity(count: number, maxCount: number): number {
  const ratio = Math.sqrt(Math.max(0, count) / Math.max(1, maxCount));
  return 0.3 + 0.62 * Math.min(1, ratio);
}

/** 列头长名截断：保留头尾，中间省略，悬停看全名。 */
function clipLabel(value: string, max = 9): string {
  const text = String(value ?? '').trim();
  return text.length > max ? `${text.slice(0, max - 2)}…${text.slice(-1)}` : text;
}

/**
 * 格子里的数字颜色：色块浅时用深字、深时用白字，
 * 阈值取在 fillOpacity 0.55 附近，两类格子都能读。
 */
function countColor(opacity: number): string {
  return opacity >= 0.55 ? '#FFFFFF' : '#3F3F46';
}

export function RelationTimeline({ groups, partners, showRejected, selected, onPick }: Props) {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [tip, setTip] = useState<TipState | null>(null);

  const model = useMemo(
    () => buildTimelineModel({ groups, partners, showRejected }),
    [groups, partners, showRejected],
  );

  const width = HEAD_W + model.columns.length * COL_W + 16;
  const height = TOP_H + model.rows.length * ROW_H + 26;

  const cellAt = useCallback((row: TimelineRow, column: { file: string }) => row.cells.get(column.file) ?? null, []);

  const hoverOn = useCallback((event: { currentTarget: Element }, cell: TimelineCell, partnerName: string) => {
    const stage = stageRef.current;
    if (!stage) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const box = stage.getBoundingClientRect();
    let left = rect.left - box.left + rect.width + 10;
    let top = rect.top - box.top - 8;
    if (left + TIP_WIDTH > box.width - 8) left = rect.left - box.left - TIP_WIDTH - 10;
    if (left < 8) left = 8;
    if (top < 8) top = 8;
    if (top + 130 > box.height) top = Math.max(8, box.height - 130);
    setTip({ left, top, cell, partnerName });
  }, []);

  const hoverOff = useCallback(() => setTip(null), []);

  if (!model.rows.length || !model.columns.length) {
    return (
      <div className="rb-rel-timeline" ref={stageRef}>
        <p className="rb-rel-overlay-empty">
          还没有按剧本文件切分的证据。跑一次角色扫描（后端要能给出每章命中）之后，这里会按章排出矩阵。
        </p>
      </div>
    );
  }

  return (
    <div className="rb-rel-timeline" ref={stageRef}>
      <div className="rb-rel-timeline-scroll">
        <svg
          className="rb-rel-timeline-svg"
          viewBox={`0 0 ${width} ${height}`}
          width={width}
          height={height}
          onClick={() => setTip(null)}
        >
          {/* 列底纹：交替淡色，代替贯穿全高的竖线，扫行时不晃眼。 */}
          <g>
            {model.columns.map((column) => {
              if (column.order % 2 === 0) return null;
              const x = HEAD_W + column.order * COL_W;
              return (
                <rect
                  key={`zebra-${column.file}`}
                  x={x}
                  y={TOP_H - 10}
                  width={COL_W}
                  height={model.rows.length * ROW_H + 4}
                  fill="var(--rb-surface-subtle)"
                />
              );
            })}
          </g>

          {/* 列头：文件名去 .rpy，长名截断。 */}
          <g>
            {model.columns.map((column) => {
              const x = HEAD_W + column.order * COL_W + COL_W / 2;
              return (
                <g key={`col-${column.file}`}>
                  <text
                    className="rb-rel-timeline-col"
                    x={x}
                    y={TOP_H - 28}
                    textAnchor="middle"
                    fontSize={10.5}
                  >
                    {clipLabel(column.label)}
                  </text>
                  <title>{column.file}</title>
                </g>
              );
            })}
            <line x1={0} y1={TOP_H - 8} x2={width - 8} y2={TOP_H - 8} stroke="var(--rb-border)" strokeWidth={1} />
          </g>

          {/* 行：行头（头像 + 名字 + 类别色条）+ 格子。 */}
          <g>
            {model.rows.map((entry, rowIndex) => {
              const y = TOP_H + rowIndex * ROW_H;
              const centerY = y + ROW_H / 2;
              const isSelected = selected === entry.partner.id;
              const dim = Boolean(selected) && !isSelected;
              const color = categorySpec(entry.partner.primary?.category ?? 'other').color;
              return (
                <g key={`row-${entry.partner.id}`} className={`rb-rel-timeline-row${dim ? ' is-dim' : ''}`}>
                  {/* 行头背景：选中时整条高亮。 */}
                  <rect
                    x={0}
                    y={y}
                    width={HEAD_W}
                    height={ROW_H}
                    fill={isSelected ? 'var(--rb-accent-surface)' : 'transparent'}
                    onClick={() => onPick(entry.partner.id)}
                  />
                  {/* 类别色条。 */}
                  <rect x={2} y={y + 4} width={3} height={ROW_H - 8} rx={1.5} fill={color} />
                  <SvgAvatar
                    card={{ id: entry.partner.id, name: entry.partner.name, avatar: entry.partner.card.avatar }}
                    cx={22}
                    cy={centerY}
                    r={9}
                    color={color}
                  />
                  <text
                    className="rb-rel-timeline-name"
                    x={38}
                    y={centerY + 4}
                    fontSize={11.5}
                    onClick={() => onPick(entry.partner.id)}
                  >
                    {clipLabel(entry.partner.name, 14)}
                  </text>
                  <text className="rb-rel-timeline-total" x={HEAD_W - 8} y={centerY + 4} textAnchor="end" fontSize={10}>
                    {entry.total}
                  </text>

                  {model.columns.map((column) => {
                    const cell = cellAt(entry, column);
                    if (!cell) return null;
                    const x = HEAD_W + column.order * COL_W + COL_W / 2;
                    const first = entry.firstFile === column.file;
                    const opacity = cellOpacity(cell.count, model.maxCount);
                    return (
                      <g key={`cell-${entry.partner.id}-${column.file}`}>
                        <rect
                          className={`rb-rel-timeline-cell${first ? ' is-first' : ''}`}
                          x={x - CELL / 2}
                          y={centerY - CELL / 2}
                          width={CELL}
                          height={CELL}
                          rx={3}
                          fill={color}
                          fillOpacity={opacity}
                          stroke={first ? 'var(--rb-text-primary)' : 'transparent'}
                          strokeOpacity={first ? 0.55 : 0}
                          strokeWidth={first ? 1.4 : 0}
                          onClick={() => onPick(entry.partner.id)}
                          onMouseEnter={(event) => hoverOn(event, cell, entry.partner.name)}
                          onMouseLeave={hoverOff}
                        />
                        <text
                          className="rb-rel-timeline-count"
                          x={x}
                          y={centerY + 3.6}
                          textAnchor="middle"
                          fontSize={cell.count > 99 ? 8 : 9.5}
                          fill={countColor(opacity)}
                        >
                          {cell.count > 99 ? '99+' : cell.count}
                        </text>
                      </g>
                    );
                  })}
                </g>
              );
            })}
          </g>
        </svg>
      </div>

      <div className="rb-rel-timeline-foot">
        <span>{`${model.rows.length} 个伙伴 × ${model.columns.length} 个剧本文件`}</span>
        <span className="rb-rel-timeline-legend">
          <i />
          描边 = 该关系首次出现的章节
        </span>
        <span className="rb-rel-overlay-note">只显示有源码证据的剧本文件</span>
      </div>

      {tip ? (
        <div className="rb-rel-tip" style={{ left: tip.left, top: tip.top, width: TIP_WIDTH }}>
          <div className="rb-rel-tip-top">
            <span className="rb-rel-tip-name">{tip.partnerName}</span>
            <span className="rb-rel-tip-meta">{`${tip.cell.count} 次`}</span>
          </div>
          <div className="rb-rel-tip-rel">
            <span>{tip.cell.file}</span>
            {tip.cell.line > 0 ? <span>{`第 ${tip.cell.line} 行`}</span> : null}
          </div>
          {tip.cell.samples.length ? (
            <div className="rb-rel-tip-evi">
              <em>证据 · </em>
              {tip.cell.samples.slice(0, 2).map((sample, position) => (
                <div key={`${sample}-${position}`}>{clipLabel(sample, 46)}</div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
