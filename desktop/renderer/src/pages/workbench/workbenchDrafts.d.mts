/** 顶部草稿横幅的判定结果。 */
export interface DraftNotice {
  /** false 时整个横幅不画（草稿为 0，也没什么可收尾的）。 */
  visible: boolean;
  /** pending：还有草稿等审核；applied：刚才的草稿已应用完；none：什么都不说。 */
  tone: 'pending' | 'applied' | 'none';
  message: string;
}

/** AI 清洗 / 复核 / 推断按钮的判定结果。 */
export interface AiActionState {
  mode: 'clean' | 'review' | 'infer';
  /** 兜底后的可处理条数（0 表示按钮置灰）。 */
  count: number;
  blocked: boolean;
  /** 按钮文案：有对象时带数量，比如「AI 清洗角色 · 2」「AI 推断关系 · 1 对」。 */
  label: string;
  /** 置灰时显示在按钮旁边的可见原因；可用时为空串。 */
  hint: string;
}

/** 有多少对角色能交给「AI 推断关系」：有同场共现、且没有人工/否决边挡路。 */
export function countInferablePairs(characters: unknown): number;

export function resolveDraftNotice(input?: {
  characters?: number;
  worldbook?: number;
  generatedCharacters?: number;
  generatedWorldbook?: number;
}): DraftNotice;

export function resolveAiAction(input?: {
  mode?: 'clean' | 'review' | 'infer';
  count?: number;
  reviewing?: boolean;
  disabled?: boolean;
}): AiActionState;
