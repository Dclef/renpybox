/**
 * 「全部关系」浮层的纯逻辑：模型聚合、分组扇区布局、姓名角度消解、路径拼装。
 *
 * 放在 .mjs 里是为了让 `node --test` 能直接跑（项目里 agentView / proofreadingView 都是这个约定），
 * React 组件只负责把这些纯函数的返回值画成 SVG/HTML。原型见
 * docs/internal/2026-10-24/plan/overlay-v2.tpl.html，这里的公式与它逐段对应。
 */

export const OVERLAY_VIEW_W = 1068;
export const OVERLAY_VIEW_H = 732;
/** 圆心比几何中心低 6px：顶部留给标题和组卡片，视觉重心才落回画面中间。 */
export const OVERLAY_CENTER_Y_OFFSET = 6;

/** 每个人在圆环上至少占的弧长（px），少于这个值姓名牌必然打架。 */
export const MIN_ARC = 64;
/** 组与组之间的角度空隙（rad，约 11°）。 */
export const GROUP_GAP = 0.19;
/** 姓名牌之间额外留的角度空隙，避免边界贴在一起。 */
export const LABEL_MIN_GAP = 0.012;
/** 整组都是 AI 否决的边时用的灰色，和类别色区分开。 */
export const REJECTED_COLOR = '#9CA3AF';

const FALLBACK_COLOR = '#8B93A3';

export function overlayCenter() {
  return { cx: OVERLAY_VIEW_W / 2, cy: OVERLAY_VIEW_H / 2 + OVERLAY_CENTER_Y_OFFSET };
}

/** 台词数：与 relationGraph.lineCountOf 同口径（扫描统计优先，老快照退回抽样条数）。 */
function characterLines(card) {
  const scanned = Number(card && card.line_count);
  if (Number.isFinite(scanned) && scanned > 0) return scanned;
  return Array.isArray(card && card.sample_lines) ? card.sample_lines.length : 0;
}

function hitsOf(row) {
  const value = Number(row && row.hits);
  if (Number.isFinite(value) && value > 0) return value;
  const count = Number(row && row.count);
  if (Number.isFinite(count) && count > 0) return count;
  return 1;
}

function isRejectedRow(row) {
  if (row && row.rejected) return true;
  return String((row && row.source) || '').trim().toLowerCase() === 'rejected';
}

function byHitsDesc(left, right) {
  return hitsOf(right) - hitsOf(left);
}

/**
 * 以某人为中心聚合出「伙伴 → 组 → 伙伴之间」三层模型。
 *
 * 方向判定和 relationGraph.partnerEdges 一致：自己写的是 own（箭头落在伙伴身上），
 * 别人写到自己头上的是 incoming（箭头落在自己身上）。AI 否决的边默认整条跳过，
 * 但仍然计入 rejectedCount，供「显示已否决」开关显示数量。
 */
export function buildOverlayModel(options) {
  const { focusId, rows, byId, showRejected = false, colorOf = () => FALLBACK_COLOR } = options;
  const partners = new Map();
  const kept = [];
  let rejectedCount = 0;

  for (const row of rows || []) {
    if (!row || !row.partner) continue;
    const rejected = isRejectedRow(row);
    const other = row.cardId === focusId
      ? row.partner
      : row.partner.id === focusId
        ? (byId && byId.get ? byId.get(row.cardId) : null) || null
        : null;
    const touchesFocus = Boolean(other && other.id !== focusId);
    // 否决计数只算「和焦点有关」的边，别的角色的否决不该出现在这个人的浮层里。
    if (rejected && touchesFocus) rejectedCount += 1;
    if (rejected && !showRejected) continue;
    if (!touchesFocus) {
      // 不经过焦点的边留着当「伙伴之间」的候选，两端都得是焦点伙伴，后面再筛。
      if (row.cardId !== focusId && row.partner.id !== focusId) {
        kept.push({ row, rejected });
      }
      continue;
    }
    kept.push({ row, rejected });
    let partner = partners.get(other.id);
    if (!partner) {
      partner = {
        id: other.id,
        card: other,
        name: String(other.name || row.target || '').trim() || '未命名角色',
        lines: characterLines(other),
        rows: [],
        own: [],
        incoming: [],
        primary: null,
        primaryDir: 'own',
        relations: [],
        hits: 0,
      };
      partners.set(other.id, partner);
    }
    const dir = row.cardId === focusId ? 'own' : 'incoming';
    const entry = {
      ...row,
      dir,
      rejected,
      hits: hitsOf(row),
      relation: String(row.relation || '').trim(),
      category: row.category || 'other',
      cardName: String(row.cardName || '').trim(),
      evidence: Array.isArray(row.evidence) ? row.evidence : Array.isArray(row.samples) ? row.samples : [],
    };
    partner.rows.push(entry);
    if (dir === 'own') partner.own.push(entry);
    else partner.incoming.push(entry);
    partner.hits += entry.hits;
  }

  const list = [...partners.values()];
  for (const partner of list) {
    partner.own.sort(byHitsDesc);
    partner.incoming.sort(byHitsDesc);
    // 主关系词：我方叫法优先，其次对方叫法 —— 与 relationGraph.partnerEdges 同口径。
    // 被否决的边只在「这个人没有别的边」时才当主关系词，否则它会抢走正常关系的组。
    const accepted = (group) => group.filter((row) => !row.rejected);
    const pick = (group) => accepted(group).find((row) => row.source === 'manual') || accepted(group)[0] || null;
    const anyPick = (group) => group.find((row) => row.source === 'manual') || group[0] || null;
    partner.primary = pick(partner.own) || pick(partner.incoming) || anyPick(partner.own) || anyPick(partner.incoming);
    partner.primaryDir = partner.primary ? partner.primary.dir : partner.own.length ? 'own' : 'incoming';
    partner.relations = partner.rows.slice().sort(byHitsDesc);
    // 只有被否决的边才连到这个人时，节点整颗标灰：开了「显示已否决」也一眼分得清。
    partner.rejectedAll = partner.rows.length > 0 && partner.rows.every((row) => row.rejected);
  }

  // 先按主关系词分组，同一组内再按命中次数排序。
  const groups = [];
  const index = new Map();
  for (const partner of list) {
    if (!partner.primary) continue;
    const word = String(partner.primary.relation || '').trim() || '关系';
    let group = index.get(word);
    if (!group) {
      group = {
        key: word,
        label: word,
        category: partner.primary.category || 'other',
        color: FALLBACK_COLOR,
        dir: partner.primaryDir,
        dirArrow: '→',
        dirLabel: '我叫TA',
        dirText: '我的叫法',
        mixedDir: false,
        members: [],
        edges: 0,
        hits: 0,
      };
      index.set(word, group);
      groups.push(group);
    }
    group.members.push(partner);
    group.hits += partner.hits;
    if (group.dir !== partner.primaryDir) group.mixedDir = true;
  }
  // 组里的「N 条」算的是这一组关系词下所有边，含同一个人写的多重关系。
  for (const partner of list) {
    for (const row of partner.rows) {
      const word = String(row.relation || '').trim() || '关系';
      const group = index.get(word);
      if (group) group.edges += 1;
    }
  }
  for (const group of groups) {
    group.members.sort((left, right) => right.hits - left.hits || left.name.localeCompare(right.name));
    // 整组都是被否决的边：整块换成灰色，和正常关系组区分开。
    group.rejectedOnly = group.members.every((partner) => partner.rejectedAll);
    group.color = group.rejectedOnly ? REJECTED_COLOR : colorOf(group.category) || FALLBACK_COLOR;
    group.dirArrow = group.mixedDir ? '↔' : group.dir === 'own' ? '→' : '←';
    group.dirLabel = group.mixedDir ? '互称' : group.dir === 'own' ? '我叫TA' : 'TA叫我';
    group.dirText = group.mixedDir ? '双向' : group.dir === 'own' ? '我的叫法' : '对方的叫法';
  }
  groups.sort((left, right) => right.members.length - left.members.length || left.key.localeCompare(right.key));

  // 伙伴之间：两端都在伙伴集合里、且不经过焦点。
  const peers = [];
  for (const entry of kept) {
    const row = entry.row;
    if (row.cardId === focusId || row.partner.id === focusId) continue;
    if (!partners.has(row.cardId) || !partners.has(row.partner.id)) continue;
    peers.push({
      key: `${row.cardId}->${row.partner.id}`,
      fromId: row.cardId,
      toId: row.partner.id,
      fromName: String(row.cardName || '').trim() || '未命名角色',
      toName: String(row.partner.name || '').trim() || '未命名角色',
      relation: String(row.relation || '').trim(),
      category: row.category || 'other',
      hits: hitsOf(row),
      rejected: entry.rejected,
    });
  }

  const maxLines = Math.max(1, ...list.map((partner) => partner.lines));
  return {
    focusId,
    partners: list,
    groups,
    peers,
    partnerCount: list.length,
    edgeCount: list.reduce((sum, partner) => sum + partner.rows.length, 0),
    multiCount: list.filter((partner) => partner.rows.length > 1).length,
    rejectedCount,
    maxLines,
  };
}

/**
 * 时间线矩阵：伙伴 × 剧本文件。
 *
 * 行沿用概览的分组顺序（组间按人数降序、组内按 hits 降序），这样两个视图切来切去
 * 是同一批人同一个顺序，不会看花眼。列只保留真的有章节证据的文件，按自然序排
 * （events2 在 events10 前），空列不画 —— 全是空格的列除了撑宽画布没有别的用处。
 *
 * 格子聚合：同一个人在一个文件里可能有多条关系（我叫TA + TA叫我），count 相加、
 * samples 拼起来截前 2 条、first 取这些关系里最早出现的那一行。
 */
export function buildTimelineModel(options) {
  const { groups, partners, showRejected = false } = options || {};
  const acceptedOnly = (row) => !row.rejected;

  const partnerList = Array.isArray(partners) && partners.length
    ? partners
    : (groups || []).flatMap((group) => group.members);

  const files = new Map();
  const rows = [];
  for (const partner of partnerList) {
    const rowsOfPartner = Array.isArray(partner.rows) ? partner.rows : [];
    const usable = showRejected ? rowsOfPartner : rowsOfPartner.filter(acceptedOnly);
    // 只剩被否决的边：除非开了开关，这个人整行不画。
    if (!usable.length) continue;
    const cells = new Map();
    let total = 0;
    for (const row of usable) {
      const chapters = Array.isArray(row.chapters) ? row.chapters : [];
      for (const chapter of chapters) {
        const file = String(chapter && chapter.file || '').trim();
        if (!file) continue;
        const count = Number(chapter.count);
        const line = Number(chapter.line);
        const hits = Number.isFinite(count) && count > 0 ? count : 1;
        total += hits;
        if (!files.has(file)) files.set(file, file);
        const cell = cells.get(file);
        const samples = Array.isArray(chapter.samples) ? chapter.samples : [];
        if (!cell) {
          cells.set(file, {
            file,
            count: hits,
            line: Number.isFinite(line) && line > 0 ? line : 0,
            samples: samples.slice(0, 2),
            relations: [row],
          });
          continue;
        }
        cell.count += hits;
        if (Number.isFinite(line) && line > 0 && (cell.line <= 0 || line < cell.line)) cell.line = line;
        for (const sample of samples) {
          if (cell.samples.length >= 2) break;
          if (!cell.samples.includes(sample)) cell.samples.push(sample);
        }
        cell.relations.push(row);
      }
    }
    // 有边但后端还没补 chapters：这一行留空，至少让人知道关系存在、只是没有分布数据。
    rows.push({
      partner,
      cells,
      total,
      hasChapters: cells.size > 0,
      relationCount: usable.length,
    });
  }

  // 行按分组顺序落位：同一组的人连在一起，组间保持概览里的先后。
  const order = new Map();
  (groups || []).forEach((group, groupIndex) => {
    group.members.forEach((member, memberIndex) => {
      order.set(member.id, [groupIndex, memberIndex]);
    });
  });
  rows.sort((left, right) => {
    const a = order.get(left.partner.id) || [Number.MAX_SAFE_INTEGER, 0];
    const b = order.get(right.partner.id) || [Number.MAX_SAFE_INTEGER, 0];
    return a[0] - b[0] || a[1] - b[1] || right.total - left.total;
  });

  const columns = [...files.values()]
    .sort(naturalCompare)
    .map((file, position) => ({
      file,
      // 列头去掉 .rpy：文件名的信息量本来就在主干上。
      label: file.replace(/\.rp(y|yc)$/i, ''),
      order: position,
    }));

  // 每行的首现文件：只在那一格加描边，表示「关系从这一章建立」。
  const columnOrder = new Map(columns.map((column) => [column.file, column.order]));
  for (const entry of rows) {
    let first = null;
    for (const [file, cell] of entry.cells) {
      const at = columnOrder.get(file);
      if (at === undefined) continue;
      if (!first || at < first.order) first = { file, order: at, line: cell.line };
    }
    entry.firstFile = first ? first.file : null;
  }

  const maxCount = rows.reduce(
    (max, entry) => Math.max(max, ...[...entry.cells.values()].map((cell) => cell.count)),
    0,
  );

  return {
    columns,
    rows,
    maxCount: Math.max(1, maxCount),
    /** 有任何一行缺 chapters 时为 true，界面上要提示「后端还没补分布数据」。 */
    missingChapters: rows.some((entry) => !entry.hasChapters),
  };
}

/**
 * 自然序：逐字符扫描，遇到两边都是数字就把整段数字按数值比，
 * 于是 events2 排在 events10 前、chapter-9 排在 chapter-10 前，
 * 而 events.rpy（`.` < `1`）仍然排在 events1.rpy 前面。
 */
export function naturalCompare(left, right) {
  const a = String(left ?? '');
  const b = String(right ?? '');
  const isDigit = (char) => char >= '0' && char <= '9';
  let i = 0;
  let j = 0;
  while (i < a.length && j < b.length) {
    if (isDigit(a[i]) && isDigit(b[j])) {
      let ai = i;
      let bj = j;
      while (ai < a.length && isDigit(a[ai])) ai += 1;
      while (bj < b.length && isDigit(b[bj])) bj += 1;
      const diff = Number(a.slice(i, ai)) - Number(b.slice(j, bj));
      if (diff !== 0) return diff;
      // 数值相同但位数不同（"2" vs "02"）：短的排前面，保证顺序稳定。
      if (ai - i !== bj - j) return (ai - i) - (bj - j);
      i = ai;
      j = bj;
      continue;
    }
    if (a[i] !== b[j]) return a[i] < b[j] ? -1 : 1;
    i += 1;
    j += 1;
  }
  return (a.length - i) - (b.length - j);
}

/**
 * 分组扇区放射布局。
 *
 * R = clamp(236, 270, n*64/2π)：人少时环不缩得太小（避免中间空一块），人多时靠 270 封顶
 * （再大姓名牌就出画布了）。扇区角度 ∝ 人数，但每人至少 MIN_ARC 弧长；如果按比例分不够，
 * 就整体等比压缩，保证每组都还有呼吸空间。
 */
export function layoutRing(options) {
  const { groups, cx, cy } = options;
  const total = (groups || []).reduce((sum, group) => sum + group.members.length, 0);
  if (!total) {
    return {
      total: 0,
      R: 240,
      nodeR: 20,
      bandIn: 182,
      bandOut: 204,
      labelRing: 288,
      groups: [],
    };
  }
  const R = Math.max(236, Math.min(270, (total * MIN_ARC) / (Math.PI * 2)));
  const nodeR = Math.max(13, Math.min(26, ((Math.PI * 2 * R) / total - 10) / 2));
  const gap = groups.length > 1 ? GROUP_GAP : 0;
  const usable = Math.PI * 2 - gap * (groups.length - 1);
  const minSector = (count) => Math.max(0.42, (count * MIN_ARC) / R);
  const minSum = groups.reduce((sum, group) => sum + minSector(group.members.length), 0);

  let sectors;
  if (minSum >= usable) {
    sectors = groups.map((group) => (minSector(group.members.length) * usable) / minSum);
  } else {
    const extra = usable - minSum;
    sectors = groups.map((group) => minSector(group.members.length) + (extra * group.members.length) / total);
  }

  // 从 12 点方向顺时针铺开。
  let angle = -Math.PI / 2;
  const placed = [];
  groups.forEach((group, position) => {
    const span = sectors[position];
    const start = angle;
    const end = angle + span;
    const pad = Math.min(0.09, span * 0.12);
    const inner = Math.max(span - pad * 2, 0.001);
    const step = group.members.length > 1 ? inner / (group.members.length - 1) : 0;
    const items = group.members.map((partner, i) => {
      const a = group.members.length > 1 ? start + pad + step * i : start + span / 2;
      return { partner, angle: a, x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R };
    });
    placed.push({ group, start, end, mid: start + span / 2, span, items });
    angle = end + gap;
  });

  return {
    total,
    R,
    nodeR,
    bandIn: R - 58,
    bandOut: R - 36,
    labelRing: R + 48,
    groups: placed,
  };
}

/** 节点半径按台词量开方缩放：台词多的稍微大一点，但不会大过头像互相挤。 */
export function nodeRadiusOf(partner, nodeR, maxLines) {
  const lines = Math.max(0, Number(partner && partner.lines) || 0);
  const max = Math.max(1, Number(maxLines) || 1);
  const ratio = Math.sqrt(lines / max);
  return 14 + Math.max(0, nodeR - 14) * ratio;
}

/**
 * 姓名牌角度冲突消解：把每块牌子的半宽换算成弧度，相邻两块加起来超过角度间隔就把它们对推开。
 * 迭代若干轮后整体收敛（相邻推挤会把压力沿环传递），环上不会再有互相压住的牌子。
 */
export function resolveLabels(entries, iterations = 120) {
  const list = (entries || []).map((entry) => ({ ...entry }));
  const count = list.length;
  if (count < 2) return list;
  list.sort((left, right) => left.angle - right.angle);
  for (let round = 0; round < iterations; round += 1) {
    for (let i = 0; i < count; i += 1) {
      const current = list[i];
      const next = list[(i + 1) % count];
      // 最后一个和第一个之间要跨 2π，否则环的接缝处永远算成「没有间隔」。
      const gap = next === list[0]
        ? next.angle + Math.PI * 2 - current.angle
        : next.angle - current.angle;
      const need = current.half + next.half + LABEL_MIN_GAP;
      if (gap < need) {
        const push = (need - gap) / 2;
        current.angle -= push;
        next.angle += push;
      }
    }
  }
  return list;
}

function round2(value) {
  return Math.round(value * 100) / 100;
}

function pointAt(cx, cy, radius, angle) {
  return [round2(cx + Math.cos(angle) * radius), round2(cy + Math.sin(angle) * radius)];
}

/** 环形扇区带：外沿 a0→a1，直线收进内沿，再沿内沿退回。 */
export function bandPath(cx, cy, a0, a1, r1, r2) {
  const [o0x, o0y] = pointAt(cx, cy, r2, a0);
  const [o1x, o1y] = pointAt(cx, cy, r2, a1);
  const [i1x, i1y] = pointAt(cx, cy, r1, a1);
  const [i0x, i0y] = pointAt(cx, cy, r1, a0);
  const large = Math.abs(a1 - a0) > Math.PI ? 1 : 0;
  const sweep = a1 > a0 ? 1 : 0;
  return `M ${o0x} ${o0y} A ${round2(r2)} ${round2(r2)} 0 ${large} ${sweep} ${o1x} ${o1y}`
    + ` L ${i1x} ${i1y} A ${round2(r1)} ${round2(r1)} 0 ${large} ${1 - sweep} ${i0x} ${i0y} Z`;
}

/** 从圆心拉到扇区带的淡楔形，用来把「这一块属于哪一组」一路连回中心。 */
export function wedgePath(cx, cy, a0, a1, r) {
  const [x0, y0] = pointAt(cx, cy, r, a0);
  const [x1, y1] = pointAt(cx, cy, r, a1);
  const large = Math.abs(a1 - a0) > Math.PI ? 1 : 0;
  const sweep = a1 > a0 ? 1 : 0;
  return `M ${round2(cx)} ${round2(cy)} L ${x0} ${y0} A ${round2(r)} ${round2(r)} 0 ${large} ${sweep} ${x1} ${y1} Z`;
}

/**
 * 伙伴之间的细弧：控制点向圆心收 bend 比例，于是弧线鼓向中心而不是甩到画布外。
 * 端点按节点半径内缩，弧线才不会从头像下面钻出来。
 */
export function peerPath(options) {
  const { x1, y1, r1, x2, y2, r2, cx, cy, bend = 0.34 } = options;
  const dx = x2 - x1;
  const dy = y2 - y1;
  const length = Math.hypot(dx, dy) || 1;
  const p0x = x1 + (dx / length) * r1;
  const p0y = y1 + (dy / length) * r1;
  const p1x = x2 - (dx / length) * r2;
  const p1y = y2 - (dy / length) * r2;
  const mx = (p0x + p1x) / 2;
  const my = (p0y + p1y) / 2;
  const qx = mx + (cx - mx) * bend;
  const qy = my + (cy - my) * bend;
  return `M ${round2(p0x)} ${round2(p0y)} Q ${round2(qx)} ${round2(qy)} ${round2(p1x)} ${round2(p1y)}`;
}
