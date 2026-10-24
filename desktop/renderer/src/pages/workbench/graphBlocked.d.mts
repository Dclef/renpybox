/** 关系图谱空态引导的判定结果。 */
export interface GraphBlockedCard {
  /** 触发的体检阶段；unknown 表示体检结果还没回来。 */
  stage: 'unknown' | 'unbound' | 'no_game' | 'packed' | 'no_script' | 'ready';
  title: string;
  detail: string;
  /** 该给人点的那一个动作；null 表示没有可点的按钮。 */
  action: 'scan' | 'bind' | 'unpack' | null;
  actionLabel: string;
}

export function resolveGraphBlocked(readiness: unknown): GraphBlockedCard;
export function scanBlockedHint(canScan: boolean): string;
