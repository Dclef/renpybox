export function resolveGameFile(gameFile: unknown, defaultRoot?: unknown): string;

export function extractJsonStatusPath(input?: {
  gameFile?: unknown;
  language?: unknown;
  defaultRoot?: unknown;
}): string;

export function extractJsonStatusTone(input?: {
  active?: boolean;
  checking?: boolean;
  job?: { status?: string } | null;
  result?: { success?: boolean; partial?: boolean; written?: boolean } | null;
}): 'info' | 'success' | 'warning' | 'error';

export function exportJsonReady(input?: {
  gameFile?: unknown;
  outputPath?: unknown;
  defaultRoot?: unknown;
}): boolean;

export function importJsonReady(input?: {
  gameFile?: unknown;
  jsonPath?: unknown;
  defaultRoot?: unknown;
}): boolean;

export function formatPreviewSummary(
  template: unknown,
  counts?: { fileCount?: number; entryCount?: number },
): string;
