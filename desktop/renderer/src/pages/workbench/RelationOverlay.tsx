/**
 * 「全部关系」浮层：把当前角色的所有伙伴按主关系词分组，铺在一个分组扇区的圆环上。
 *
 * 布局与原型 docs/internal/2026-10-24/plan/overlay-v2.tpl.html 逐段对应，纯几何/聚合逻辑
 * 抽在 relationOverlayView.mjs（node --test 可直接跑），这里只负责画：
 * 1. 环：R = clamp(236, 270, n*64/2π)，节点半径按台词量开方缩放。
 * 2. 扇区：每组占一段角，人多的组更宽，组间留 0.19rad；带在 R-58..R-36，填类别色。
 * 3. 刻度：带外沿到节点内沿的短径向线，实线=我叫TA，虚线=TA叫我。
 * 4. 姓名：外圈单环 R+48，水平药丸 + 虚线引线，角度冲突用迭代推挤消解。
 * 5. 伙伴之间：默认关闭，开启后画向内收的细弧。
 * 6. 右栏 320px：搜索 / 分组列表 / 选中详情（证据台词 + 以TA为中心）。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Button } from 'antd';

import { AvatarBlock, SvgAvatar } from './GraphAvatar';
import { RelationTimeline } from './RelationTimeline';
import {
  categorySpec,
  indexCharacters,
  lineCountOf,
  RELATION_CATEGORIES,
  type RelationRowRef,
  type WorkbenchCharacter,
} from './relationGraph';
import {
  bandPath,
  buildOverlayModel,
  layoutRing,
  nodeRadiusOf,
  overlayCenter,
  peerPath,
  resolveLabels,
  OVERLAY_VIEW_H,
  OVERLAY_VIEW_W,
  type OverlayGroup,
  type OverlayPartner,
  type OverlayRow,
} from './relationOverlayView.mjs';

interface Props {
  focus: WorkbenchCharacter;
  characters: WorkbenchCharacter[];
  rows: RelationRowRef[];
  /** 换焦点：由外层决定要不要关掉这个浮层。 */
  onFocus: (id: string) => void;
  onClose: () => void;
}

interface TipState {
  id: string;
  left: number;
  top: number;
}

interface LabelEntry {
  partner: OverlayPartner;
  text: string;
  width: number;
  angle: number;
  half: number;
  item: { x: number; y: number; angle: number };
  radius: number;
  /** 姓名牌所在环的半径：相邻两块错开一圈，26 块牌子才放得下。 */
  ringRadius: number;
}

const { cx: CX, cy: CY } = overlayCenter();
const TIP_WIDTH = 248;
/** 第二圈姓名牌往外退的像素：要大于牌高的一半，两圈才不会互相压住。 */
const LABEL_RING_STEP = 26;

function clipText(value: string, max = 11): string {
  const text = String(value ?? '').trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

function groupColor(group: OverlayGroup): string {
  return group.color || categorySpec(group.category).color;
}

function dirArrowOf(row: OverlayRow): string {
  return row.dir === 'own' ? '→' : '←';
}

/** 详情卡里的一句话：「Momoko 的母亲是 Airi」。 */
function relHeadline(row: OverlayRow, fallbackName: string): string {
  const from = row.cardName || fallbackName;
  const to = row.partner?.name || row.target || '';
  return `${from} 的${row.relation || '关系'}是 ${to}`;
}

export function RelationOverlay({ focus, characters, rows, onFocus, onClose }: Props) {
  const [centerId, setCenterId] = useState(focus.id);
  const [selected, setSelected] = useState<string | null>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(() => new Set());
  const [showPeers, setShowPeers] = useState(false);
  const [showNames, setShowNames] = useState(true);
  const [showRejected, setShowRejected] = useState(() => rows.some((row) => row.rejected === true));
  const [view, setView] = useState<'overview' | 'timeline'>('overview');
  const [query, setQuery] = useState('');
  const [tip, setTip] = useState<TipState | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);

  // 外层换焦点（右栏「以TA为中心」或画布点节点）时，整块视图跟着重置。
  useEffect(() => {
    setCenterId(focus.id);
    setSelected(null);
    setHovered(null);
    setHidden(new Set());
    setQuery('');
    setTip(null);
  }, [focus.id]);

  const index = useMemo(() => indexCharacters(characters), [characters]);
  const center = index.byId.get(centerId) ?? focus;

  const model = useMemo(
    () => buildOverlayModel({
      focusId: centerId,
      rows,
      byId: index.byId,
      showRejected,
      colorOf: (category: string) => categorySpec(category).color,
    }),
    [centerId, rows, index, showRejected],
  );

  const visibleGroups = useMemo(
    () => model.groups.filter((group) => !hidden.has(group.key)),
    [model.groups, hidden],
  );

  const layout = useMemo(
    () => layoutRing({ groups: visibleGroups, cx: CX, cy: CY }),
    [visibleGroups],
  );

  const radiusOf = useCallback(
    (partner: OverlayPartner) => nodeRadiusOf(partner, layout.nodeR, model.maxLines),
    [layout.nodeR, model.maxLines],
  );

  /** 伙伴 id → 环上的落点与半径，边、刻度、标签都从这里取。 */
  const placed = useMemo(() => {
    const map = new Map<string, { x: number; y: number; angle: number; radius: number; partner: OverlayPartner; group: OverlayGroup }>();
    for (const entry of layout.groups) {
      for (const item of entry.items) {
        map.set(item.partner.id, {
          x: item.x,
          y: item.y,
          angle: item.angle,
          radius: radiusOf(item.partner),
          partner: item.partner,
          group: entry.group,
        });
      }
    }
    return map;
  }, [layout.groups, radiusOf]);

  const hotId = selected ?? hovered;

  const peerEdges = useMemo(() => {
    if (!model.peers.length) return [];
    if (showPeers) return model.peers;
    if (!hotId) return [];
    return model.peers.filter((edge) => edge.fromId === hotId || edge.toId === hotId);
  }, [model.peers, showPeers, hotId]);

  /**
   * 姓名牌：单圈最多放得下「弧长 ÷ 牌宽」块，26 个伙伴时牌子会挤在一起。
   * 所以把环上的邻居按奇偶分到两圈（外圈再退 26），每圈独立推挤 —— 可容纳量直接翻倍，
   * 上下两端的短名字也不会再互相压住。
   */
  const labels = useMemo(() => {
    if (!showNames) return [] as LabelEntry[];
    const entries: LabelEntry[] = [];
    for (const entry of layout.groups) {
      for (const item of entry.items) {
        const text = clipText(item.partner.name);
        const width = Math.min(112, text.length * 11.4 + 16);
        entries.push({
          partner: item.partner,
          text,
          width,
          angle: item.angle,
          half: 0,
          item: { x: item.x, y: item.y, angle: item.angle },
          radius: radiusOf(item.partner),
          ringRadius: layout.labelRing,
        });
      }
    }
    const sorted = entries.sort((left, right) => left.angle - right.angle);
    const rings = [sorted.filter((_, index) => index % 2 === 0), sorted.filter((_, index) => index % 2 === 1)];
    const placed: LabelEntry[] = [];
    rings.forEach((ring, depth) => {
      const ringRadius = layout.labelRing + depth * LABEL_RING_STEP;
      placed.push(...resolveLabels(ring.map((entry) => ({
        ...entry,
        ringRadius,
        half: (entry.width / 2 + 6) / ringRadius,
      }))));
    });
    return placed;
  }, [showNames, layout.groups, layout.labelRing, radiusOf]);

  const centerLines = lineCountOf(center);
  const stagePointer = useCallback((event: { currentTarget: Element }, id: string) => {
    const stage = stageRef.current;
    if (!stage) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const box = stage.getBoundingClientRect();
    let left = rect.left - box.left + rect.width + 10;
    let top = rect.top - box.top + rect.height / 2 - 44;
    if (left + TIP_WIDTH > box.width - 8) left = rect.left - box.left - TIP_WIDTH - 10;
    if (left < 8) left = 8;
    if (top < 8) top = 8;
    if (top > box.height - 150) top = Math.max(8, box.height - 150);
    setTip({ id, left, top });
  }, []);

  const hoverOn = useCallback((event: { currentTarget: Element }, id: string) => {
    setHovered(id);
    stagePointer(event, id);
  }, [stagePointer]);

  const hoverOff = useCallback(() => {
    setHovered(null);
    setTip(null);
  }, []);

  const pick = useCallback((id: string) => {
    setSelected((previous) => (previous === id ? null : id));
  }, []);

  const toggleGroup = useCallback((key: string) => {
    setHidden((previous) => {
      const next = new Set(previous);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const centered = useCallback((id: string) => {
    setSelected(null);
    setQuery('');
    setHidden(new Set());
    onFocus(id);
  }, [onFocus]);

  const tipPartner = tip ? model.partners.find((partner) => partner.id === tip.id) ?? null : null;
  const selectedPartner = selected ? model.partners.find((partner) => partner.id === selected) ?? null : null;
  const needle = query.trim().toLocaleLowerCase();

  const panelGroups = model.groups
    .map((group) => ({
      group,
      members: group.members.filter((partner) => !needle || partner.name.toLocaleLowerCase().includes(needle)),
    }))
    .filter((entry) => entry.members.length > 0 || !needle);

  const peersOfSelected = selectedPartner
    ? model.peers.filter((edge) => edge.fromId === selectedPartner.id || edge.toId === selectedPartner.id)
    : [];

  return (
    <div className="rb-rel-overlay" role="dialog" aria-label="全部关系">
      <div className="rb-rel-overlay-head">
        <div className="rb-rel-overlay-title">
          <h3><em>{center.name || '未命名角色'}</em> 的全部关系</h3>
          <p>
            <b>{model.partnerCount}</b> 个伙伴 · <b>{model.edgeCount}</b> 条直接关系 ·
            伙伴之间 {model.peers.length} 条 · {centerLines} 句台词
            {model.rejectedCount ? ` · 已否决 ${model.rejectedCount} 条` : ''}
          </p>
          {view === 'overview' ? (
            <p className="rb-rel-overlay-read">
              中间是 <b>{center.name || '当前角色'}</b>；每段弧 = 一种叫法，弧上卡片写「谁这么叫谁」；
              每人一条线：<b>TA 这么叫我</b> = 虚线，<b>我这么叫 TA</b> = 实线；节点右上角数字 = 两人之间有几条关系。
            </p>
          ) : null}
        </div>
        <span className="rb-rel-overlay-actions">
          <div className="rb-rel-viewswitch" role="tablist" aria-label="视图">
            <button
              type="button"
              role="tab"
              aria-selected={view === 'overview'}
              className={`rb-rel-viewtab${view === 'overview' ? ' is-active' : ''}`}
              onClick={() => setView('overview')}
            >概览</button>
            <button
              type="button"
              role="tab"
              aria-selected={view === 'timeline'}
              className={`rb-rel-viewtab${view === 'timeline' ? ' is-active' : ''}`}
              onClick={() => setView('timeline')}
            >时间线</button>
          </div>
          <Button size="small" onClick={() => { onFocus(centerId); onClose(); }}>在主视图打开</Button>
          <Button size="small" type="primary" onClick={onClose}>关闭</Button>
        </span>
      </div>

      <div className="rb-rel-overlay-toolbar">
        <div className="rb-rel-overlay-chips">
          {model.groups.map((group) => {
            const off = hidden.has(group.key);
            return (
              <button
                key={group.key}
                type="button"
                className={`rb-rel-chip${off ? ' is-off' : ' is-on'}`}
                style={{ color: groupColor(group) }}
                title={off ? '点击显示这一组' : '点击隐藏这一组'}
                onClick={() => toggleGroup(group.key)}
              >
                <i className="rb-rel-chip-dot" style={{ background: groupColor(group) }} />
                {`${group.rejectedOnly ? '已否决 · ' : ''}${group.mixedDir ? '互称' : group.dir === 'own' ? '我叫 TA' : 'TA 叫我'}「${group.label}」`}
                <b>{group.members.length}</b>
              </button>
            );
          })}
          {!model.groups.length ? <span className="rb-rel-overlay-hint">还没有挖到关系</span> : null}
        </div>
        <div className="rb-rel-overlay-switches">
          <label className="rb-rel-switch">
            <input type="checkbox" checked={showNames} onChange={(event) => setShowNames(event.target.checked)} />
            <span>姓名</span>
          </label>
          <label className="rb-rel-switch">
            <input type="checkbox" checked={showPeers} onChange={(event) => setShowPeers(event.target.checked)} />
            <span>{`显示伙伴之间${model.peers.length ? `（${model.peers.length}）` : ''}`}</span>
          </label>
          {model.rejectedCount ? (
            <label className="rb-rel-switch">
              <input type="checkbox" checked={showRejected} onChange={(event) => setShowRejected(event.target.checked)} />
              <span>{`显示已否决（${model.rejectedCount}）`}</span>
            </label>
          ) : null}
          <span className="rb-rel-overlay-hint">悬停看详情 · 点击固定</span>
        </div>
      </div>

      <div className="rb-rel-overlay-main">
        {view === 'timeline' ? (
          <div className="rb-rel-overlay-stage is-timeline">
            <RelationTimeline
              groups={model.groups}
              partners={model.partners}
              showRejected={showRejected}
              selected={selected}
              onPick={pick}
            />
          </div>
        ) : (
        <div className="rb-rel-overlay-stage" ref={stageRef}>
          <svg
            className="rb-rel-overlay-svg"
            viewBox={`0 0 ${OVERLAY_VIEW_W} ${OVERLAY_VIEW_H}`}
            preserveAspectRatio="xMidYMid meet"
            onClick={() => setSelected(null)}
          >
            {/* 伙伴之间：向内收的细弧，只有开关打开才画。 */}
            {showPeers ? (
            <g className="rb-rel-peers">
              {peerEdges.map((edge) => {
                const a = placed.get(edge.fromId);
                const b = placed.get(edge.toId);
                if (!a || !b) return null;
                return (
                  <path
                    key={edge.key}
                    d={peerPath({
                      x1: a.x,
                      y1: a.y,
                      r1: a.radius,
                      x2: b.x,
                      y2: b.y,
                      r2: b.radius,
                      cx: CX,
                      cy: CY,
                    })}
                    fill="none"
                    stroke={categorySpec(edge.category).color}
                    strokeWidth={1.1}
                    opacity={0.28}
                    strokeLinecap="round"
                  />
                );
              })}
            </g>
            ) : null}

            {/* 环形带：只画在人所在的环上。旧版从中心拉淡楔形，会被读成饼图/从属关系，已去掉。 */}
            <g>
              {layout.groups.map((entry) => {
                const dim = Boolean(selected) && !entry.group.members.some((member) => member.id === selected);
                return (
                  <path
                    key={`band-${entry.group.key}`}
                    d={bandPath(CX, CY, entry.start, entry.end, layout.bandIn, layout.bandOut)}
                    fill={groupColor(entry.group)}
                    fillOpacity={0.2}
                    stroke={groupColor(entry.group)}
                    strokeOpacity={0.5}
                    strokeWidth={1}
                    className={`rb-rel-band${dim ? ' is-dim' : ''}`}
                    onClick={(event) => {
                      event.stopPropagation();
                      const first = entry.group.members[0];
                      if (first) pick(first.id);
                    }}
                  />
                );
              })}
            </g>

            {/* 组摘要卡片：每组都标，写明「谁这么叫谁」；单人组也要标，否则母亲那段弧没有解释。 */}
            <g className="rb-rel-glabel">
              {layout.groups.map((entry) => {
                const group = entry.group;
                const dirWord = group.mixedDir ? '互称' : group.dir === 'own' ? '我叫' : 'TA 叫我';
                const text = `${group.rejectedOnly ? '已否决 · ' : ''}${dirWord}「${group.label}」${group.members.length > 1 ? `×${group.members.length}` : ''}`;
                const width = Math.max(92, text.length * 12.2 + 28);
                const radius = (layout.bandIn + layout.bandOut) / 2;
                const x = CX + Math.cos(entry.mid) * radius;
                const y = CY + Math.sin(entry.mid) * radius;
                return (
                  <g key={`gcard-${group.key}`} transform={`translate(${x}, ${y})`}>
                    <rect
                      x={-width / 2}
                      y={-15}
                      width={width}
                      height={30}
                      rx={8}
                      fill="#FFFFFF"
                      fillOpacity={0.92}
                      stroke={groupColor(group)}
                      strokeOpacity={0.55}
                      strokeWidth={1}
                    />
                    <circle cx={-width / 2 + 12} cy={-4} r={3.4} fill={groupColor(group)} />
                    <text x={-width / 2 + 21} y={0} fontSize={11.5} fontWeight={600} fill="#3F3F46">
                      {text}
                    </text>
                    <text x={-width / 2 + 21} y={11} fontSize={9.8} fill="#8B8B96">
                      {`${group.rejectedOnly ? 'AI 认为不对' : group.dirLabel} · ${group.edges} 条`}
                    </text>
                  </g>
                );
              })}
            </g>

            {/* 刻度线：实线 = 我叫TA，虚线 = TA叫我。 */}
            <g>
              {layout.groups.map((entry) => {
                const dim = Boolean(selected) && !entry.group.members.some((member) => member.id === selected);
                return entry.items.map((item) => {
                  const a = item.angle;
                  const radius = radiusOf(item.partner);
                  const incoming = item.partner.primaryDir === 'incoming';
                  const rejected = item.partner.rejectedAll;
                  return (
                    <line
                      key={`tick-${item.partner.id}`}
                      x1={CX + Math.cos(a) * layout.bandOut}
                      y1={CY + Math.sin(a) * layout.bandOut}
                      x2={CX + Math.cos(a) * (layout.R - radius - 5)}
                      y2={CY + Math.sin(a) * (layout.R - radius - 5)}
                      stroke={groupColor(entry.group)}
                      strokeWidth={1.1}
                      opacity={rejected ? 0.45 : 0.3}
                      strokeDasharray={rejected ? '1 3' : incoming ? '3 4' : undefined}
                      className={`rb-rel-tick${dim ? ' is-dim' : ''}`}
                    />
                  );
                });
              })}
            </g>

            <circle cx={CX} cy={CY} r={layout.R} fill="none" stroke="#F1F1F4" strokeWidth={1} />

            {/* 伙伴节点。 */}
            <g>
              {layout.groups.map((entry) => {
                const dim = Boolean(selected) && !entry.group.members.some((member) => member.id === selected);
                return entry.items.map((item) => {
                  const partner = item.partner;
                  const radius = radiusOf(partner);
                  const hot = hotId === partner.id;
                  const color = groupColor(entry.group);
                  return (
                    <g
                      key={`node-${partner.id}`}
                      className={`rb-rel-node${hot ? ' is-hot' : ''}${dim ? ' is-dim' : ''}`}
                      onMouseEnter={(event) => hoverOn(event, partner.id)}
                      onMouseLeave={hoverOff}
                      onClick={(event) => {
                        event.stopPropagation();
                        pick(partner.id);
                      }}
                    >
                      {hot ? (
                        <circle cx={item.x} cy={item.y} r={radius + 6} fill="none" stroke="var(--rb-accent)" strokeOpacity={0.35} strokeWidth={3} />
                      ) : null}
                      <circle cx={item.x} cy={item.y} r={radius + 2.5} fill="#FFFFFF" stroke={color} strokeOpacity={0.9} strokeWidth={2} strokeDasharray={partner.rejectedAll ? '3 2' : undefined} />
                      <SvgAvatar card={partner.card} cx={item.x} cy={item.y} r={radius} color={color} />
                      <circle cx={item.x} cy={item.y} r={radius} fill="none" stroke="rgba(0,0,0,.07)" strokeWidth={1} />
                      {partner.rows.length > 1 ? (
                        <g>
                          <title>{`${partner.rows.length} 条关系：${partner.rows.map((row) => row.relation || '关系').join(' / ')}`}</title>
                          <circle cx={item.x + radius * 0.74} cy={item.y - radius * 0.74} r={8} fill="#FFFFFF" stroke="#A1A1AA" strokeWidth={1} />
                          <text
                            x={item.x + radius * 0.74}
                            y={item.y - radius * 0.74 + 3}
                            textAnchor="middle"
                            fontSize={9}
                            fontWeight={700}
                            fill="#52525B"
                          >
                            {partner.rows.length}
                          </text>
                        </g>
                      ) : null}
                    </g>
                  );
                });
              })}
            </g>

            {/* 姓名药丸 + 虚线引线。 */}
            {showNames ? (
              <g>
                {labels.map((entry) => {
                  const a = entry.angle;
                  const ax = CX + Math.cos(a) * entry.ringRadius;
                  const ay = CY + Math.sin(a) * entry.ringRadius;
                  const nx = entry.item.x + Math.cos(a) * (entry.radius + 3);
                  const ny = entry.item.y + Math.sin(a) * (entry.radius + 3);
                  const hot = hotId === entry.partner.id;
                  return (
                    <g key={`label-${entry.partner.id}`}>
                      <path
                        d={`M ${nx} ${ny} L ${CX + Math.cos(a) * (entry.ringRadius - 12)} ${CY + Math.sin(a) * (entry.ringRadius - 12)}`}
                        fill="none"
                        stroke="#CFCFD6"
                        strokeWidth={1}
                        strokeDasharray="2 2"
                      />
                      <g
                        className={`rb-rel-nlabel${hot ? ' is-hot' : ''}`}
                        transform={`translate(${ax}, ${ay})`}
                        onMouseEnter={(event) => hoverOn(event, entry.partner.id)}
                        onMouseLeave={hoverOff}
                        onClick={(event) => {
                          event.stopPropagation();
                          pick(entry.partner.id);
                        }}
                      >
                        <rect
                          x={-entry.width / 2}
                          y={-9.5}
                          width={entry.width}
                          height={19}
                          rx={9.5}
                          fill="#FFFFFF"
                          fillOpacity={0.95}
                          stroke={hot ? 'var(--rb-accent)' : '#E4E4E7'}
                          strokeWidth={1}
                        />
                        <text y={3.4} textAnchor="middle" fontSize={10.8} fill="#52525B">
                          {entry.text}
                        </text>
                      </g>
                    </g>
                  );
                })}
              </g>
            ) : null}

            {/* 中心焦点。 */}
            <g>
              <circle cx={CX} cy={CY} r={46} fill="none" stroke="#E4E4E7" strokeWidth={1} strokeDasharray="2 4" />
              <circle cx={CX} cy={CY} r={39} fill="#FFFFFF" stroke="var(--rb-accent)" strokeWidth={2} />
              <SvgAvatar card={center} cx={CX} cy={CY} r={36} />
              <text x={CX} y={CY + 68} textAnchor="middle" fontSize={13} fontWeight={600} fill="#18181B">
                {center.name || '未命名角色'}
              </text>
              <text x={CX} y={CY + 84} textAnchor="middle" fontSize={10.5} fill="#71717A">
                {`${centerLines} 句 · ${model.partnerCount} 个伙伴`}
              </text>
            </g>
          </svg>

          {!model.partners.length ? (
            <p className="rb-rel-overlay-empty">
              这个人还没有挖到关系。回图谱页跑一次角色扫描，或在「角色卡」里手动补一条关系。
            </p>
          ) : null}

          {tip && tipPartner ? (
            <div className="rb-rel-tip" style={{ left: tip.left, top: tip.top, width: TIP_WIDTH }}>
              <div className="rb-rel-tip-top">
                <span className="rb-rel-tip-name">{tipPartner.name}</span>
                <span className="rb-rel-tip-meta">{`${tipPartner.lines} 句`}</span>
              </div>
              <div className="rb-rel-tip-rel">
                {tipPartner.relations.map((row) => (
                  <span key={`${row.cardId}#${row.index}`}>
                    {`${dirArrowOf(row)} ${row.relation || '关系'} · ${row.hits}${row.rejected ? ' · 已否决' : ''}`}
                  </span>
                ))}
              </div>
              {tipPartner.primary?.evidence?.length ? (
                <div className="rb-rel-tip-evi">
                  <em>证据 · </em>
                  {clipText(String(tipPartner.primary.evidence[0]), 90)}
                </div>
              ) : null}
            </div>
          ) : null}
        </div>
        )}

        <aside className="rb-rel-panel" aria-label="伙伴列表">
          <div className="rb-rel-panel-head">
            <div className="rb-rel-panel-focus">
              <AvatarBlock card={center} size={34} />
              <div>
                <div className="rb-rel-panel-name">{center.name || '未命名角色'}</div>
                <div className="rb-rel-panel-meta">{`${centerLines} 句台词 · ${model.partnerCount} 个伙伴`}</div>
              </div>
            </div>
            <div className="rb-rel-search">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden>
                <circle cx={11} cy={11} r={7} />
                <path d="m20 20-3.5-3.5" />
              </svg>
              <input
                value={query}
                placeholder="搜索角色…"
                aria-label="搜索角色"
                onChange={(event) => setQuery(event.target.value)}
              />
            </div>
          </div>

          <div className="rb-rel-panel-body">
            {selectedPartner ? (
              <>
                <button type="button" className="rb-rel-detail-back" onClick={() => setSelected(null)}>‹ 返回列表</button>
                <div className="rb-rel-detail-top">
                  <AvatarBlock card={selectedPartner.card} size={52} />
                  <div>
                    <div className="rb-rel-detail-name">{selectedPartner.name}</div>
                    <div className="rb-rel-detail-meta">
                      {`${selectedPartner.lines} 句台词 · 命中 ${selectedPartner.hits} 次 · ${selectedPartner.rows.length} 条直接关系`}
                    </div>
                  </div>
                </div>

                <div className="rb-rel-sect">{`与 ${center.name || '未命名角色'} 的关系`}</div>
                {selectedPartner.relations.map((row) => (
                  <div className={`rb-rel-card${row.rejected ? ' is-rejected' : ''}`} key={`${row.cardId}#${row.index}`}>
                    <div className="rb-rel-card-top">
                      <span className="rb-rel-card-arrow">{dirArrowOf(row)}</span>
                      <span className="rb-rel-card-word">{relHeadline(row, center.name || '未命名角色')}</span>
                      {row.rejected ? <span className="rb-rel-card-tag">AI 否决</span> : null}
                      <span className="rb-rel-card-cnt">{`${row.hits} 次`}</span>
                    </div>
                    {row.evidence.length
                      ? row.evidence.slice(0, 2).map((line, position) => (
                        <p className="rb-rel-card-evi" key={`${row.cardId}#${row.index}#${position}`}>
                          <q>{line}</q>
                        </p>
                      ))
                      : <p className="rb-rel-card-evi is-empty">没有留下证据台词</p>}
                  </div>
                ))}

                <div className="rb-rel-sect">{`伙伴之间（${peersOfSelected.length}）`}</div>
                {peersOfSelected.length ? peersOfSelected.map((edge) => {
                  const otherId = edge.fromId === selectedPartner.id ? edge.toId : edge.fromId;
                  const otherName = edge.fromId === selectedPartner.id ? edge.toName : edge.fromName;
                  return (
                    <button
                      type="button"
                      className="rb-rel-peer-line"
                      key={edge.key}
                      onClick={() => {
                        if (placed.has(otherId)) pick(otherId);
                      }}
                    >
                      <span className="rb-rel-peer-name">{otherName}</span>
                      <span className="rb-rel-peer-word">{`${edge.relation || '关系'} · ${edge.hits}`}</span>
                    </button>
                  );
                }) : <p className="rb-rel-empty">没有伙伴之间的关系</p>}

                <div className="rb-rel-detail-actions">
                  <Button size="small" onClick={() => centered(selectedPartner.id)}>
                    {`以 ${selectedPartner.name} 为中心`}
                  </Button>
                </div>
              </>
            ) : (
              <>
                {panelGroups.map(({ group, members }) => {
                  const off = hidden.has(group.key);
                  return (
                    <div className={`rb-rel-group${off ? ' is-off' : ''}`} key={group.key}>
                      <button
                        type="button"
                        className="rb-rel-group-head"
                        title={off ? '点击显示这一组' : '点击隐藏这一组'}
                        onClick={() => toggleGroup(group.key)}
                      >
                        <i className="rb-rel-group-dot" style={{ background: groupColor(group) }} />
                        <span className="rb-rel-group-name">{`${group.dirArrow} ${group.label}`}</span>
                        <span className="rb-rel-group-dir">{group.dirText}</span>
                        <span className="rb-rel-group-count">{`${group.edges} 条 · ${group.members.length} 人`}</span>
                      </button>
                      {members.map((partner) => (
                        <button
                          type="button"
                          className={`rb-rel-row${selected === partner.id ? ' is-selected' : ''}`}
                          key={partner.id}
                          onMouseEnter={(event) => hoverOn(event, partner.id)}
                          onMouseLeave={hoverOff}
                          onClick={() => pick(partner.id)}
                        >
                          <AvatarBlock card={partner.card} size={22} />
                          <span className="rb-rel-row-name">{partner.name}</span>
                          {partner.rows.length > 1 ? (
                            <span className="rb-rel-row-multi" title="与当前角色有多重关系">{partner.rows.length}</span>
                          ) : null}
                          <span className="rb-rel-row-count">{partner.hits}</span>
                        </button>
                      ))}
                    </div>
                  );
                })}
                {!panelGroups.length ? <p className="rb-rel-empty">没有匹配的角色</p> : null}
              </>
            )}
          </div>
        </aside>
      </div>

      <div className="rb-rel-overlay-foot">
        <div className="rb-rel-overlay-legend">
          {RELATION_CATEGORIES.map((spec) => (
            <span key={spec.key}><i style={{ background: spec.color }} />{spec.label}</span>
          ))}
          <span><i className="is-line" />我的叫法</span>
          <span><i className="is-line is-dashed" />对方的叫法</span>
        </div>
        <span className="rb-rel-overlay-note">
          {`规则挖掘 · ${model.edgeCount} 条直接关系 · ${model.partnerCount} 位伙伴`}
        </span>
      </div>
    </div>
  );
}
