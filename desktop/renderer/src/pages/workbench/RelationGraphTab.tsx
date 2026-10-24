/**
 * 关系图谱标签页：左侧角色名册 / 中间焦点画布 / 右侧关系证据。
 *
 * 数据不在这里另存一份：画的是工作台草稿里的角色卡，改关系就直接改草稿里的 relations，
 * 再走页面原来的「保存修改」（带版本校验）落盘。所以这里只负责「按焦点派生出可画的边」
 * 和「把人工修改写回对应的角色卡」。
 *
 * 三条方向规则在画布组件里，这里只管把它要的东西备齐：
 * 焦点自己写的边、别人写到他头上的边、只有同场记录的虚线候选。
 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Input, Select } from 'antd';

import { Empty } from '../../ui';
import type { PageKey } from '../../nav';
import type { StoryBlueprintReadiness } from '../storyBlueprint/storyBlueprintView.mjs';
import { AvatarBlock } from './GraphAvatar';
import { resolveGraphBlocked, scanBlockedHint } from './graphBlocked.mjs';
import { RelationGraphCanvas } from './RelationGraphCanvas';
import { RelationOverlay } from './RelationOverlay';
import {
  buildRelationRows,
  categorySpec,
  focusRelationRows,
  hitCount,
  indexCharacters,
  lineCountOf,
  partnerEdges,
  RELATION_CATEGORIES,
  relationPhrase,
  relationSamples,
  relationsOfCard,
  restoreRejectedRows,
  sourceLabel,
  visibleRows,
  weakPartners,
  type RelationRowRef,
  type WorkbenchCharacter,
} from './relationGraph';

interface Props<C extends WorkbenchCharacter> {
  characters: C[];
  /**
   * 项目体检结果：关系图谱和剧情蓝图一样要读 game 下的 .rpy 脚本，所以「没角色」有几种
   * 完全不同的原因——没绑工程 / 是 .rpa 没解包 / 工程就绪只是没扫过。不区分的话用户只会
   * 看到一句「还没有角色资料」，不知道该点哪。
   */
  readiness?: StoryBlueprintReadiness | null;
  /** 触发角色扫描；工程就绪时直接从这里补一步。 */
  onScan?: () => void;
  /** 让用户自己解除前置：去绑定工程或去解包。 */
  onNavigate?: (page: PageKey) => void;
  /** 扫描按钮此刻能不能点（引擎忙 / 有未保存改动时不能）。 */
  canScan?: boolean;
  /** 把改过的角色卡数组交回工作台草稿；走原有保存流程，不调新接口。 */
  onChange: (characters: C[]) => void;
  /** 保存中 / 版本校验失败等状态下禁止改动。 */
  disabled: boolean;
  /** 有多少对「有源码证据的规则边」可以送去复核；0 表示按钮置灰。 */
  reviewable?: number;
  /** 正在请求模型（工作台用全局 busy 表示）。 */
  reviewing?: boolean;
  /** 打开复核确认弹窗；真正的请求在页面层，因为要用 snapshot 里的版本号。 */
  onReview?: () => void;
  /** 有多少张「待审核草稿」可以清洗；0 表示按钮置灰。 */
  cleanable?: number;
  /** 打开清洗确认弹窗；同样是页面层发请求，因为它要动 snapshot 里的草稿。 */
  onClean?: () => void;
}

function rowKey(row: RelationRowRef): string {
  return `${row.cardId}#${row.index}`;
}

/**
 * 没有角色卡时的引导：先按体检结果说清「卡在哪一步」，再给对应的那一个按钮。
 *
 * 关系图谱是纯规则挖掘（RelationMiner 只读 game 下的 .rpy，找「称谓词 + 同场景角色」），
 * 所以既不需要世界观，也不需要先翻译；真正的前置只有三件事：绑工程、有 .rpy、扫一次。
 */
function GraphBlocked(props: {
  readiness: StoryBlueprintReadiness | null;
  onScan?: () => void;
  onNavigate?: (page: PageKey) => void;
  canScan: boolean;
}) {
  const { readiness, onScan, onNavigate, canScan } = props;
  // 判定逻辑放在 graphBlocked.mjs，node 单测盯住「哪种体检结果给哪张卡」。
  const card = resolveGraphBlocked(readiness);
  const hint = scanBlockedHint(canScan);
  // 按钮只在真的能点动时才画：缺对应的回调就干脆不给一个点了没反应的按钮。
  const run = card.action === 'scan'
    ? onScan
    : card.action === 'bind'
      ? (onNavigate ? () => onNavigate('project') : undefined)
      : (onNavigate ? () => onNavigate('pack-unpack') : undefined);
  const disabled = card.action === 'scan' ? !canScan : false;

  return (
    <div className="rb-graph-blocked" data-stage={card.stage}>
      <strong>{card.title}</strong>
      <p>{card.detail}</p>
      {run ? (
        <Button type="primary" disabled={disabled} onClick={run}>{card.actionLabel}</Button>
      ) : null}
      {hint && card.action === 'scan' ? (
        <span className="rb-graph-blocked-hint">{hint}</span>
      ) : null}
    </div>
  );
}

// 泛型收口：工作台的角色卡类型（多几个可选字段）和这里的 WorkbenchCharacter 结构兼容，
// 改完原样交回去，不用在调用处做任何转换。
/** AI 否决的原因文案：note 形如「AI 否决：<reason>」，取冒号后的原因。 */
function rejectedReason(note: string): string {
  const text = String(note ?? '').trim();
  const prefix = 'AI 否决：';
  return text.startsWith(prefix) ? text.slice(prefix.length).trim() : text;
}

export function RelationGraphTab<C extends WorkbenchCharacter>(props: Props<C>) {
  const { characters, onChange, disabled, reviewable = 0, reviewing = false, onReview, cleanable = 0, onClean } = props;
  const { readiness = null, onScan, onNavigate, canScan = false } = props;
  const [focusId, setFocusId] = useState('');
  const [overlayOpen, setOverlayOpen] = useState(false);
  /** 回退栈：点过谁就压一层，只记 id，跟着角色卡走。 */
  const [history, setHistory] = useState<string[]>([]);
  const [search, setSearch] = useState('');
  const [showWeak, setShowWeak] = useState(false);
  /** 正在编辑的那条关系（cardId#index），空串表示没在编辑。 */
  const [editing, setEditing] = useState('');
  const [editWord, setEditWord] = useState('');
  const [editCategory, setEditCategory] = useState('other');

  const index = useMemo(() => indexCharacters(characters), [characters]);
  const rows = useMemo(() => buildRelationRows(characters), [characters]);
  // 中栏画布和伙伴圆环都不画被否决的边，它们只在右栏「已否决」小节里出现。
  const canvasRows = useMemo(() => visibleRows(rows), [rows]);

  const focus = useMemo(() => {
    const hit = focusId ? index.byId.get(focusId) : undefined;
    if (hit) return hit;
    // 默认焦点：关系证据最多的人；都没有关系就退回第一位。
    let best = characters[0];
    let bestCount = -1;
    for (const card of characters) {
      const count = rows.filter((row) => row.cardId === card.id || row.partner?.id === card.id).length;
      if (count > bestCount) { best = card; bestCount = count; }
    }
    return best;
  }, [characters, focusId, index, rows]);

  // 角色被删掉或换了项目时，焦点要跟着落回一位存在的角色，否则右侧面板会空在那儿。
  useEffect(() => {
    if (!focusId) return;
    if (!index.byId.has(focusId)) setFocusId('');
  }, [focusId, index]);

  const goFocus = (id: string) => {
    if (!id || id === focus?.id) return;
    setFocusId(id);
    setHistory((previous) => (focus ? [...previous, focus.id] : previous));
    setEditing('');
  };

  const goBack = () => {
    const previous = history[history.length - 1];
    if (!previous) return;
    setHistory(history.slice(0, -1));
    setFocusId(previous);
    setEditing('');
  };

  const edges = useMemo(() => (focus ? partnerEdges(focus.id, canvasRows, index.byId) : []), [focus, canvasRows, index]);
  // 已经画在圆环上的伙伴不能再用虚线补一遍。
  const drawn = useMemo(() => new Set(edges.map((edge) => edge.partner.id)), [edges]);
  const weakAll = useMemo(() => (focus ? weakPartners(focus, index, drawn) : []), [focus, index, drawn]);
  // AI 否决的边不画在画布上，单独收进右栏的「已否决」小节。
  const detailAll = useMemo(() => (focus ? focusRelationRows(focus.id, rows) : []), [focus, rows]);
  const detailRows = useMemo(() => detailAll.filter((row) => !row.rejected), [detailAll]);
  const rejectedDetail = useMemo(() => detailAll.filter((row) => row.rejected), [detailAll]);
  const [showRejected, setShowRejected] = useState(false);

  /**
   * 恢复一条被否决的边：只把 source 改回 manual，仍然走 onChange 的草稿保存路径，
   * 后端不需要新接口 —— manual 的边之后既不会被重扫覆盖，也不会被 AI 复核改写。
   */
  const restoreRejected = (row: RelationRowRef) => {
    onChange(restoreRejectedRows(characters, new Set([rowKey(row)])));
  };

  const needle = search.trim().toLocaleLowerCase();
  const railRows = characters.filter((card) => !needle
    || [card.name, card.name_translation, ...(card.aliases ?? []), ...(card.match_keywords ?? [])]
      .join(' ').toLocaleLowerCase().includes(needle));

  /**
   * 把一条关系的改动写回它所属的角色卡。
   * 直接按 cardId + index 定位，改完统一把 source 置成 manual —— 后端对 manual 的边
   * 既不会重新扫描覆盖，也不会被 AI 复核改写。
   */
  const commit = (row: RelationRowRef, patch: { relation: string; category: string } | null) => {
    onChange(characters.map((card) => {
      if (card.id !== row.cardId) return card;
      const current = relationsOfCard(card);
      const next = patch
        ? current.map((item, position) => (position === row.index ? { ...item, ...patch, source: 'manual' } : item))
        : current.filter((_, position) => position !== row.index);
      return { ...card, relations: next };
    }));
    setEditing('');
  };

  const startEdit = (row: RelationRowRef) => {
    setEditing(rowKey(row));
    setEditWord(row.relation);
    setEditCategory(categorySpec(row.category).key);
  };

  if (!characters.length) {
    return <GraphBlocked readiness={readiness} onScan={onScan} onNavigate={onNavigate} canScan={canScan} />;
  }

  if (!focus) return <Empty>选择一位角色，查看他和其他人的关系。</Empty>;

  return (
    <div className="rb-graph">
      <div className="rb-graph-bar">
        <label className="rb-graph-toggle">
          <input
            type="checkbox"
            checked={showWeak}
            disabled={disabled}
            onChange={(event) => setShowWeak(event.target.checked)}
          />
          <span>显示只是同场的连线</span>
        </label>
        <span className="rb-graph-chips">
          <Button
            size="small"
            disabled={!focus}
            title="把这个人的所有关系一次摊开：不限 8 个、伙伴之间也连线、节点可以拖"
            onClick={() => setOverlayOpen(true)}
          >
            查看全部关系
          </Button>
          {onClean ? (
            <Button
              size="small"
              loading={reviewing}
              disabled={disabled || reviewing || cleanable === 0}
              title={cleanable === 0
                ? '没有可清洗的角色草稿：先跑一次角色扫描'
                : `让模型给这 ${cleanable} 个草稿角色归类，去掉报幕员/音效/占位符这类非角色`}
              onClick={onClean}
            >
              {cleanable > 0 ? `AI 清洗角色 · ${cleanable}` : 'AI 清洗角色'}
            </Button>
          ) : null}
          {onReview ? (
            <Button
              size="small"
              loading={reviewing}
              disabled={disabled || reviewing || reviewable === 0}
              title={reviewable === 0
                ? '没有可复核的规则边：先跑一次角色扫描，或者这些关系都已经人工确认过'
                : `把 ${reviewable} 对规则挖出的关系交给模型做判断题`}
              onClick={onReview}
            >
              {reviewable > 0 ? `AI 复核关系 · ${reviewable}` : 'AI 复核关系'}
            </Button>
          ) : null}
          <span className="rb-graph-chip">角色 <b>{characters.length}</b></span>
          <span className="rb-graph-chip">关系 <b>{rows.length}</b></span>
        </span>
      </div>

      <div className="rb-graph-body">
        <aside className="rb-graph-rail" aria-label="角色名册">
          <div className="rb-graph-rail-head">
            <span>角色名册</span>
            <span>{`${railRows.length} / ${characters.length}`}</span>
          </div>
          <Input
            allowClear
            size="small"
            placeholder="搜索角色…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
          <div className="rb-graph-rail-list">
            {railRows.map((card) => (
              <button
                key={card.id}
                type="button"
                className="rb-graph-rail-row"
                aria-pressed={card.id === focus.id}
                onClick={() => goFocus(card.id)}
              >
                <AvatarBlock card={card} size={24} />
                <span className="rb-graph-rail-name">{card.name || '未命名角色'}</span>
                <span className="rb-graph-rail-lines">{lineCountOf(card)}</span>
              </button>
            ))}
            {!railRows.length ? <p className="rb-graph-empty">没有匹配的角色，清空搜索框可以看全部。</p> : null}
          </div>
        </aside>

        <RelationGraphCanvas
          focus={focus}
          edges={edges}
          weak={showWeak ? weakAll : []}
          weakTotal={weakAll.length}
          rows={canvasRows}
          onFocus={goFocus}
          onBack={goBack}
          canBack={history.length > 0}
        />

        <aside className="rb-graph-panel" aria-label="关系证据">
          <div className="rb-graph-card-head">
            <AvatarBlock card={focus} size={52} />
            <div>
              <h3>{focus.name || '未命名角色'}</h3>
              <div className="rb-graph-card-meta">
                {`${lineCountOf(focus)} 句台词`}
                {focus.faction ? ` · ${focus.faction}` : ''}
              </div>
              <div className="rb-graph-card-meta">
                {`${detailRows.length} 条关系证据`}
                {rejectedDetail.length ? ` · ${rejectedDetail.length} 条已否决` : ''}
              </div>
            </div>
          </div>

          <div className="rb-graph-section">关系（点一行跳到对方）</div>
          {detailRows.length ? detailRows.map((row) => {
            const key = rowKey(row);
            const spec = categorySpec(row.category);
            const target = row.partner?.id ?? '';
            const isEditing = editing === key;
            return (
              <div className="rb-graph-rel" key={key}>
                <div className="rb-graph-rel-head">
                  <span className="rb-graph-tag" style={{ color: spec.color }}>{spec.label}</span>
                  <button
                    type="button"
                    className="rb-graph-rel-phrase"
                    title={target ? `以 ${row.partner?.name ?? row.target} 为焦点` : '名册里没有这个角色，无法跳转'}
                    disabled={!target}
                    onClick={() => target && goFocus(target)}
                  >
                    {relationPhrase(row, focus.id)}
                  </button>
                  <span className="rb-graph-rel-hit" title="命中次数">{`×${hitCount(row, rows)}`}</span>
                </div>
                {(() => {
                  const evidence = relationSamples(row);
                  if (!evidence.length) return <p className="rb-graph-rel-note is-empty">没有留存证据原文</p>;
                  return (
                    <p className="rb-graph-rel-note">
                      {evidence.slice(0, 2).map((line) => `「${line}」`).join(' ')}
                    </p>
                  );
                })()}
                <div className="rb-graph-rel-meta">
                  <span>{`关系词：${row.relation || '未写明'}`}</span>
                  <span>{`来源：${sourceLabel(row.source)}`}</span>
                </div>
                {isEditing ? (
                  <div className="rb-graph-edit">
                    <label>
                      关系词
                      <Input
                        size="small"
                        value={editWord}
                        disabled={disabled}
                        placeholder="例如 母亲 / 同事 / 宿敌"
                        onChange={(event) => setEditWord(event.target.value)}
                      />
                    </label>
                    <label>
                      类别
                      <Select
                        size="small"
                        value={editCategory}
                        disabled={disabled}
                        onChange={(value: string) => setEditCategory(value)}
                        options={RELATION_CATEGORIES.map((item) => ({ value: item.key, label: item.label }))}
                      />
                    </label>
                    <div className="rb-graph-edit-actions">
                      <Button
                        size="small"
                        type="primary"
                        disabled={disabled || !editWord.trim()}
                        onClick={() => commit(row, {
                          relation: editWord.trim(),
                          category: categorySpec(editCategory).key,
                        })}
                      >保存这条</Button>
                      <Button size="small" type="default" disabled={disabled} onClick={() => setEditing('')}>取消</Button>
                      <Button size="small" danger disabled={disabled} onClick={() => commit(row, null)}>删除这条</Button>
                    </div>
                  </div>
                ) : (
                  <div className="rb-graph-rel-actions">
                    <Button size="small" type="text" disabled={disabled} onClick={() => startEdit(row)}>改成手动</Button>
                  </div>
                )}
              </div>
            );
          }) : (
            <p className="rb-graph-empty">
              这个角色还没有挖到关系证据。可以打开顶部「显示只是同场的连线」看看他常和谁同场，
              或在「角色卡」里手动补一条关系。
            </p>
          )}

          {rejectedDetail.length ? (
            <>
              <button
                type="button"
                className="rb-graph-section rb-graph-section-toggle"
                onClick={() => setShowRejected((previous) => !previous)}
              >
                <span aria-hidden>{showRejected ? '▾' : '▸'}</span>
                <span>{`已否决 ${rejectedDetail.length} 条`}</span>
                <span className="rb-graph-section-hint">AI 复核判为不成立，画布上不画</span>
              </button>
              {showRejected ? rejectedDetail.map((row) => {
                const key = rowKey(row);
                const target = row.partner?.id ?? '';
                return (
                  <div className="rb-graph-rel is-rejected" key={key}>
                    <div className="rb-graph-rel-head">
                      <span className="rb-graph-tag is-muted">{categorySpec(row.category).label}</span>
                      <button
                        type="button"
                        className="rb-graph-rel-phrase"
                        title={target ? `以 ${row.partner?.name ?? row.target} 为焦点` : '名册里没有这个角色，无法跳转'}
                        disabled={!target}
                        onClick={() => target && goFocus(target)}
                      >
                        {relationPhrase(row, focus.id)}
                      </button>
                      <span className="rb-graph-rel-hit" title="命中次数">{`×${hitCount(row, rows)}`}</span>
                    </div>
                    {(() => {
                      const evidence = relationSamples(row);
                      return (
                        <>
                          {evidence.length ? (
                            <p className="rb-graph-rel-note">
                              {evidence.slice(0, 2).map((line) => `「${line}」`).join(' ')}
                            </p>
                          ) : null}
                          {rejectedReason(row.note) ? (
                            <p className="rb-graph-rel-note is-reason">{`AI 判为不成立：${rejectedReason(row.note)}`}</p>
                          ) : null}
                        </>
                      );
                    })()}
                    <div className="rb-graph-rel-meta">
                      <span>{`关系词：${row.relation || '未写明'}`}</span>
                      <span>{`来源：${sourceLabel(row.source)}`}</span>
                    </div>
                    <div className="rb-graph-rel-actions">
                      <Button size="small" type="text" disabled={disabled} onClick={() => restoreRejected(row)}>
                        恢复为手动
                      </Button>
                    </div>
                  </div>
                );
              }) : null}
            </>
          ) : null}

          <p className="rb-graph-manual-hint">
            <span aria-hidden>ⓘ</span>
            <span>
              点「改成手动」后可以改写关系词、类别或删除这条。手动关系保存后会标记为人工标注，
              重新扫描和 AI 复核都不会覆盖它。
            </span>
          </p>
          <p className="rb-graph-manual-hint">
            <span aria-hidden>ⓘ</span>
            <span>改完记得点右上角「保存修改」——这里改的是草稿，和其他字段一起按版本校验写入项目。</span>
          </p>
        </aside>
      </div>
      {overlayOpen && focus ? (
        <RelationOverlay
          focus={focus}
          characters={characters}
          // 浮层自己管「显示已否决」开关，所以这里给全量 rows，别先过滤。
          rows={rows}
          onFocus={(id) => goFocus(id)}
          onClose={() => setOverlayOpen(false)}
        />
      ) : null}
    </div>
  );
}
