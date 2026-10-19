export const FONT_DEFAULT_LANGUAGE_VALUE: string;

export const FONT_DEFAULT_LANGUAGE_LABEL: { ZH: string; EN: string };

export const FONT_SCAN_NO_REFS_LABEL: { ZH: string; EN: string };

export const FONT_SCAN_STALE_LABEL: { ZH: string; EN: string };

export const FONT_BACKUP_SIDE_EFFECT_LABEL: { ZH: string; EN: string };

export const FONT_RESTORE_OK_LABEL: { ZH: string; EN: string };

export const FONT_RESTORE_PARTIAL_LABEL: { ZH: string; EN: string };

export const FONT_BROWSE_LABEL: { ZH: string; EN: string };

export const FONT_GAME_DIR_HINT: { ZH: string; EN: string };

export const FONT_GAME_DIR_EMPTY_LABEL: { ZH: string; EN: string };

export function fontGameDirReady(gamePath?: unknown): boolean;

export function fontToolsStatusPath(gamePath?: string): string;

export function fontToolsGamePathPayload(
  gamePath: unknown,
  boundGamePath?: unknown,
): { game_path?: string };

export function fontCopy(table: { ZH: string; EN: string }, lang?: string): string;

export function formatFontBackupSideEffect(path: unknown, lang?: string): string;

export function formatFontRestoreHint(
  result: { restored?: boolean; backup_path?: string; backup_name?: string; message?: string } | null | undefined,
  lang?: string,
): string;

export function resolveOriginalFonts(input: {
  replaceAll: boolean;
  selectedFont?: unknown;
  originalFont?: unknown;
  detected?: unknown;
}): string[] | null;

export function replaceFontsReady(input: {
  replaceAll: boolean;
  selectedFont?: unknown;
  originalFont?: unknown;
  detected?: unknown;
}): boolean;

export function formatFontScanSummary(
  template: unknown,
  counts?: { fontCount?: number; fontFileCount?: number; langCount?: number },
): string;

export function resolveFontInjectLanguage(
  selected: unknown,
  custom: unknown,
  defaultLanguage?: string,
): string;

export function fontDetectedPlaceholder(
  state: { fontsScanned?: boolean; scanStale?: boolean; fontRefCount?: number },
  labels: { noRefs: string; notScanned: string },
): string | undefined;
