export type RowStatus = 'pending' | 'translated' | 'reviewed';

export interface Row {
  id: number;
  key: string;
  source: string;
  target: string;
  status: RowStatus;
}

export interface RowsStats {
  received: number;
  total: number;
  done: boolean;
  elapsedMs: number | null;
  /** 从点击加载到首批行渲染出来的耗时，用于验证「首屏 < 300ms」 */
  firstPaintMs: number | null;
}

export interface JobStats {
  jobId: string | null;
  done: number;
  total: number;
  running: boolean;
  finished: boolean;
}

export interface PerfSample {
  fps: number;
  minFps: number;
  longTasks: number;
  /** 主线程最大阻塞时长（ms） */
  maxBlockMs: number;
}