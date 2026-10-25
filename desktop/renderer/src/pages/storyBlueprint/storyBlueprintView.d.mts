/** 剧情蓝图纯计算层的类型声明（供渲染端 import type 使用）。 */

/** 图片来自哪类语句：`scene` 是场景背景（正常口径），`show` 是立绘/插图兜底。
 * 旧后端返回的 image 没有这个字段，一律按 'scene' 处理。 */
export type StoryBlueprintImageSource = 'scene' | 'show';

export interface StoryBlueprintImage {
  /** 相对 game/ 的路径，正斜杠；由 /api/story-blueprint/asset 回源。 */
  path: string;
  kind: 'image' | 'video';
  tag: string;
  note?: string;
  /** 缺省（旧数据）视为 'scene'。 */
  source?: StoryBlueprintImageSource;
}

export type StoryBlueprintStatus = 'done' | 'part' | 'todo';

export interface StoryBlueprintNode {
  id: string;
  chapter: string;
  file: string;
  line: number;
  end_line: number;
  title_zh: string | null;
  title_src: string;
  say: number;
  zh: number;
  /** 应用翻译缓存里命中并翻好的台词行数；没有缓存时为 0。 */
  cache_zh: number;
  /** 实际用于进度口径的行数：有缓存用缓存，否则用 tl 的中文行数。 */
  progress: number;
  tl_blocks: number;
  image: StoryBlueprintImage | null;
  /** 该 label 内能解析成图片的 show 标签数量；缺省视为 0。
   * 只给数量不给列表：卡片只需要「这段有几张演出图」的提示。 */
  show_image_count?: number;
  status: StoryBlueprintStatus;
  placeholder: boolean;
}

export interface StoryBlueprintEdge {
  from: string;
  to: string;
  kind: 'menu' | 'jump';
  option_src: string | null;
  option_zh: string | null;
  line: number;
}

export interface StoryBlueprintChapter {
  id: string;
  file: string;
  labels: number;
  say: number;
  zh: number;
  cache_zh: number;
  progress: number;
}

export interface StoryBlueprintStats {
  chapters: number;
  labels: number;
  say_lines: number;
  zh_lines: number;
  cache_lines: number;
  translated_labels: number;
  labels_with_image: number;
  edges: number;
  menu_edges: number;
  jump_edges: number;
  placeholder_labels: number;
  progress_source: 'cache' | 'tl';
}

export interface StoryBlueprintProject {
  project_key: string;
  game_dir: string;
  tl_dir: string;
  language: string;
  /** 命中的翻译缓存目录；为空表示没找到缓存，进度退回 tl 口径。 */
  cache?: string;
}

export interface StoryBlueprintLine {
  line: number;
  speaker: string;
  src: string;
  dst: string | null;
  status: 'done' | 'empty';
}

export interface StoryBlueprintLabelDetail {
  ok: boolean;
  id: string;
  chapter: string;
  file: string;
  line: number;
  end_line: number;
  title_src: string;
  title_zh: string | null;
  say: number;
  cache_zh: number;
  image: StoryBlueprintImage | null;
  show_image_count?: number;
  status: StoryBlueprintStatus;
  lines: StoryBlueprintLine[];
}

/** 项目体检结论：决定蓝图页是出图、还是给引导。
 * - unbound   还没绑定 Ren'Py 工程
 * - no_game   绑了，但解析出的 game 目录不存在
 * - packed    有 .rpa 但没有 .rpy：必须先解包
 * - no_script game 在，但既没 rpy 也没 rpa
 * - ready     有 .rpy，可以出图
 */
export type StoryBlueprintStage = 'unbound' | 'no_game' | 'packed' | 'no_script' | 'ready';

export interface StoryBlueprintReadiness {
  ok: boolean;
  stage: StoryBlueprintStage;
  game_dir: string;
  rpy_files: number;
  rpa_files: number;
  has_tl: boolean;
  has_cache: boolean;
  language: string;
}

export interface StoryBlueprintResponse {
  ok: boolean;
  project: StoryBlueprintProject;
  stats: StoryBlueprintStats;
  chapters: StoryBlueprintChapter[];
  nodes: StoryBlueprintNode[];
  edges: StoryBlueprintEdge[];
}

export interface Position {
  x: number;
  y: number;
}

export interface LayoutOptions {
  cardW?: number;
  cardH?: number;
  gapX?: number;
  gapY?: number;
  cols?: number;
}

export interface LayoutResult {
  positions: Record<string, Position>;
  columns: number;
  rows: number;
  bounds: { width: number; height: number };
}

export interface View {
  x: number;
  y: number;
  scale: number;
}

export interface Viewport {
  width: number;
  height: number;
}

export interface Segment {
  key: string;
  from: string;
  to: string;
  kind: 'menu' | 'jump';
  option_src: string | null;
  option_zh: string | null;
  line: number;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  cross: boolean;
}

export interface Filters {
  query?: string;
  status?: StoryBlueprintStatus | '';
}

export const LAYOUT: Readonly<{ cardW: number; cardH: number; gapX: number; gapY: number; cols: number }>;
export const MIN_SCALE: number;
export const MAX_SCALE: number;
export const CULL_BUFFER: number;

export function hasCjk(text: unknown): boolean;
export function progressCount(node: Pick<StoryBlueprintNode, 'zh' | 'cache_zh'>): number;
export function labelName(id: unknown): string;
export function cleanSay(text: unknown): string;
export function isNoiseTitle(text: unknown): boolean;
export function nodeHeading(node: Pick<StoryBlueprintNode, 'id' | 'title_src' | 'title_zh'>): {
  title: string;
  subtitle: string;
};
export function nodeStatus(node: Pick<StoryBlueprintNode, 'say' | 'zh' | 'cache_zh'>): StoryBlueprintStatus;
export function isPlaceholder(node: Pick<StoryBlueprintNode, 'tl_blocks' | 'zh' | 'cache_zh'>): boolean;

/** 图片来源：'scene' 场景背景 / 'show' 立绘插图兜底；缺 source 的旧数据按 'scene'。 */
export function imageSource(image: { source?: StoryBlueprintImageSource } | null | undefined): StoryBlueprintImageSource;

/** 是否 show 兜底图，卡片/详情据此标注「来自 show」。 */
export function isShowImage(image: { source?: StoryBlueprintImageSource } | null | undefined): boolean;
export function layoutNodes(nodes: StoryBlueprintNode[], options?: LayoutOptions): LayoutResult;
export function buildSegments(
  nodes: StoryBlueprintNode[],
  edges: StoryBlueprintEdge[],
  positions: Record<string, Position>,
  options?: LayoutOptions,
): Segment[];
export function filterNodes(
  nodes: StoryBlueprintNode[],
  filters?: Filters,
): { ids: Set<string>; count: number };
export function visibleIds(
  positions: Record<string, Position>,
  view: View,
  viewport: Viewport,
  buffer?: number,
): Set<string>;
export function colsForWidth(
  viewportWidth: number,
  options?: LayoutOptions & { padding?: number },
): number;
export function fitView(
  bounds: { width: number; height: number },
  viewport: Viewport,
  padding?: number,
): View;
export function clampScale(scale: number): number;
export function fitAllView(
  bounds: { width: number; height: number },
  viewport: Viewport,
  padding?: number,
): View;
export function clampView(
  view: View,
  bounds: { width: number; height: number },
  viewport: Viewport,
  padding?: number,
): View;
export function formatPercent(zh: number, say: number): string;
export function centerOn(position: Position | undefined, viewport: Viewport, scale?: number): View;
