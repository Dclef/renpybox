export const TOOLBOX_TRANSLATE_MODES: readonly string[];

export interface ToolboxLangOption {
  value: string;
  traditional: boolean;
  label: string;
}

export const TOOLBOX_LANG_OPTIONS: readonly ToolboxLangOption[];

export function normalizePath(value: unknown): string;

export function isPathWithin(child: unknown, parent: unknown): boolean;

export function pathsOverlap(left: unknown, right: unknown): boolean;

export function defaultSourceOutputDir(inputFolder: unknown): string;

export function defaultSourceFileOutputDir(inputFile: unknown): string;

export function validateSourceLayout(
  inputFolder: unknown,
  outputFolder: unknown,
): { ok: boolean; message: string };

export function translationModeSummary(mode: unknown): string;

export function translationProgressView(progress: unknown): { percent: number; label: string };

export function sourceResumeView(info: unknown): {
  canContinue: boolean;
  percent: number;
  line: number;
  total: number;
  hint: string;
};

export function toolboxStartGate(options?: {
  mode?: string;
  hasProject?: boolean;
  linkOpen?: boolean;
  engineBusy?: boolean;
  tlDir?: string;
  gamePath?: string;
  tlParent?: string;
  tlName?: string;
  inputFolder?: string;
  outputFolder?: string;
}): { canStart: boolean; hint: string };

export function encodeLangChoice(code: unknown, traditional?: unknown): string;

export function decodeLangChoice(value: unknown): { code: string; traditional: boolean };

export function toolboxOwnerKey(projectPath: unknown, language?: unknown): string;

export function toolboxProjectRootFromGamePath(rawPath: unknown): string;

export function toolboxTargetKeyFromGamePath(rawPath: unknown, language?: unknown): string;

export function toolboxTlLanguageName(tlFolder: unknown, fallback?: unknown): string;
