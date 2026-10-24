/** relationOverlayView.mjs 的类型声明：组件里只用到这些形状。 */

export const OVERLAY_VIEW_W: number;
export const OVERLAY_VIEW_H: number;
export const OVERLAY_CENTER_Y_OFFSET: number;
export const MIN_ARC: number;
export const GROUP_GAP: number;
export const LABEL_MIN_GAP: number;
export const REJECTED_COLOR: string;

export function overlayCenter(): { cx: number; cy: number };

export interface OverlayRowInput {
  target?: string;
  relation?: string;
  category?: string;
  note?: string;
  source?: string;
  count?: number | null;
  samples?: string[] | null;
  cardId: string;
  cardName?: string;
  index?: number;
  partner?: { id: string; name: string; line_count?: number | null; sample_lines?: string[] } | null;
  hits?: number;
  rejected?: boolean;
  evidence?: string[];
}

export interface OverlayCharacter {
  id: string;
  name: string;
  line_count?: number | null;
  sample_lines?: string[];
  /** 立绘信息；时间线行头的头像要用它（与 relationGraph.CharacterAvatar 同形）。 */
  avatar?: Partial<{
    kind: string;
    relative: string;
    relative_path?: string;
    width: number;
    height: number;
  }> | null;
}

export interface OverlayRow extends OverlayRowInput {
  dir: 'own' | 'incoming';
  rejected: boolean;
  hits: number;
  relation: string;
  category: string;
  cardName: string;
  evidence: string[];
  partner: NonNullable<OverlayRowInput['partner']>;
}

export interface OverlayPartner {
  id: string;
  card: OverlayCharacter;
  name: string;
  lines: number;
  rows: OverlayRow[];
  own: OverlayRow[];
  incoming: OverlayRow[];
  primary: OverlayRow | null;
  primaryDir: 'own' | 'incoming';
  relations: OverlayRow[];
  hits: number;
  rejectedAll: boolean;
}

export interface OverlayGroup {
  key: string;
  label: string;
  category: string;
  color: string;
  dir: 'own' | 'incoming';
  dirArrow: string;
  dirLabel: string;
  dirText: string;
  mixedDir: boolean;
  rejectedOnly: boolean;
  members: OverlayPartner[];
  edges: number;
  hits: number;
}

export interface OverlayPeer {
  key: string;
  fromId: string;
  toId: string;
  fromName: string;
  toName: string;
  relation: string;
  category: string;
  hits: number;
  rejected: boolean;
}

export interface OverlayModel {
  focusId: string;
  partners: OverlayPartner[];
  groups: OverlayGroup[];
  peers: OverlayPeer[];
  partnerCount: number;
  edgeCount: number;
  multiCount: number;
  rejectedCount: number;
  maxLines: number;
}

export function buildOverlayModel(options: {
  focusId: string;
  rows: OverlayRowInput[];
  byId: Map<string, OverlayCharacter>;
  showRejected?: boolean;
  colorOf?: (category: string) => string;
}): OverlayModel;

export interface RingItem {
  partner: OverlayPartner;
  angle: number;
  x: number;
  y: number;
}

export interface PlacedGroup {
  group: OverlayGroup;
  start: number;
  end: number;
  mid: number;
  span: number;
  items: RingItem[];
}

export interface RingLayout {
  total: number;
  R: number;
  nodeR: number;
  bandIn: number;
  bandOut: number;
  labelRing: number;
  groups: PlacedGroup[];
}

export function layoutRing(options: { groups: OverlayGroup[]; cx: number; cy: number }): RingLayout;

export function nodeRadiusOf(partner: OverlayPartner, nodeR: number, maxLines: number): number;

export interface LabelEntry {
  angle: number;
  half: number;
}

export function resolveLabels<T extends LabelEntry>(entries: T[], iterations?: number): T[];

export function bandPath(cx: number, cy: number, a0: number, a1: number, r1: number, r2: number): string;
export function wedgePath(cx: number, cy: number, a0: number, a1: number, r: number): string;
export function peerPath(options: {
  x1: number;
  y1: number;
  r1: number;
  x2: number;
  y2: number;
  r2: number;
  cx: number;
  cy: number;
  bend?: number;
}): string;

/** 自然序：events2 排在 events10 前。 */
export function naturalCompare(left: string, right: string): number;

export interface TimelineCell {
  file: string;
  count: number;
  line: number;
  samples: string[];
  relations: OverlayRow[];
}

export interface TimelineRow {
  partner: OverlayPartner;
  cells: Map<string, TimelineCell>;
  total: number;
  hasChapters: boolean;
  relationCount: number;
  /** 该伙伴最早出现的文件；没有章节数据时为 null。 */
  firstFile: string | null;
}

export interface TimelineColumn {
  file: string;
  /** 去掉 .rpy 的列头文字。 */
  label: string;
  order: number;
}

export interface TimelineModel {
  columns: TimelineColumn[];
  rows: TimelineRow[];
  maxCount: number;
  missingChapters: boolean;
}

export function buildTimelineModel(options: {
  groups: OverlayGroup[];
  partners?: OverlayPartner[];
  showRejected?: boolean;
}): TimelineModel;
