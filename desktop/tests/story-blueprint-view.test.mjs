/** 剧情蓝图纯函数层的单元测试（不启动 Electron / 不 build）。 */
import assert from 'node:assert/strict';
import test from 'node:test';

import {
  LAYOUT,
  MAX_SCALE,
  MIN_SCALE,
  buildSegments,
  centerOn,
  clampScale,
  clampView,
  cleanSay,
  colsForWidth,
  filterNodes,
  fitView,
  formatPercent,
  hasCjk,
  isNoiseTitle,
  isPlaceholder,
  isShowImage,
  imageSource,
  labelName,
  layoutNodes,
  nodeHeading,
  nodeStatus,
  progressCount,
  visibleIds,
} from '../renderer/src/pages/storyBlueprint/storyBlueprintView.mjs';

const node = (id, extra = {}) => ({
  id,
  chapter: extra.chapter ?? 'events1',
  file: extra.file ?? `${extra.chapter ?? 'events1'}.rpy`,
  line: extra.line ?? 1,
  end_line: 10,
  title_zh: extra.title_zh ?? null,
  title_src: extra.title_src ?? '',
  say: extra.say ?? 10,
  zh: extra.zh ?? 0,
  tl_blocks: extra.tl_blocks ?? 0,
  image: null,
  status: 'todo',
  placeholder: false,
});

test('layoutNodes：蛇形列优先，第 1 列反向', () => {
  const nodes = [node('a'), node('b'), node('c'), node('d')];
  const result = layoutNodes(nodes, { cols: 2 });
  // 4 个节点 / 2 列 = 每列 2 行：第 0 列 上→下，第 1 列 下→上
  assert.deepEqual(result.positions.a, { x: 0, y: 0 });
  assert.deepEqual(result.positions.b, { x: 0, y: LAYOUT.cardH + LAYOUT.gapY });
  assert.deepEqual(result.positions.c, {
    x: LAYOUT.cardW + LAYOUT.gapX,
    y: LAYOUT.cardH + LAYOUT.gapY,
  });
  assert.deepEqual(result.positions.d, { x: LAYOUT.cardW + LAYOUT.gapX, y: 0 });
  assert.equal(result.columns, 2);
  assert.equal(result.rows, 2);
});

test('layoutNodes：坐标唯一、数量一致、bounds 覆盖全部卡片', () => {
  const nodes = Array.from({ length: 69 }, (_, index) => node(`n${index}`));
  const result = layoutNodes(nodes);
  const keys = Object.values(result.positions).map((position) => `${position.x},${position.y}`);
  assert.equal(keys.length, 69);
  assert.equal(new Set(keys).size, 69);
  assert.equal(result.columns, 8);
  assert.equal(result.rows, 9);
  assert.equal(result.bounds.width, 8 * (LAYOUT.cardW + LAYOUT.gapX) - LAYOUT.gapX);
  assert.equal(result.bounds.height, 9 * (LAYOUT.cardH + LAYOUT.gapY) - LAYOUT.gapY);
});

test('layoutNodes：空数组不产生坐标，也不除零', () => {
  const result = layoutNodes([]);
  assert.deepEqual(result.positions, {});
  assert.equal(result.bounds.width, 0);
  assert.equal(formatPercent(0, 0), '0%');
});

test('nodeStatus：未译 / 部分 / 全译三档，没有台词算未译', () => {
  assert.equal(nodeStatus({ say: 10, zh: 0 }), 'todo');
  assert.equal(nodeStatus({ say: 10, zh: 3 }), 'part');
  assert.equal(nodeStatus({ say: 10, zh: 10 }), 'done');
  assert.equal(nodeStatus({ say: 0, zh: 0 }), 'todo');
  assert.equal(nodeStatus({ say: 10, zh: 12 }), 'done');
});

test('isPlaceholder：有 tl 块但零中文才算占位', () => {
  assert.equal(isPlaceholder({ tl_blocks: 32, zh: 0 }), true);
  assert.equal(isPlaceholder({ tl_blocks: 32, zh: 1 }), false);
  assert.equal(isPlaceholder({ tl_blocks: 0, zh: 0 }), false);
});

test('buildSegments：菜单/结尾两类边都画，悬空与重复丢弃', () => {
  const nodes = [node('a', { chapter: 'c1' }), node('b', { chapter: 'c2' })];
  const { positions } = layoutNodes(nodes);
  const edges = [
    { from: 'a', to: 'b', kind: 'menu', option_src: 'Go', option_zh: '去吧', line: 12 },
    { from: 'a', to: 'b', kind: 'menu', option_src: 'Go', option_zh: '去吧', line: 12 },
    { from: 'b', to: 'a', kind: 'jump', option_src: null, option_zh: null, line: 20 },
    { from: 'a', to: 'missing', kind: 'jump', option_src: null, option_zh: null, line: 33 },
  ];
  const segments = buildSegments(nodes, edges, positions);
  assert.equal(segments.length, 2);
  const [menu, jump] = segments;
  assert.equal(menu.kind, 'menu');
  assert.equal(menu.option_zh, '去吧');
  assert.equal(menu.cross, true);
  // a 在左、b 在右：起点取 a 的右边中点，终点取 b 的左边中点
  assert.equal(menu.x1, LAYOUT.cardW);
  assert.equal(menu.y1, LAYOUT.cardH / 2);
  assert.equal(jump.kind, 'jump');
  assert.equal(jump.cross, true);
});

test('buildSegments：左向边从卡片左边出发', () => {
  const nodes = [node('a'), node('b')];
  const { positions } = layoutNodes(nodes);
  const segments = buildSegments(nodes, [{ from: 'b', to: 'a', kind: 'jump' }], positions);
  assert.equal(segments.length, 1);
  assert.equal(segments[0].x1, positions.b.x);
  assert.equal(segments[0].x2, positions.a.x + LAYOUT.cardW);
});

test('filterNodes：label 名 / 英文首句 / 中文标题 / 文件名都能搜到', () => {
  const nodes = [
    node('intro', { title_src: 'This is my story', title_zh: '这是我的故事' }),
    node('event_kimiko', { file: 'events1.rpy', title_src: 'Hey!' }),
    node('bath', { chapter: 'events2', file: 'events2.rpy' }),
  ];
  assert.equal(filterNodes(nodes, { query: 'kimi' }).count, 1);
  assert.equal(filterNodes(nodes, { query: '我的故事' }).count, 1);
  assert.equal(filterNodes(nodes, { query: 'events2.rpy' }).count, 1);
  assert.equal(filterNodes(nodes, { query: '' }).count, 3);
  assert.equal(filterNodes(nodes, { query: 'nothing' }).count, 0);
});

test('filterNodes：状态筛选按三档口径', () => {
  const nodes = [
    node('done', { say: 5, zh: 5 }),
    node('part', { say: 5, zh: 2 }),
    node('todo', { say: 5, zh: 0 }),
  ];
  assert.deepEqual([...filterNodes(nodes, { status: 'done' }).ids], ['done']);
  assert.deepEqual([...filterNodes(nodes, { status: 'part' }).ids], ['part']);
  assert.deepEqual([...filterNodes(nodes, { status: 'todo' }).ids], ['todo']);
  assert.equal(filterNodes(nodes, { status: '' }).count, 3);
});

test('visibleIds：视口外的卡片不进 DOM，buffer 内保留', () => {
  const nodes = [node('near', { line: 1 }), node('far')];
  const positions = {
    near: { x: 0, y: 0 },
    far: { x: 6000, y: 6000 },
  };
  const view = { x: 0, y: 0, scale: 1 };
  const viewport = { width: 800, height: 600 };
  const visible = visibleIds(positions, view, viewport, 320);
  assert.equal(visible.has('near'), true);
  assert.equal(visible.has('far'), false);
  // 缩到 0.5 也只在视口附近，远的不该出现
  assert.equal(visibleIds(positions, view, viewport, 320).has('far'), false);
});

test('visibleIds：平移后原来在视口外、现在进来的卡片会被算进来', () => {
  const positions = { near: { x: 0, y: 0 }, far: { x: 2000, y: 0 } };
  const viewport = { width: 800, height: 600 };
  const before = visibleIds(positions, { x: 0, y: 0, scale: 1 }, viewport, 0);
  const after = visibleIds(positions, { x: -1900, y: 0, scale: 1 }, viewport, 0);
  assert.equal(before.has('far'), false);
  assert.equal(after.has('far'), true);
});

test('fitView：不缩放，横向居中、纵向贴顶（列数已按视口算好）', () => {
  const viewport = { width: 800, height: 600 };
  const view = fitView({ width: 700, height: 2000 }, viewport);
  assert.deepEqual(view, { x: 50, y: 24, scale: 1 });
  // 内容比视口宽时也不缩：保持 1:1，交给横向拖动。
  assert.deepEqual(fitView({ width: 2000, height: 400 }, viewport), { x: 24, y: 24, scale: 1 });
});

test('fitView：空 bounds 退回默认视图', () => {
  assert.deepEqual(fitView({ width: 0, height: 0 }, { width: 800, height: 600 }), { x: 24, y: 24, scale: 1 });
});

test('colsForWidth：按视口宽度决定列数，保证 1:1 铺满', () => {
  // 1014px 视口（应用主区实测）→ 5 列，每张卡 168 宽
  assert.equal(colsForWidth(1014), 5);
  assert.equal(colsForWidth(1600), 8);
  assert.equal(colsForWidth(640), 3);
  // 极端窄窗口也不少于 2 列
  assert.equal(colsForWidth(200), 2);
  // 卡片按算出的列数铺开后，总宽不超过视口
  const cols = colsForWidth(1014);
  const { bounds } = layoutNodes(Array.from({ length: 40 }, (_, i) => node(`n${i}`)), { cols });
  assert.ok(bounds.width <= 1014);
});

test('clampScale：夹在 MIN_SCALE..MAX_SCALE', () => {
  assert.equal(clampScale(0.01), MIN_SCALE);
  assert.equal(clampScale(99), MAX_SCALE);
  assert.equal(clampScale(1.2), 1.2);
});

test('formatPercent：整数不带小数点，一位小数其余情况', () => {
  assert.equal(formatPercent(0, 100), '0%');
  assert.equal(formatPercent(13, 42322), '0%');
  assert.equal(formatPercent(1, 8), '12.5%');
  assert.equal(formatPercent(1, 3), '33.3%');
  assert.equal(formatPercent(10, 10), '100%');
  assert.equal(formatPercent(5, 0), '0%');
});

test('centerOn：把指定卡片放到视口中心', () => {
  const view = centerOn({ x: 400, y: 300 }, { width: 800, height: 600 }, 1);
  assert.deepEqual(view, { x: 0, y: 0, scale: 1 });
});

test('hasCjk：中文范围判定与后端一致', () => {
  assert.equal(hasCjk('看来大家都来了。'), true);
  assert.equal(hasCjk('Hey, you!'), false);
  assert.equal(hasCjk(''), false);
});

test('progressCount：优先 progress，回退 cache_zh，再回退 zh', () => {
  assert.equal(progressCount({ progress: 21, cache_zh: 0, zh: 0 }), 21);
  assert.equal(progressCount({ cache_zh: 7, zh: 2 }), 7);
  assert.equal(progressCount({ zh: 2 }), 2);
});

test('clampView：内容小于视口时贴边留白，内容大时限制在 padding 内', () => {
  const viewport = { width: 800, height: 600 };
  // 内容 1000x500：横向可滚（范围 -280..80），纵向小于视口（20..80）
  assert.deepEqual(clampView({ x: -999, y: -999, scale: 1 }, { width: 1000, height: 500 }, viewport), { x: -280, y: 20, scale: 1 });
  assert.deepEqual(clampView({ x: 9999, y: 9999, scale: 1 }, { width: 1000, height: 500 }, viewport), { x: 80, y: 80, scale: 1 });
  // 内容 4000x3000：两轴都可滚，钳到 padding 边界
  const big = clampView({ x: -99999, y: 99999, scale: 1 }, { width: 4000, height: 3000 }, viewport);
  assert.equal(big.x, -3280);
  assert.equal(big.y, 80);
});

// ---- 标题可辨识性（用户 m01889「大纲我有点没看懂」） ----
test('labelName 把 label 名变成人话', () => {
  assert.equal(labelName('event_knight_follow_to_bathroom'), 'knight follow to bathroom');
  assert.equal(labelName('scene_living_room'), 'living room');
  assert.equal(labelName(''), '');
});

test('cleanSay 去掉 Ren\'Py 标记但保留插值', () => {
  assert.equal(cleanSay('{b}Soldier{/b} "Same night"'), 'Soldier "Same night"');
  // `[mom]` 是角色名占位，保留；删掉会得到「是的， 。」这种断句
  assert.equal(cleanSay('Hey [mom]! Where?'), 'Hey [mom]! Where?');
});

test('nodeHeading 跳过省略号标题，退回 label 名', () => {
  assert.deepEqual(
    nodeHeading({ id: 'event_knight_follow_to_bathroom', title_src: '...', title_zh: null }),
    { title: 'knight follow to bathroom', subtitle: '' },
  );
  assert.deepEqual(
    nodeHeading({ id: 'event_knight_morning_wake_up', title_src: 'Morning already?', title_zh: '已经早上了吗？' }),
    { title: '已经早上了吗？', subtitle: 'knight morning wake up' },
  );
  assert.equal(nodeHeading({ id: 'x', title_src: '', title_zh: null }).title, 'x');
});

test('isNoiseTitle 只把纯标点当噪音', () => {
  assert.equal(isNoiseTitle('...'), true);
  assert.equal(isNoiseTitle('?!'), true);
  assert.equal(isNoiseTitle('Wow!'), false);
});

test('imageSource：show 兜底图与 scene 背景分得开，老数据缺 source 按 scene', () => {
  assert.equal(imageSource({ path: 'images/cap1.jpg', source: 'show' }), 'show');
  assert.equal(imageSource({ path: 'images/bg room.jpg', source: 'scene' }), 'scene');
  // v0.9.7 之前后端只出 scene 图，没有 source 字段；不能凭空冒出「来自 show」。
  assert.equal(imageSource({ path: 'images/bg room.jpg' }), 'scene');
  assert.equal(imageSource(null), 'scene');
  assert.equal(imageSource(undefined), 'scene');
  // 脏 source 值也按 scene 处理，避免把未知来源标成 show。
  assert.equal(imageSource({ path: 'x.jpg', source: 'gallery' }), 'scene');
});

test('isShowImage 只对 show 兜底图返回 true', () => {
  assert.equal(isShowImage({ path: 'images/cap1.jpg', source: 'show' }), true);
  assert.equal(isShowImage({ path: 'images/bg room.jpg', source: 'scene' }), false);
  assert.equal(isShowImage({ path: 'images/bg room.jpg' }), false);
  assert.equal(isShowImage(null), false);
});
