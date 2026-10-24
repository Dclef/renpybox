import assert from 'node:assert/strict';
import test from 'node:test';

import {
  bandPath,
  buildOverlayModel,
  buildTimelineModel,
  layoutRing,
  naturalCompare,
  nodeRadiusOf,
  overlayCenter,
  peerPath,
  resolveLabels,
  OVERLAY_VIEW_H,
  OVERLAY_VIEW_W,
} from '../renderer/src/pages/workbench/relationOverlayView.mjs';

const CHARACTERS = [
  { id: 'momoko', name: 'Momoko', line_count: 3332 },
  { id: 'airi', name: 'Airi', line_count: 4597 },
  { id: 'kimiko', name: 'Kimiko', line_count: 900 },
  { id: 'taka', name: 'Taka', line_count: 300 },
  { id: 'sada', name: 'Sada', line_count: 120 },
];
const BY_ID = new Map(CHARACTERS.map((card) => [card.id, card]));
const BY_NAME = new Map(CHARACTERS.map((card) => [card.name, card]));

function row(cardId, target, relation, extra = {}) {
  return {
    cardId,
    cardName: BY_ID.get(cardId)?.name ?? cardId,
    target,
    relation,
    category: 'family',
    note: '证据：hello',
    source: 'rule',
    partner: BY_NAME.get(target) ?? null,
    hits: 1,
    evidence: [],
    rejected: false,
    ...extra,
  };
}

function sampleRows() {
  return [
    row('momoko', 'Airi', '母亲', { hits: 214 }),
    row('momoko', 'Kimiko', '姐妹', { hits: 102 }),
    row('kimiko', 'Momoko', '姐妹', { hits: 102 }),
    row('taka', 'Momoko', '姐妹', { hits: 100 }),
    row('sada', 'Momoko', '姐妹', { hits: 68, source: 'rejected', rejected: true }),
    // 伙伴之间：两端都不是焦点。
    row('airi', 'Taka', '母亲', { hits: 5 }),
  ];
}

function model(extra = {}) {
  return buildOverlayModel({ focusId: 'momoko', rows: sampleRows(), byId: BY_ID, colorOf: () => '#E8A33D', ...extra });
}

test('按主关系词分组：我方叫法优先，组内按命中次数降序', () => {
  const built = model();
  assert.equal(built.partnerCount, 3);
  // Airi 是「母亲」（own 优先），Kimiko / Taka 是「姐妹」。
  assert.deepEqual(built.groups.map((group) => group.label), ['姐妹', '母亲']);
  const sisters = built.groups[0];
  assert.equal(sisters.members.length, 2);
  assert.deepEqual(sisters.members.map((partner) => partner.name), ['Kimiko', 'Taka']);
  // Kimiko 两边都写了「姐妹」，所以这一组有 3 条边。
  assert.equal(sisters.edges, 3);
  // Taka 只在别人卡里出现 → TA叫我；Kimiko 自己也写了 → 我叫TA。
  assert.equal(sisters.mixedDir, true);
  assert.equal(sisters.dirArrow, '↔');
  assert.equal(sisters.dirLabel, '互称');
});

test('命中次数 = Σ count，关系条数另算', () => {
  const built = model();
  const kimiko = built.partners.find((partner) => partner.name === 'Kimiko');
  assert.equal(kimiko.hits, 204);
  assert.equal(kimiko.rows.length, 2);
  assert.equal(kimiko.primaryDir, 'own');
  const taka = built.partners.find((partner) => partner.name === 'Taka');
  assert.equal(taka.primaryDir, 'incoming');
  assert.equal(built.edgeCount, 4);
  assert.equal(built.multiCount, 1);
});

test('AI 否决的边默认不画，但仍然计数；打开后进模型', () => {
  const hidden = model();
  assert.equal(hidden.rejectedCount, 1);
  assert.equal(hidden.partners.some((partner) => partner.name === 'Sada'), false);
  const shown = model({ showRejected: true });
  assert.equal(shown.partners.some((partner) => partner.name === 'Sada'), true);
  assert.equal(shown.rejectedCount, 1);
});

test('伙伴之间只保留两端都是焦点伙伴的边', () => {
  const built = model();
  assert.deepEqual(built.peers.map((peer) => `${peer.fromName}->${peer.toName}`), ['Airi->Taka']);
});

test('环形半径按人数 clamp 到 236..270', () => {
  const { cx, cy } = overlayCenter();
  assert.equal(cx, OVERLAY_VIEW_W / 2);
  assert.equal(cy, OVERLAY_VIEW_H / 2 + 6);

  const few = layoutRing({ groups: [{ members: [1, 2], hits: 0, edges: 0 }], cx, cy });
  assert.equal(few.R, 236);
  const manyMembers = Array.from({ length: 26 }, (_, i) => ({ id: `p${i}`, name: `P${i}` }));
  const many = layoutRing({ groups: [{ members: manyMembers, hits: 0, edges: 0 }], cx, cy });
  // 26 人：n*64/2π ≈ 264.8，落在 236..270 之间，没有顶到上限。
  assert.ok(Math.abs(many.R - (26 * 64) / (Math.PI * 2)) < 1e-9);
  assert.ok(many.R > 236 && many.R <= 270);
  // 40 人时才会顶到 270 上限。
  const crowded = layoutRing({
    groups: [{ members: Array.from({ length: 40 }, (_, i) => ({ id: `q${i}`, name: `Q${i}` })), hits: 0, edges: 0 }],
    cx,
    cy,
  });
  assert.equal(crowded.R, 270);
  // 26 人一圈：nodeR = clamp(13, 26, (2πR/n-10)/2)
  assert.equal(many.nodeR, Math.max(13, Math.min(26, ((Math.PI * 2 * many.R) / 26 - 10) / 2)));
  assert.equal(many.bandIn, many.R - 58);
  assert.equal(many.bandOut, many.R - 36);
  assert.equal(many.labelRing, many.R + 48);
});

test('扇区从 12 点方向顺时针铺开，角度之和 + 空隙 = 2π', () => {
  const { cx, cy } = overlayCenter();
  const built = model();
  const lay = layoutRing({ groups: built.groups, cx, cy });
  assert.equal(lay.groups.length, 2);
  assert.equal(lay.groups[0].start, -Math.PI / 2);
  for (let i = 1; i < lay.groups.length; i += 1) {
    assert.ok(lay.groups[i].start > lay.groups[i - 1].end);
  }
  const spanSum = lay.groups.reduce((sum, placed) => sum + placed.span, 0);
  assert.ok(Math.abs(spanSum + 0.19 * (lay.groups.length - 1) - Math.PI * 2) < 1e-9);
  // 人多的组扇区更大。
  assert.ok(lay.groups[0].span > lay.groups[1].span);
  // 每个伙伴都落在半径 R 上。
  for (const placed of lay.groups) {
    for (const item of placed.items) {
      const r = Math.hypot(item.x - cx, item.y - cy);
      assert.ok(Math.abs(r - lay.R) < 1e-6);
    }
  }
});

test('姓名牌角度冲突消解后不再互相重叠', () => {
  const entries = [
    { angle: 0, half: 0.2 },
    { angle: 0.05, half: 0.2 },
    { angle: 0.1, half: 0.2 },
    { angle: Math.PI, half: 0.2 },
  ];
  const resolved = resolveLabels(entries);
  const sorted = resolved.slice().sort((left, right) => left.angle - right.angle);
  for (let i = 0; i < sorted.length; i += 1) {
    const current = sorted[i];
    const next = sorted[(i + 1) % sorted.length];
    const gap = i === sorted.length - 1
      ? next.angle + Math.PI * 2 - current.angle
      : next.angle - current.angle;
    assert.ok(gap >= current.half + next.half + 0.012 - 1e-9, `第 ${i} 块牌子仍与下一块重叠：${gap}`);
  }
  // 入参不被就地改写。
  assert.equal(entries[0].angle, 0);
});

test('节点半径按台词量开方缩放，落在 14..nodeR', () => {
  const heavy = { lines: 100 };
  const light = { lines: 25 };
  assert.equal(nodeRadiusOf(heavy, 26, 100), 26);
  assert.equal(nodeRadiusOf(light, 26, 100), 14 + 12 * 0.5);
  assert.equal(nodeRadiusOf({ lines: 0 }, 26, 100), 14);
});

test('路径拼装：扇区带闭合、伙伴弧向圆心收', () => {
  const band = bandPath(534, 372, 0, 0.5, 212, 234);
  assert.ok(band.startsWith('M '));
  assert.ok(band.trim().endsWith('Z'));
  assert.equal(band.split('A').length - 1, 2);
  const peer = peerPath({ x1: 100, y1: 100, r1: 10, x2: 200, y2: 100, r2: 10, cx: 150, cy: 300 });
  assert.ok(peer.startsWith('M 110 100'));
  // 控制点比两端更靠近圆心（y 更大）。
  const controlY = Number(peer.split('Q')[1].trim().split(' ')[1]);
  assert.ok(controlY > 100);
});

// ---------------------------------------------------------------- 时间线矩阵

const CHAPTERS = {
  momoko: [
    { file: 'events10.rpy', line: 40, count: 3, samples: ['晚点再说吧。'] },
    { file: 'events2.rpy', line: 12, count: 9, samples: ['妈妈，我回来了。'] },
    { file: 'intro.rpy', line: 5, count: 2, samples: ['初次见面。'] },
  ],
  airi: [
    { file: 'events2.rpy', line: 30, count: 4, samples: ['你回来了。'] },
    { file: 'events2b.rpy', line: 8, count: 1, samples: ['……'] },
  ],
};

function chapterRow(cardId, target, relation, chapters, extra = {}) {
  return {
    cardId,
    cardName: BY_ID.get(cardId)?.name ?? cardId,
    target,
    relation,
    category: 'family',
    note: '',
    source: 'rule',
    partner: BY_NAME.get(target) ?? null,
    hits: chapters.reduce((sum, item) => sum + item.count, 0),
    evidence: [],
    chapters,
    rejected: false,
    ...extra,
  };
}

function timelineModel(extra = {}) {
  const rows = [
    chapterRow('momoko', 'Airi', '母亲', CHAPTERS.momoko),
    chapterRow('momoko', 'Kimiko', '姐妹', CHAPTERS.airi),
    // 只有被否决的边：默认整行不画。
    chapterRow('momoko', 'Sada', '姐妹', [{ file: 'events3.rpy', line: 9, count: 2, samples: ['嗯。'] }], {
      source: 'rejected',
      rejected: true,
    }),
  ];
  const base = buildOverlayModel({
    focusId: 'momoko',
    rows,
    byId: BY_ID,
    showRejected: Boolean(extra.showRejected),
    colorOf: () => '#E8A33D',
  });
  return buildTimelineModel({ groups: base.groups, partners: base.partners, showRejected: Boolean(extra.showRejected) });
}

test('时间线列按自然序排：events2 在 events10 前，intro 打头', () => {
  const built = timelineModel();
  assert.deepEqual(built.columns.map((column) => column.file), [
    'events2.rpy',
    'events2b.rpy',
    'events10.rpy',
    'intro.rpy',
  ]);
  // 列头去掉 .rpy，order 与下标一致。
  assert.deepEqual(built.columns.map((column) => column.label), ['events2', 'events2b', 'events10', 'intro']);
  assert.deepEqual(built.columns.map((column) => column.order), [0, 1, 2, 3]);
});

test('时间线格子聚合：同文件多条关系合并 count/samples，line 取最早', () => {
  const built = timelineModel();
  const airiRow = built.rows.find((entry) => entry.partner.name === 'Airi');
  const cell = airiRow.cells.get('events2.rpy');
  assert.equal(cell.count, 9);
  assert.equal(cell.line, 12);
  assert.deepEqual(cell.samples, ['妈妈，我回来了。']);
  assert.equal(airiRow.total, 14);
  // 没有证据的文件不产生格子。
  assert.equal(airiRow.cells.has('events3.rpy'), false);
  // maxCount 是「单个格子的最大命中数」，用来定色阶上限，不是行总计。
  assert.equal(built.maxCount, 9);
});

test('时间线首现标记：每行取列序最靠前的有证据文件', () => {
  const built = timelineModel();
  const airiRow = built.rows.find((entry) => entry.partner.name === 'Airi');
  // events2 的 order 是 0，比 events10(2)/intro(3) 都靠前。
  assert.equal(airiRow.firstFile, 'events2.rpy');
  const kimikoRow = built.rows.find((entry) => entry.partner.name === 'Kimiko');
  assert.equal(kimikoRow.firstFile, 'events2.rpy');
});

test('时间线行序沿用分组顺序，组内按 hits 降序', () => {
  const built = timelineModel();
  // Airi 是「母亲」组、Kimiko 是「姐妹」组；组间按人数降序，两组都是 1 人时按词排序。
  const names = built.rows.map((entry) => entry.partner.name);
  assert.equal(names.length, 2);
  assert.ok(names.includes('Airi') && names.includes('Kimiko'));
});

test('时间线默认跳过只有 rejected 的伙伴，打开开关后保留', () => {
  const hidden = timelineModel();
  assert.equal(hidden.rows.some((entry) => entry.partner.name === 'Sada'), false);
  assert.equal(hidden.columns.some((column) => column.file === 'events3.rpy'), false);

  const shown = timelineModel({ showRejected: true });
  assert.equal(shown.rows.some((entry) => entry.partner.name === 'Sada'), true);
  assert.equal(shown.columns.some((column) => column.file === 'events3.rpy'), true);
});

test('没有 chapters 的伙伴：行保留但标记 hasChapters=false', () => {
  const rows = [
    chapterRow('momoko', 'Airi', '母亲', CHAPTERS.momoko),
    chapterRow('momoko', 'Kimiko', '姐妹', []),
  ];
  const base = buildOverlayModel({ focusId: 'momoko', rows, byId: BY_ID, colorOf: () => '#E8A33D' });
  const built = buildTimelineModel({ groups: base.groups, partners: base.partners });
  const kimiko = built.rows.find((entry) => entry.partner.name === 'Kimiko');
  assert.equal(kimiko.hasChapters, false);
  assert.equal(kimiko.cells.size, 0);
  assert.equal(kimiko.firstFile, null);
  assert.equal(built.missingChapters, true);
});

test('自然序比较函数：数字段按数值比，其余按字符比', () => {
  assert.ok(naturalCompare('events2.rpy', 'events10.rpy') < 0);
  assert.ok(naturalCompare('events10.rpy', 'events2.rpy') > 0);
  assert.equal(naturalCompare('a.rpy', 'a.rpy'), 0);
  assert.ok(naturalCompare('chapter-9.rpy', 'chapter-10.rpy') < 0);
  // 前缀相同但长度不同：短的排前面。
  assert.ok(naturalCompare('events.rpy', 'events1.rpy') < 0);
});
