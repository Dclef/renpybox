/**
 * 剧情蓝图的纯计算层：蛇形布局、连线端点、过滤、视口裁剪、适配缩放。
 *
 * 这些函数不依赖 React / DOM / antd，`node --test` 直接 import 就能测；
 * 页面组件只负责把结果画出来。口径与后端 `module/Story/BlueprintScanner.py`
 * 一致（状态、占位判定都在这里再算一遍，用于徽章与筛选）。
 */

/**
 * 卡片尺寸与默认列数。
 *
 * 卡片按「不缩放也看得清」设计：168×118 在 scale=1 时标题是 11px、缩略图 72px 高，
 * 再缩小就会出现「字只有 7px、点不准」的情况 —— 所以列数按视口宽度算，
 * 保证永远以 scale=1 铺满，而不是把整张图压小塞进视口。
 */
export const LAYOUT = Object.freeze({ cardW: 168, cardH: 118, gapX: 14, gapY: 16, cols: 8 });

export const MIN_SCALE = 0.25;
export const MAX_SCALE = 2.5;
/** 视口外还要多建多少世界坐标像素的卡片，避免拖动时空白。 */
export const CULL_BUFFER = 320;

/**
 * 按视口宽度算「一屏能放几列」，让卡片始终以 scale=1 显示。
 * 至少 2 列、最多 10 列；窗口很窄时也不至于把卡片压扁。
 */
export function colsForWidth(viewportWidth, options = {}) {
  const layout = { ...LAYOUT, ...options };
  const cardW = Number(layout.cardW);
  const gapX = Number(layout.gapX);
  const padding = Number(options.padding ?? 24);
  const usable = Math.max(cardW * 2, (Number(viewportWidth) || 0) - padding * 2);
  const raw = Math.floor((usable + gapX) / (cardW + gapX));
  return Math.min(10, Math.max(2, raw || 2));
}

/** 与后端 CJK 区间一致，仅用于把中文标题判定为「真中文」。 */
const CJK_RE = /[\u3400-\u9fff\uf900-\ufaff]/;

export function hasCjk(text) {
  return CJK_RE.test(String(text ?? ''));
}

/**
 * 真实已译行数：后端给了 `progress` 就用它（有缓存时按缓存口径），
 * 老数据只有 `zh` 时退回 tl 中文行数。
 */
export function progressCount(node) {
  const progress = Number(node?.progress);
  if (Number.isFinite(progress) && node?.progress !== undefined && node?.progress !== null) return progress;
  const cache = Number(node?.cache_zh ?? 0);
  return cache > 0 ? cache : Number(node?.zh ?? 0);
}

/**
 * label 名变成人话：`event_knight_follow_to_bathroom` → `knight follow to bathroom`。
 *
 * 首句台词经常是 `...` / `Wow!`（1012 个 label 里 311 个是纯省略号），
 * 光看台词分不清是哪一段；label 名虽然英文，但稳定且唯一，适合当副标题。
 */
export function labelName(id) {
  return String(id ?? '')
    .replace(/^event_|^scene_|^label_/, '')
    .replace(/_/g, ' ')
    .trim();
}

/**
 * 去掉 Ren'Py 文本标记 `{b}`，和后端 `clean_say` 口径一致。
 *
 * `[mom]` 这种插值是角色名占位，删掉会让中文变成「是的， 。」，所以保留。
 */
export function cleanSay(text) {
  return String(text ?? '')
    .replace(/\{[^{}]*\}/g, ' ')
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.!?;:，。！？；：])/g, '$1')
    .trim();
}

/** 只有标点/省略号的标题等于没标题。 */
export function isNoiseTitle(text) {
  const stripped = String(text ?? '').trim();
  return stripped === '' || /^[\s.\u2026,!?~\-—_]+$/.test(stripped);
}

/**
 * 行标题与副标题。
 *
 * 标题优先级：能认出来的中文 → 能认出来的英文 → label 名。
 * 副标题固定放 label 名（和标题不同时才显示），这样 `...` 也能被认出来。
 */
export function nodeHeading(node) {
  const zh = cleanSay(node?.title_zh);
  const src = cleanSay(node?.title_src);
  const name = labelName(node?.id);
  const pick = !isNoiseTitle(zh) && zh.length >= 4 ? zh : !isNoiseTitle(src) && src.length >= 4 ? src : '';
  const title = pick || name || String(node?.id ?? '');
  return { title, subtitle: name && name !== title ? name : '' };
}

/** 与后端口径一致：0 行已译 = 未译；已译行数达到台词行数 = 全译；中间 = 部分。 */
export function nodeStatus(node) {
  const say = Number(node?.say ?? 0);
  const done = progressCount(node);
  if (say <= 0 || done <= 0) return 'todo';
  return done >= say ? 'done' : 'part';
}

/** tl 里有翻译块、但一行真译文都没有 —— 游戏里看着「翻译过」，实际是英文占位。 */
export function isPlaceholder(node) {
  return Number(node?.tl_blocks ?? 0) > 0 && progressCount(node) === 0;
}

/**
 * 这张图的来源：'scene' 是场景背景，'show' 是立绘/插图兜底。
 *
 * 旧后端返回的 image 没有 source 字段，一律按 'scene' 处理 —— 那时能出图的
 * 本来就只可能是 scene，这样老数据观感不变，也不会凭空冒出「来自 show」徽标。
 */
export function imageSource(image) {
  return image?.source === 'show' ? 'show' : 'scene';
}

/** 是否为 show 兜底图：前端据此在图片角落标注来源，避免被误认成背景。 */
export function isShowImage(image) {
  return imageSource(image) === 'show';
}

/**
 * 蛇形布局（列优先）：第 0 列从上到下，第 1 列从下到上，以此类推。
 *
 * 返回的 positions 始终覆盖全部节点 —— 视口裁剪只裁 DOM，不裁这份坐标，
 * 否则搜索、连线、跳转定位都会失效。
 */
export function layoutNodes(nodes, options = {}) {
  const layout = { ...LAYOUT, ...options };
  const cardW = Number(layout.cardW);
  const cardH = Number(layout.cardH);
  const gapX = Number(layout.gapX);
  const gapY = Number(layout.gapY);
  const cols = Math.max(1, Math.floor(Number(layout.cols) || LAYOUT.cols));
  const list = Array.isArray(nodes) ? nodes : [];
  const positions = {};
  if (list.length === 0) {
    return { positions, columns: 0, rows: 0, bounds: { width: 0, height: 0 } };
  }
  const rows = Math.max(1, Math.ceil(list.length / cols));

  list.forEach((node, index) => {
    const column = Math.floor(index / rows);
    const offset = index % rows;
    const row = column % 2 === 0 ? offset : rows - 1 - offset;
    positions[node.id] = { x: column * (cardW + gapX), y: row * (cardH + gapY) };
  });

  return {
    positions,
    columns: Math.min(cols, Math.max(1, Math.ceil(list.length / rows))),
    rows,
    bounds: {
      width: Math.min(cols, Math.ceil(list.length / rows)) * (cardW + gapX) - gapX,
      height: rows * (cardH + gapY) - gapY,
    },
  };
}

/**
 * 把边落成可画的线段：从卡片侧边中点连到另一张卡的侧边中点。
 * `to` 不在 positions 里的边直接丢弃（悬空跳转、被过滤掉的章节）。
 */
export function buildSegments(nodes, edges, positions, options = {}) {
  const layout = { ...LAYOUT, ...options };
  const cardW = Number(layout.cardW);
  const cardH = Number(layout.cardH);
  const byId = new Map((Array.isArray(nodes) ? nodes : []).map((node) => [node.id, node]));
  const seen = new Set();
  const segments = [];

  for (const edge of Array.isArray(edges) ? edges : []) {
    const from = edge?.from;
    const to = edge?.to;
    const origin = positions?.[from];
    const target = positions?.[to];
    if (!origin || !target || !byId.has(from) || !byId.has(to)) continue;
    const kind = edge.kind === 'jump' ? 'jump' : 'menu';
    const dedupeKey = `${from}|${to}|${kind}|${edge.option_src ?? ''}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);

    const rightward = target.x > origin.x;
    segments.push({
      key: `${kind}:${dedupeKey}`,
      from,
      to,
      kind,
      option_src: edge.option_src ?? null,
      option_zh: edge.option_zh ?? null,
      line: Number(edge.line ?? 0),
      x1: rightward ? origin.x + cardW : origin.x,
      y1: origin.y + cardH / 2,
      x2: rightward ? target.x : target.x + cardW,
      y2: target.y + cardH / 2,
      cross: (byId.get(from)?.chapter ?? '') !== (byId.get(to)?.chapter ?? ''),
    });
  }
  return segments;
}

/** 搜索匹配 label 名、英文首句、中文标题与文件名；status 为空表示不筛。 */
export function filterNodes(nodes, filters = {}) {
  const query = String(filters.query ?? '').trim().toLowerCase();
  const status = String(filters.status ?? '');
  const ids = new Set();
  for (const node of Array.isArray(nodes) ? nodes : []) {
    if (status && nodeStatus(node) !== status) continue;
    if (query) {
      const haystack = [node.id, node.title_src, node.title_zh, node.file]
        .map((value) => String(value ?? '').toLowerCase());
      if (!haystack.some((value) => value.includes(query))) continue;
    }
    ids.add(node.id);
  }
  return { ids, count: ids.size };
}

/** 只把「视口 + buffer」内的卡片交给 DOM；坐标换算成世界坐标再判断。 */
export function visibleIds(positions, view, viewport, buffer = CULL_BUFFER) {
  const scale = Number(view?.scale) || 1;
  const width = Number(viewport?.width) || 0;
  const height = Number(viewport?.height) || 0;
  const left = (-(Number(view?.x) || 0)) / scale - buffer;
  const top = (-(Number(view?.y) || 0)) / scale - buffer;
  const right = left + width / scale + buffer * 2;
  const bottom = top + height / scale + buffer * 2;
  const ids = new Set();
  for (const [id, position] of Object.entries(positions ?? {})) {
    const x = position.x;
    const y = position.y;
    if (x + LAYOUT.cardW < left || x > right || y + LAYOUT.cardH < top || y > bottom) continue;
    ids.add(id);
  }
  return ids;
}

/**
 * 进入章节时的初始视图：横向居中、纵向从顶部开始、**不缩放**。
 *
 * 早先是「把整张图缩小到塞进视口」（events8 得到 0.63），结果是卡片 105×74、
 * 字 7px，既看不清也点不准。列数已按视口宽度算好，这里保持 scale=1 即可。
 */
export function fitView(bounds, viewport, padding = 24) {
  const width = Math.max(0, Number(bounds?.width) || 0);
  const extent = Number(viewport?.width) || 0;
  if (width <= 0) return { x: padding, y: padding, scale: 1 };
  return { x: Math.max(padding, (extent - width) / 2), y: padding, scale: 1 };
}

/**
 * 全览：刻意缩小到整章都看得见（卡片会变小、字变细，只用来判断结构）。
 * 与 fitView 的区别：fitView 保持 1:1 只看一屏，fitAllView 才是「缩略全景」。
 */
export function fitAllView(bounds, viewport, padding = 24) {
  const width = Math.max(0, Number(bounds?.width) || 0);
  const height = Math.max(0, Number(bounds?.height) || 0);
  const availableW = Math.max(1, (Number(viewport?.width) || 0) - padding * 2);
  const availableH = Math.max(1, (Number(viewport?.height) || 0) - padding * 2);
  if (width <= 0 || height <= 0) return { x: padding, y: padding, scale: 1 };
  const scale = clampScale(Math.min(availableW / width, availableH / height, 1));
  return {
    x: Math.max(padding, ((Number(viewport?.width) || 0) - width * scale) / 2),
    y: Math.max(padding, ((Number(viewport?.height) || 0) - height * scale) / 2),
    scale,
  };
}

/**
 * 把平移量钳制在内容边界内：内容比视口大时可以拖到边缘，但不会整幅拖丢。
 * 之前滚轮/拖拽没有钳制，随手一滚就把内容推出视口，看起来像「空白」。
 */
export function clampView(view, bounds, viewport, padding = 80) {
  const scale = clampScale(Number(view?.scale) || 1);
  const width = Math.max(1, Number(bounds?.width) || 0) * scale;
  const height = Math.max(1, Number(bounds?.height) || 0) * scale;
  const axis = (value, content, extent) => {
    const free = extent - content;
    const low = Math.min(padding, free - padding);
    const high = Math.max(free - padding, padding);
    return Math.min(Math.max(Number(value) || 0, low), high);
  };
  return {
    x: axis(view?.x, width, Number(viewport?.width) || 0),
    y: axis(view?.y, height, Number(viewport?.height) || 0),
    scale,
  };
}

export function clampScale(scale) {
  const value = Number(scale) || 1;
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, value));
}

/** 覆盖率文案：0% / 12.3% / 100%，整数不带小数点。 */
export function formatPercent(zh, say) {
  const total = Number(say) || 0;
  const done = Number(zh) || 0;
  if (total <= 0 || done <= 0) return '0%';
  const percent = Math.min(100, (done / total) * 100);
  if (percent >= 100) return '100%';
  const rounded = Math.round(percent * 10) / 10;
  return `${Number.isInteger(rounded) ? rounded.toFixed(0) : rounded.toFixed(1)}%`;
}

/** 章节切换、跳转定位共用：把某个 label 居中到视口。 */
export function centerOn(position, viewport, scale = 1) {
  const width = Number(viewport?.width) || 0;
  const height = Number(viewport?.height) || 0;
  const factor = clampScale(scale);
  return {
    x: width / 2 - (Number(position?.x) || 0) * factor,
    y: height / 2 - (Number(position?.y) || 0) * factor,
    scale: factor,
  };
}
