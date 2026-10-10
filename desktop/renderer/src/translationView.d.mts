import type { TokenEstimate, TranslationState } from './types';

export interface TranslationCommands {
  start: boolean;
  continueTask: boolean;
  stop: boolean;
  exportFile: boolean;
  retryFailed: boolean;
  confirmRestart: boolean;
}

export function hasTranslationCache(progress: Record<string, unknown> | null | undefined): boolean;

export function translationCommands(
  snapshot: Pick<TranslationState, 'engine_status' | 'stop_barrier' | 'single_tasks' | 'progress'>,
  options?: { busy?: boolean; ready?: boolean },
): TranslationCommands;

export function mergeProgressUpdate(
  previous: Record<string, unknown>,
  update: Record<string, unknown>,
): Record<string, unknown>;

export function mergeTranslationSnapshot(
  previous: TranslationState | null,
  next: TranslationState,
  progressChangedDuringRequest: boolean,
): TranslationState;

export function elapsedSeconds(
  progress: Record<string, unknown> | null | undefined,
  engineStatus: string,
  nowMs: number,
): number;

export function describeTokenEstimate(result: TokenEstimate | null | undefined): {
  tone: 'info';
  text: string;
};
