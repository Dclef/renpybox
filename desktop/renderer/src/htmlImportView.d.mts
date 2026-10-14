export const HTML_COPY: Record<string, { ZH: string; EN: string }>;

export function htmlCopy(table: { ZH: string; EN: string }, lang?: string): string;

export function defaultPendingTxt(tlDir?: string): string;

export function htmlImportStatusPath(input?: { tlDir?: string; manifestPath?: string }): string;

export function extractReady(tlDir?: string): boolean;

export function applyReady(input?: { manifestPath?: string; translatedTxt?: string }): boolean;

export function siblingOutput(inputPath?: string, suffix?: string): string;

export function excelColumnValue(uiValue: unknown): '原文' | '译文';

export function htmlImportOwnerIdentity(status: { owner_identity?: unknown } | null | undefined): string[] | undefined;

export function htmlImportStatusTone(input?: {
  active?: boolean;
  checking?: boolean;
  job?: { status?: string } | null;
  result?: { success?: boolean; partial?: boolean; written?: boolean } | null;
}): 'info' | 'warning' | 'error' | 'success';
