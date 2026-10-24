/**
 * 关系图谱的数据整理。
 *
 * 角色卡里的 relations 是有方向的：`{ target, relation }` 表示「target 是这张卡主人的 relation」，
 * 例如 Momoko 卡里的「母亲 → Airi」读作 Airi 是 Momoko 的母亲。
 * 画布的箭头方向和右侧详情的中文短句都由这里派生；改边时按 cardId + index 定位回角色卡的
 * relations 数组，所以图谱自己不留一份状态，永远跟着草稿走。
 */

export interface CharacterAvatar {
  /** 命中的目录名：faces / headshots / portraits。 */
  kind: string;
  /** 相对 game/ 的图片路径（/ 分隔）。施工单写的是 relative，后端落盘字段是 relative_path，两个都收。 */
  relative: string;
  relative_path?: string;
  width: number;
  height: number;
}

export interface CharacterRelation {
  /** 对方的显示名。 */
  target: string;
  /** 中文关系词，如「母亲」。 */
  relation: string;
  /** family | romantic | friendly | hostile | work | other。 */
  category: string;
  /** 证据原文。 */
  note: string;
  /** rule | ai | manual | rejected；manual 的边后端不会被重新扫描或 AI 覆盖，rejected 是 AI 复核否决的边。 */
  source: string;
  /** 命中次数：后端暂时不返回，缺了按 1 计、再按两人之间的证据条数兜底。 */
  count?: number | null;
  /** 证据台词（后端新版返回，旧快照没有）；缺了回退 note 去掉「证据：」前缀。 */
  samples?: string[] | null;
  /** 按剧本文件切分的命中分布；旧快照没有，缺了当空数组。 */
  chapters?: RelationChapter[] | null;
}

/** 一条关系在某个剧本文件里的命中分布。 */
export interface RelationChapter {
  /** 相对 game/ 的路径，POSIX 分隔符，保留 .rpy。 */
  file: string;
  /** 该文件里第一次命中所在行号（1 起）。 */
  line: number;
  /** 该文件内的命中次数（≥1）。 */
  count: number;
  /** 该文件里的证据原文，最多 2 条。 */
  samples: string[];
}

/** AI 复核否决的边：数据保留、默认不画，可以恢复成人工关系。 */
export const RELATION_SOURCE_REJECTED = 'rejected';

/** 工作台角色卡：图谱只用到其中一部分字段，其余原样带过去。 */
export interface WorkbenchCharacter {
  id: string;
  name: string;
  name_translation: string;
  aliases: string[];
  match_keywords: string[];
  identity: string;
  personality: string;
  speech_style: string;
  relationship_notes: string;
  prompt_notes: string;
  sample_lines: string[];
  enabled: boolean;
  is_primary: boolean;
  /** 立绘信息由后端同步中，字段可能缺失（后端无头像时给 null），缺了就退回名字色块。 */
  avatar?: Partial<CharacterAvatar> | null;
  relations?: CharacterRelation[] | null;
  /** 同场证据：对方名字 → 同场场景数，用来补「只是同场」的虚线。 */
  co_occurrence?: Record<string, number> | null;
  status?: unknown;
  /** 扫描统计的台词句数；老快照里没有这个字段时退回抽样条数。 */
  line_count?: number | null;
  faction?: string | null;
}

export interface RelationCategorySpec {
  key: string;
  label: string;
  color: string;
}

/** 关系类别配色固定写在 SVG 里，不跟主题令牌走：浅色主题下也要能分得清。 */
export const RELATION_CATEGORIES: RelationCategorySpec[] = [
  { key: 'family', label: '亲属', color: '#E8A33D' },
  { key: 'romantic', label: '恋慕', color: '#E86AA6' },
  { key: 'friendly', label: '友好', color: '#4FB477' },
  { key: 'hostile', label: '敌对', color: '#E05C5C' },
  { key: 'work', label: '主从同僚', color: '#5B9BD5' },
  { key: 'other', label: '其他', color: '#8B93A3' },
];

const FALLBACK_CATEGORY: RelationCategorySpec = RELATION_CATEGORIES[5];

/** 未知类别统一落到「其他」，避免画布上出现没有颜色的边。 */
export function categorySpec(value: string): RelationCategorySpec {
  const key = (value || '').trim().toLowerCase();
  return RELATION_CATEGORIES.find((spec) => spec.key === key) ?? FALLBACK_CATEGORY;
}

const SOURCE_LABELS: Record<string, string> = { manual: '手动', ai: 'AI 推断', rule: '规则挖掘', rejected: 'AI 否决' };

export function sourceLabel(value: string): string {
  return SOURCE_LABELS[(value || '').trim().toLowerCase()] ?? '来源未标';
}

/** 后端字段可能还没齐：relations 缺失或不是数组时一律按空列表兜底。 */
export function relationsOfCard(card: WorkbenchCharacter): CharacterRelation[] {
  return Array.isArray(card.relations) ? card.relations : [];
}

export function coOccurrenceOfCard(card: WorkbenchCharacter): Record<string, number> {
  const value = card.co_occurrence;
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const counts: Record<string, number> = {};
  for (const [name, count] of Object.entries(value)) {
    const key = String(name).trim();
    const weight = Number(count);
    if (key && Number.isFinite(weight) && weight > 0) counts[key] = weight;
  }
  return counts;
}

export function lineCountOf(card: WorkbenchCharacter): number {
  // 台词数由扫描统计进角色卡。老快照里没有 line_count 时才退回抽样条数——
  // 那是 sample_lines 的长度，只够表示「有没有样本」，不能当台词数用。
  const scanned = Number(card.line_count);
  if (Number.isFinite(scanned) && scanned > 0) return scanned;
  return Array.isArray(card.sample_lines) ? card.sample_lines.length : 0;
}

/** 名字归一化：比较用，不改变展示。 */
export function nameKey(value: string): string {
  return String(value ?? '').trim().toLocaleLowerCase();
}

export interface CharacterIndex {
  byId: Map<string, WorkbenchCharacter>;
  byName: Map<string, WorkbenchCharacter>;
}

/** 名字索引：正式名字优先，别名和匹配关键词只在没登记过时补位，避免抢走别人的名字。 */
export function indexCharacters(characters: WorkbenchCharacter[]): CharacterIndex {
  const byId = new Map<string, WorkbenchCharacter>();
  const byName = new Map<string, WorkbenchCharacter>();
  for (const card of characters) {
    if (card.id) byId.set(card.id, card);
    const keys = [card.name, card.name_translation, ...(card.aliases ?? []), ...(card.match_keywords ?? [])];
    for (const key of keys) {
      const name = nameKey(key);
      if (name && !byName.has(name)) byName.set(name, card);
    }
  }
  return { byId, byName };
}

function normalizeSamples(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const list: string[] = [];
  for (const item of value) {
    const text = String(item ?? '').trim();
    if (text && !list.includes(text)) list.push(text);
  }
  return list;
}

/**
 * 自然序比较：把字符串切成「文字段 / 数字段」逐段比，
 * 于是 events2 排在 events10 前面，chapter-9 排在 chapter-10 前面。
 */
export function naturalCompare(left: string, right: string): number {
  const split = (value: string) => String(value ?? '').match(/(\d+|\D+)/g) ?? [];
  const a = split(left);
  const b = split(right);
  const length = Math.min(a.length, b.length);
  for (let i = 0; i < length; i += 1) {
    const leftPart = a[i];
    const rightPart = b[i];
    const leftNum = /^\d/.test(leftPart);
    const rightNum = /^\d/.test(rightPart);
    if (leftNum && rightNum) {
      const diff = Number(leftPart) - Number(rightPart);
      if (diff !== 0) return diff;
      // 数字相同但位数不同（"02" vs "2"）时按字符串兜底，保证顺序稳定。
      if (leftPart !== rightPart) return leftPart < rightPart ? -1 : 1;
      continue;
    }
    if (leftPart !== rightPart) return leftPart < rightPart ? -1 : 1;
  }
  return a.length - b.length;
}

/**
 * 章节规范化：file 必须非空，count 至少 1，samples 最多 2 条，
 * 同一文件出现多次就合并（count 相加、samples 去重、line 取最早），最后按自然序排。
 */
export function normalizeChapters(value: unknown): RelationChapter[] {
  if (!Array.isArray(value)) return [];
  const merged = new Map<string, RelationChapter>();
  for (const item of value) {
    if (!item || typeof item !== 'object') continue;
    const raw = item as Partial<RelationChapter>;
    const file = String(raw.file ?? '').trim().replace(/\\/g, '/');
    if (!file) continue;
    const count = Number(raw.count);
    const line = Number(raw.line);
    const samples = normalizeSamples(raw.samples).slice(0, 2);
    const hit = merged.get(file);
    if (hit) {
      hit.count += Number.isFinite(count) && count > 0 ? count : 1;
      if (Number.isFinite(line) && line > 0 && (hit.line <= 0 || line < hit.line)) hit.line = line;
      for (const sample of samples) {
        if (hit.samples.length >= 2) break;
        if (!hit.samples.includes(sample)) hit.samples.push(sample);
      }
      continue;
    }
    merged.set(file, {
      file,
      line: Number.isFinite(line) && line > 0 ? line : 0,
      count: Number.isFinite(count) && count > 0 ? count : 1,
      samples,
    });
  }
  return [...merged.values()].sort((left, right) => naturalCompare(left.file, right.file));
}

/** 一条关系按剧本文件排好序的章节；旧快照没有 chapters 时返回空数组。 */
export function relationChapters(row: Pick<CharacterRelation, 'chapters'>): RelationChapter[] {
  return normalizeChapters(row.chapters);
}

function normalizeRelation(raw: CharacterRelation): CharacterRelation | null {
  if (!raw || typeof raw !== 'object') return null;
  const target = String(raw.target ?? '').trim();
  if (!target) return null;
  const count = Number(raw.count);
  const samples = normalizeSamples(raw.samples);
  const chapters = normalizeChapters(raw.chapters);
  return {
    target,
    relation: String(raw.relation ?? '').trim(),
    category: String(raw.category ?? 'other').trim().toLowerCase() || 'other',
    note: String(raw.note ?? '').trim(),
    source: String(raw.source ?? '').trim().toLowerCase(),
    ...(Number.isFinite(count) && count > 0 ? { count } : {}),
    ...(samples.length ? { samples } : {}),
    ...(chapters.length ? { chapters } : {}),
  };
}

/** 一条关系证据，带上它归属的角色卡和在数组里的下标。 */
export interface RelationRowRef extends CharacterRelation {
  /** 关系归属的角色卡（方向里的 from 一方）。 */
  cardId: string;
  cardName: string;
  /** 在归属卡 relations 数组里的下标，改或删都按它定位。 */
  index: number;
  /** 另一端的角色卡；名册里没有这个人时为 null（只有证据，画不出节点）。 */
  partner: WorkbenchCharacter | null;
  /** 命中次数：后端 count ?? 1，画布和面板的 ×N 都读它。 */
  hits: number;
  /** 证据台词：samples ?? []，空了由调用方回退 note。 */
  evidence: string[];
  /** 按剧本文件排好序的命中分布；没有 chapters 时是空数组。 */
  chapters: RelationChapter[];
  /** AI 复核否决的边：默认不画、不进主列表。 */
  rejected: boolean;
}

/** 证据台词：优先 samples，没有时回退 note 去掉「证据：」前缀。 */
export function relationSamples(row: Pick<CharacterRelation, 'samples' | 'note'>): string[] {
  const samples = normalizeSamples(row.samples);
  if (samples.length) return samples;
  const note = String(row.note ?? '').trim();
  if (!note) return [];
  const stripped = note.startsWith('证据：') ? note.slice('证据：'.length).trim() : note;
  return stripped ? [stripped] : [];
}

export function buildRelationRows(characters: WorkbenchCharacter[]): RelationRowRef[] {
  const index = indexCharacters(characters);
  const rows: RelationRowRef[] = [];
  for (const card of characters) {
    relationsOfCard(card).forEach((raw, position) => {
      const relation = normalizeRelation(raw);
      if (!relation) return;
      const partner = index.byName.get(nameKey(relation.target)) ?? null;
      // 指向自己的边不画，否则圆环上会出现一个和自己头像重名的节点。
      if (partner && partner.id === card.id) return;
      rows.push({
        ...relation,
        cardId: card.id,
        cardName: card.name,
        index: position,
        partner,
        hits: typeof relation.count === 'number' && relation.count > 0 ? relation.count : 1,
        evidence: relationSamples(relation),
        chapters: relationChapters(relation),
        rejected: relation.source === RELATION_SOURCE_REJECTED,
      });
    });
  }
  return rows;
}

/** 默认要画的边：AI 否决的先剔掉，画布和主列表都不该出现它们。 */
export function visibleRows(rows: RelationRowRef[]): RelationRowRef[] {
  return rows.filter((row) => !row.rejected);
}

/** AI 否决的边：单独成节，灰色删除线展示，可以恢复成人工关系。 */
export function rejectedRows(rows: RelationRowRef[]): RelationRowRef[] {
  return rows.filter((row) => row.rejected);
}

/** 恢复一条被否决的边：只把 source 改回 manual，走原来的草稿保存路径。 */
export function restoreRejectedRows<C extends WorkbenchCharacter>(characters: C[], keys: Set<string>): C[] {
  if (!keys.size) return characters;
  return characters.map((card) => {
    const relations = relationsOfCard(card);
    let changed = false;
    const next = relations.map((raw, position) => {
      if (!keys.has(`${card.id}#${position}`)) return raw;
      if (String(raw.source ?? '').trim().toLowerCase() !== RELATION_SOURCE_REJECTED) return raw;
      changed = true;
      return { ...raw, source: 'manual' };
    });
    return changed ? { ...card, relations: next } : card;
  });
}

/** 中心和某个伙伴之间的合并视图：两个人可能各写了一条关系。 */
export interface PartnerEdge {
  partner: WorkbenchCharacter;
  /** 两个人之间的全部关系行，焦点自己写的排前面。 */
  rows: RelationRowRef[];
  /** 焦点写的（焦点是 from）：箭头落在伙伴身上。 */
  own: RelationRowRef[];
  /** 伙伴写的（焦点是 to）：箭头落在焦点身上。 */
  incoming: RelationRowRef[];
  label: string;
  category: string;
  note: string;
  /** 关系条数（两边的行数合计）。 */
  count: number;
  /** 命中次数合计：Σ count，图上的 ×N 和面板的「X 次」都用它。 */
  hits: number;
}

/** 焦点视角的伙伴列表：只保留和焦点直接相连的关系。 */
export function partnerEdges(
  focusId: string,
  rows: RelationRowRef[],
  byId: Map<string, WorkbenchCharacter>,
): PartnerEdge[] {
  const grouped = new Map<string, PartnerEdge>();
  for (const row of rows) {
    if (!row.partner) continue;
    // 方向有两种：焦点自己写的（另一端是 target），或别人写到他头上的（另一端是作者本人）。
    // 这里必须分清楚，否则「别人说我是他母亲」这类边会整条丢掉。
    const other = row.cardId === focusId ? row.partner
      : row.partner.id === focusId ? (byId.get(row.cardId) ?? null)
        : null;
    if (!other || other.id === focusId) continue;
    const current = grouped.get(other.id) ?? {
      partner: other, rows: [], own: [], incoming: [], label: '', category: 'other', note: '', count: 0, hits: 0,
    };
    current.rows.push(row);
    if (row.cardId === focusId) current.own.push(row);
    else current.incoming.push(row);
    grouped.set(other.id, current);
  }
  for (const edge of grouped.values()) {
    // 主标签优先用焦点自己的说法；人工标注过的边优先，免得被规则边盖住。
    const pick = (list: RelationRowRef[]) => list.find((row) => row.source === 'manual') ?? list[0];
    const best = pick(edge.own) ?? pick(edge.incoming);
    edge.label = best?.relation ?? '';
    edge.category = best?.category ?? 'other';
    edge.note = (edge.own.find((row) => row.note) ?? edge.incoming.find((row) => row.note))?.note ?? '';
    edge.count = edge.rows.length;
    edge.hits = edge.rows.reduce((sum, row) => sum + (row.hits > 0 ? row.hits : 1), 0);
  }
  return [...grouped.values()];
}

/** 伙伴与伙伴之间的细弧：只要两人之间有过任意一条关系就画。 */
export function pairRowBetween(rows: RelationRowRef[], aId: string, bId: string): RelationRowRef | null {
  return rows.find((row) => (row.cardId === aId && row.partner?.id === bId)
    || (row.cardId === bId && row.partner?.id === aId)) ?? null;
}

/** 右侧详情：焦点自己写的在前，别人写到他头上的在后。 */
export function focusRelationRows(focusId: string, rows: RelationRowRef[]): RelationRowRef[] {
  const own = rows.filter((row) => row.cardId === focusId);
  const incoming = rows.filter((row) => row.cardId !== focusId && row.partner?.id === focusId);
  return [...own, ...incoming];
}

/** 方向明确的中文短句：自己的说法是「我的X是 对方」，别人的说法是「某某的X是我」。 */
export function relationPhrase(row: RelationRowRef, focusId: string): string {
  const other = row.partner?.name ?? row.target;
  if (row.cardId === focusId) return row.relation ? `我的${row.relation}是 ${other}` : `${other}（没写明称谓）`;
  return row.relation ? `${row.cardName} 的${row.relation}是我` : `${row.cardName} 没写明我是什么人`;
}

export interface WeakPartner {
  card: WorkbenchCharacter;
  weight: number;
}

/** 只有同场记录、没有语义关系的角色，按同场次数降序；已画在圆环上的排除。 */
export function weakPartners(focus: WorkbenchCharacter, index: CharacterIndex, exclude: Set<string>): WeakPartner[] {
  const seen = new Set<string>();
  const result: WeakPartner[] = [];
  for (const [name, weight] of Object.entries(coOccurrenceOfCard(focus))) {
    const card = index.byName.get(nameKey(name));
    if (!card || card.id === focus.id || exclude.has(card.id) || seen.has(card.id)) continue;
    seen.add(card.id);
    result.push({ card, weight });
  }
  return result.sort((left, right) => right.weight - left.weight);
}

/** 关系里两个人之间的「命中次数」：后端给了 count 就用它，否则数同一对人的证据条数。 */
export function hitCount(row: RelationRowRef | undefined, rows: RelationRowRef[]): number {
  if (!row) return 1;
  if (typeof row.count === 'number' && row.count > 0) return row.count;
  if (!row.partner) return 1;
  return rows.filter((item) => (item.cardId === row.cardId && item.partner?.id === row.partner?.id)
    || (item.partner?.id === row.cardId && item.cardId === row.partner?.id)).length || 1;
}

/** 没有头像时用角色 ID 映射到固定色相，同一个人每次都是同一个颜色。 */
export function fallbackColor(card: { id: string; name: string }): string {
  const seed = card.id || card.name || '?';
  let hue = 0;
  for (let position = 0; position < seed.length; position += 1) {
    hue = (hue * 31 + seed.charCodeAt(position)) % 360;
  }
  return `hsl(${hue} 52% 40%)`;
}

export function firstLetter(card: { name: string }): string {
  return (card.name || '?').slice(0, 1).toUpperCase();
}

/**
 * 这个「名字」像不像一个角色。
 *
 * 抽取阶段会把不是人的东西也塞进 name 字段：Ren'Py 插值占位（`[mom]`）、
 * 拼接出来的组合名（`[me] & Girls`）、带斜杠的分组标题。它们进图谱只会变成
 * 一堆没头像、没关系的孤点，所以在画之前挡掉。
 */
export function isLikelyCharacter(card: { name: string }): boolean {
  const name = String(card.name ?? '').trim();
  if (!name) return false;
  return !/[[\]&/\\]/.test(name);
}
