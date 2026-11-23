export interface ParsedMirrorList {
  values: string[];
  errors: string[];
}

export function parseMirrorList(text: unknown): ParsedMirrorList;
export function formatMirrorList(list: unknown): string;

// 内置默认镜像（与 desktop/main/updater-mirror.js 保持一致，测试防漂移）与空态展示助手
export const BUILTIN_MIRRORS: readonly string[];
export const MIRROR_PRESETS: readonly string[];
export function builtinMirrorText(): string;
export function isUsingBuiltinMirrors(list: unknown): boolean;
export function mirrorValuesFromSetting(value: unknown): string[];
export function reconcileMirrorSelection(ordered: string[], selected: string[]): string[];
export function addCustomMirror(
  values: string[],
  raw: unknown,
): ParsedMirrorList;

export interface MirrorRankResult {
  prefix: string;
  latencyMs: number;
  bytesPerSec: number;
  ok: boolean;
  fastest: boolean;
}

export function rankMirrorResults(results: unknown): MirrorRankResult[];
export function speedOrderedMirrors(results: unknown): string[];
export function mirrorProbeCandidates(ordered: unknown): string[];
