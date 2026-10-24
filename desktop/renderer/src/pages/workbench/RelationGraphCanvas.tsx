/**
 * 关系图谱画布：焦点视图（中心角色 + 环绕伙伴），原生 SVG，不引入图表库。
 *
 * 布局照 docs/internal/2026-10-24/plan/graph-v3.tpl.html：伙伴按角度均分在一个圆环上，不做力导向。
 * 三条最容易写反的规则集中在这里处理：
 * 1. 箭头逐端点判断：焦点自己写出的关系 → 箭头落在伙伴那端；伙伴写出的 → 落在焦点那端；
 *    两个方向都有 → 两头都有箭头。
 * 2. 同一个关系词只画一次文字胶囊（后面同名边只画线 + 箭头，悬停用 <title> 补全），
 *    胶囊上带「×N」表示这张图里同名关系有几条，避免重复写八次。
 * 3. 一条关系都没有时只画这一个人 + 两行说明，不留空白画布。
 */
import { useLayoutEffect, useRef, useState } from 'react';

import { SvgAvatar } from './GraphAvatar';
import {
  categorySpec,
  hitCount,
  lineCountOf,
  pairRowBetween,
  RELATION_CATEGORIES,
  type PartnerEdge,
  type RelationRowRef,
  type WeakPartner,
  type WorkbenchCharacter,
} from './relationGraph';

/** 圆环上最多画多少人。
 *
 * 12 个在这个尺寸下必然互相压住姓名条：一圈周长约 2π·176 ≈ 1100px，
 * 平分给 12 个只剩 92px，而一块姓名牌就要 60~115px。留 8 个位置，
 * 一圈 136px 才排得开；剩下的伙伴在右侧列表里都能点到。
 */
const MAX_PARTNERS = 8;
const CENTER_RADIUS = 46;
const PARTNER_RADIUS = 27;
/** 线从中心头像外圈起笔、到伙伴头像外圈收笔，箭头才不会被头像盖住。 */
const LINE_START = 48;
const LINE_END = 30;

interface Point { x: number; y: number }

type RingItem =
  | { kind: 'relation'; card: WorkbenchCharacter; edge: PartnerEdge }
  | { kind: 'weak'; card: WorkbenchCharacter; weight: number };

function namePlateWidth(text: string): number {
  return Math.max(46, text.length * 12 + 18);
}

function clipName(name: string): string {
  return name.length > 9 ? `${name.slice(0, 8)}…` : name;
}

/** 姓名条：头像下面那块小牌子，中心与伙伴共用。above=true 时挂在头像上方（朝外的一侧）。 */
function NamePlate(props: { name: string; cx: number; top: number }) {
  const text = clipName(props.name || '未命名角色');
  const width = namePlateWidth(text);
  return (
    <>
      <rect className="rb-graph-name-box" x={props.cx - width / 2} y={props.top} width={width} height={22} rx={5} />
      <text className="rb-graph-name-text" x={props.cx} y={props.top + 15} textAnchor="middle">{text}</text>
    </>
  );
}

/** 圆环节点的姓名条一律朝外（上半圈挂上方、下半圈挂下方），把内侧那条带宽留给关系胶囊。 */
function plateTop(point: Point, cy: number, radius: number): number {
  return point.y <= cy ? point.y - radius - 6 - 22 : point.y + radius + 6;
}

/** 一条关系边：颜色取类别色（固定值，不跟主题），粗细按命中次数。 */
function RelationEdge(props: {
  edge: PartnerEdge;
  point: Point;
  cx: number;
  cy: number;
  rows: RelationRowRef[];
  markerId: (category: string) => string;
  labelled: boolean;
  tally: number;
}) {
  const { edge, point, cx, cy, rows, markerId, labelled, tally } = props;
  const color = categorySpec(edge.category).color;
  const angle = Math.atan2(point.y - cy, point.x - cx);
  const startX = cx + Math.cos(angle) * LINE_START;
  const startY = cy + Math.sin(angle) * LINE_START;
  const endX = point.x - Math.cos(angle) * LINE_END;
  const endY = point.y - Math.sin(angle) * LINE_END;
  // 这就是那三条容易写反的规则里的第 1 条：逐端点判断，而不是整条边一个方向。
  const focusSpoke = edge.own.length > 0;
  const partnerSpoke = edge.incoming.length > 0;
  const hits = hitCount(edge.own[0] ?? edge.incoming[0], rows);
  const lineWidth = 1.6 + Math.min(2.4, Math.log2(Math.max(hits, 1)) * 0.55);
  const marker = markerId(edge.category);
  // 同一个关系词只标一次：第二条同名的边只留线 + 箭头，靠 title 补信息。
  const labelText = edge.label || '未写明称谓';
  const shown = tally > 1 ? `${edge.label || '关系'} ×${tally}` : labelText;
  const labelWidth = Math.max(32, shown.length * 11 + 12);
  // 胶囊沿连线摆，两头都要让开：内侧让开中心头像和它下面的姓名条，外侧让开伙伴头像。
  // 姓名条挂在圆环外侧（plateTop），所以内侧这条带子可以整条用来放胶囊。
  const dx = point.x - cx;
  const dy = point.y - cy;
  const distance = Math.hypot(dx, dy) || 1;
  const outerRatio = Math.min(0.92, Math.max(0.42, (distance - PARTNER_RADIUS - 12 - labelWidth / 2) / distance));
  let ratio = Math.min(outerRatio, 0.58);
  // 向下的边会正好穿过中心的姓名条和「N 句台词」那行统计：落在这一带就顺着连线往外挪到下面。
  const CAPTION_TOP = CENTER_RADIUS + 4;
  const CAPTION_BOTTOM = CENTER_RADIUS + 72;
  if (dy > 0 && Math.abs(dx * ratio) < 100 && dy * ratio > CAPTION_TOP && dy * ratio < CAPTION_BOTTOM) {
    ratio = Math.min(outerRatio, (CAPTION_BOTTOM + 6) / dy);
  }
  const labelX = cx + dx * ratio;
  const labelY = cy + dy * ratio;

  return (
    <>
      <line
        className="rb-graph-edge"
        x1={startX}
        y1={startY}
        x2={endX}
        y2={endY}
        stroke={color}
        strokeWidth={lineWidth}
        markerEnd={focusSpoke ? `url(#${marker})` : undefined}
        markerStart={partnerSpoke ? `url(#${marker})` : undefined}
      >
        <title>{`${edge.partner.name} — ${labelText} — ${edge.note || '没有留存证据原文'}`}</title>
      </line>
      {labelled ? (
        <>
          <rect
            className="rb-graph-capsule"
            x={labelX - labelWidth / 2}
            y={labelY - 10}
            width={labelWidth}
            height={20}
            rx={10}
            stroke={color}
          />
          <text className="rb-graph-capsule-text" x={labelX} y={labelY + 4} textAnchor="middle" fill={color}>{shown}</text>
        </>
      ) : null}
    </>
  );
}

interface Props {
  focus: WorkbenchCharacter;
  /** 有语义关系的伙伴（已按焦点视角合并）。 */
  edges: PartnerEdge[];
  /** 只有同场记录的伙伴；开关关掉时传空数组。 */
  weak: WeakPartner[];
  /** 同场名单总人数：关掉开关也要在单人状态里说出来。 */
  weakTotal: number;
  rows: RelationRowRef[];
  onFocus: (cardId: string) => void;
  onBack: () => void;
  canBack: boolean;
}

export function RelationGraphCanvas(props: Props) {
  const { focus, edges, weak, weakTotal, rows, onFocus, onBack, canBack } = props;
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [size, setSize] = useState({ width: 880, height: 560 });

  // 画布铺满中间那一栏：用 ResizeObserver 量真实像素，窗口变窄时圆环跟着收。
  useLayoutEffect(() => {
    const element = stageRef.current;
    if (!element) return;
    const measure = () => {
      const width = element.clientWidth;
      const height = element.clientHeight;
      if (width > 0 && height > 0) setSize({ width, height });
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const { width, height } = size;
  // 底部 48px 留给图例：图例是 HTML 叠层，不参与 SVG 布局，
  // 不预留的话最低一排节点和姓名条会被压在它下面。
  const usableHeight = Math.max(160, height - 48);
  const cx = width / 2;
  const cy = usableHeight / 2 + 8;
  // 半径按「画布还能剩多少」算，而不是按尺寸取百分比：
  // 横向要留姓名条（最宽 ~115px），纵向要留头像和上下两块姓名条。
  const ring = Math.max(110, Math.min(width / 2 - 62, usableHeight / 2 - 58, 190));

  const strong: RingItem[] = edges.slice(0, MAX_PARTNERS).map((edge) => ({ kind: 'relation', card: edge.partner, edge }));
  const spare = Math.max(0, MAX_PARTNERS - strong.length);
  const extras: RingItem[] = weak.slice(0, spare).map((item) => ({ kind: 'weak', card: item.card, weight: item.weight }));
  const ringItems = [...strong, ...extras];
  const solo = ringItems.length === 0;

  // 角度均分：从正上方（-90°）开始顺时针排，第一个伙伴永远在头顶，读图时不用找。
  const points = new Map<string, Point>();
  ringItems.forEach((item, position) => {
    const angle = -Math.PI / 2 + (position / ringItems.length) * Math.PI * 2;
    points.set(item.card.id, { x: cx + Math.cos(angle) * ring, y: cy + Math.sin(angle) * ring });
  });

  // 同一个关系词只标一次：先数一遍每个词有几条边，再按伙伴顺序决定谁画胶囊。
  // 只数「真的画出来」的那些边——否则胶囊会写「姐妹 ×25」，画布上却只有 8 根线，对不上。
  const tally = new Map<string, number>();
  ringItems.forEach((item) => {
    if (item.kind !== 'relation') return;
    const key = item.edge.label || '';
    tally.set(key, (tally.get(key) ?? 0) + 1);
  });
  const drawnWords = new Set<string>();

  return (
    <div className="rb-graph-stage" ref={stageRef}>
      <svg
        className="rb-graph-svg"
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={solo ? `${focus.name} 还没有关系证据` : `${focus.name} 的关系图谱`}
      >
        <defs>
          {/* 每种类别一个箭头，颜色和连线一致；auto-start-reverse 让同一个 marker 能用在起点。 */}
          {RELATION_CATEGORIES.map((spec) => (
            <marker
              key={spec.key}
              id={`rb-graph-arrow-${spec.key}`}
              viewBox="0 0 10 10"
              refX={9}
              refY={5}
              markerWidth={6}
              markerHeight={6}
              orient="auto-start-reverse"
            >
              <path d="M0 0 L10 5 L0 10 z" fill={spec.color} />
            </marker>
          ))}
        </defs>

        {solo ? null : (
          <>
            {/* 伙伴与伙伴之间的细弧：弱化处理，避免抢主线 */}
            {ringItems.map((item, index) => {
              const from = points.get(item.card.id);
              if (!from) return null;
              return ringItems.slice(index + 1).map((other) => {
                const row = pairRowBetween(rows, item.card.id, other.card.id);
                const to = points.get(other.card.id);
                if (!row || !to) return null;
                const midX = (from.x + to.x) / 2;
                const midY = (from.y + to.y) / 2;
                // 往圆心方向收一点，弦就不会和两侧的主线叠在一起。
                const qx = midX + (cx - midX) * 0.18;
                const qy = midY + (cy - midY) * 0.18;
                return (
                  <path
                    key={`arc-${item.card.id}-${other.card.id}`}
                    className="rb-graph-arc"
                    d={`M${from.x} ${from.y} Q${qx} ${qy} ${to.x} ${to.y}`}
                    stroke={categorySpec(row.category).color}
                  >
                    <title>{`${item.card.name} 与 ${other.card.name}：${row.relation || '关系未写明'}`}</title>
                  </path>
                );
              });
            })}

            {/* 只是同场的灰虚线：勾上顶部开关才出现 */}
            {ringItems.map((item) => {
              if (item.kind !== 'weak') return null;
              const point = points.get(item.card.id);
              if (!point) return null;
              // 「同场 N」贴着伙伴那头放，再沿法线让开十几个像素：
              // 圆心正下方的姓名条和「N 句台词 · N 条关系」那块要留空，虚线文字不能压上去。
              const dx = point.x - cx;
              const dy = point.y - cy;
              const span = Math.hypot(dx, dy) || 1;
              const ratio = Math.min(0.92, Math.max(0.5, (span - PARTNER_RADIUS - 40) / span));
              const side = dx <= 0 ? -1 : 1;
              let labelX = cx + dx * ratio - (dy / span) * 16 * side;
              let labelY = cy + dy * ratio + (dx / span) * 16 * side - 4;
              // 向下那几条虚线会正好穿过字幕带：压到字就往侧向推出去。
              const inCaption = Math.abs(labelX - cx) < 100 && labelY > cy + 28 && labelY < cy + 124;
              if (inCaption) labelX = cx + side * 126;
              return (
                <g key={`weak-${item.card.id}`}>
                  <line
                    className="rb-graph-weak-line"
                    x1={cx}
                    y1={cy}
                    x2={point.x}
                    y2={point.y}
                  />
                  <text
                    className="rb-graph-weak-text"
                    x={labelX}
                    y={labelY}
                    textAnchor="middle"
                  >{`同场 ${item.weight}`}</text>
                </g>
              );
            })}

            {/* 关系边：靠前的先画，标签胶囊压在线上面 */}
            {ringItems.map((item) => {
              if (item.kind !== 'relation') return null;
              const point = points.get(item.card.id);
              if (!point) return null;
              const key = item.edge.label || '';
              const labelled = !drawnWords.has(key);
              drawnWords.add(key);
              return (
                <RelationEdge
                  key={`edge-${item.card.id}`}
                  edge={item.edge}
                  point={point}
                  cx={cx}
                  cy={cy}
                  rows={rows}
                  markerId={(category) => `rb-graph-arrow-${categorySpec(category).key}`}
                  labelled={labelled}
                  tally={tally.get(key) ?? 1}
                />
              );
            })}

            {/* 伙伴节点 */}
            {ringItems.map((item) => {
              const point = points.get(item.card.id);
              if (!point) return null;
              const radius = item.card.avatar?.relative ? PARTNER_RADIUS : PARTNER_RADIUS - 2;
              return (
                <g
                  key={`node-${item.card.id}`}
                  className="rb-graph-node"
                  role="button"
                  tabIndex={0}
                  aria-label={`以 ${item.card.name || '未命名角色'} 为焦点`}
                  onClick={() => onFocus(item.card.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      onFocus(item.card.id);
                    }
                  }}
                >
                  <SvgAvatar card={item.card} cx={point.x} cy={point.y} r={radius} />
                  <circle
                    className={`rb-graph-node-ring${item.kind === 'weak' ? ' is-weak' : ''}`}
                    cx={point.x}
                    cy={point.y}
                    r={radius}
                  />
                  <NamePlate name={item.card.name} cx={point.x} top={plateTop(point, cy, radius)} />
                </g>
              );
            })}
          </>
        )}

        {/* 中心：焦点角色（大头像 + 蓝色描边环 + 姓名条） */}
        <g>
          <SvgAvatar card={focus} cx={cx} cy={cy} r={solo ? CENTER_RADIUS + 4 : CENTER_RADIUS} />
          <circle
            className="rb-graph-center-ring"
            cx={cx}
            cy={cy}
            r={solo ? CENTER_RADIUS + 4 : CENTER_RADIUS}
          />
          <NamePlate name={focus.name} cx={cx} top={cy + CENTER_RADIUS + 12} />
          {solo ? (
            <>
              <text className="rb-graph-solo-hint" x={cx} y={cy + CENTER_RADIUS + 62} textAnchor="middle">
                这个角色还没有挖到关系证据
              </text>
              <text className="rb-graph-solo-sub" x={cx} y={cy + CENTER_RADIUS + 86} textAnchor="middle">
                {weakTotal
                  ? `和 ${weakTotal} 个人同过场，打开顶部「显示只是同场的连线」可以看名单`
                  : '台词里没有出现可识别的称谓，也没有同场记录'}
              </text>
            </>
          ) : (
            <text className="rb-graph-center-sub" x={cx} y={cy + CENTER_RADIUS + 54} textAnchor="middle">
              {`${lineCountOf(focus)} 句台词 · ${edges.length} 条关系`}
            </text>
          )}
        </g>
      </svg>

      <div className="rb-graph-crumbs">
        <button type="button" className="rb-graph-back" disabled={!canBack} onClick={onBack}>← 上一人</button>
        <span>{`当前：${focus.name || '未命名角色'}`}</span>
      </div>

      <div className="rb-graph-legend">
        <div className="rb-graph-legend-items">
          {RELATION_CATEGORIES.map((spec) => (
            <span key={spec.key}><i style={{ background: spec.color }} />{spec.label}</span>
          ))}
          <span><i className="is-weak" />只是同场</span>
        </div>
        <span
          className="rb-graph-legend-help"
          role="img"
          aria-label="关系是怎么算出来的"
          title={`关系由「谁先说出哪个称谓 + 同场景里有谁」挖出来，证据在右侧；箭头指向被称呼的那个人。画布最多画 ${MAX_PARTNERS} 个最强伙伴，其余在右侧关系列表里点。`}
        >?</span>
      </div>
    </div>
  );
}
