export function isIncrementalOutput(outputFolder: unknown): boolean;

export function canRetryPrepare(options?: {
  mode?: string;
  status?: string | null;
  active?: boolean;
  kind?: string | null;
}): boolean;

export function prepareFailureSummary(
  options?: {
    status?: string | null;
    error?: string | null;
    message?: string | null;
  },
  fallback?: string,
): string;

export interface OneKeyLexiconStep {
  status?: string;
  message?: string;
  count?: number;
  [key: string]: unknown;
}

export interface OneKeyLexiconReport {
  success?: boolean;
  message?: string;
  glossary?: OneKeyLexiconStep;
  preserve?: OneKeyLexiconStep;
  warnings?: string[];
  [key: string]: unknown;
}

export function onekeyLexiconOptions(
  values?: Record<string, unknown> | null,
  overrides?: { prepareGlossary?: boolean | null; prepareLexicon?: boolean | null },
): { prepare_glossary: boolean; prepare_lexicon: boolean };

export function onekeyLexiconReport(result: unknown): OneKeyLexiconReport | null;

export function onekeyLexiconReportOf(...results: unknown[]): OneKeyLexiconReport | null;

export function onekeyLexiconHasWarning(report: unknown): boolean;

export function onekeyLexiconSummaryLines(report: unknown): string[];

export function prepareStageSummaryLines(
  result: unknown,
  labels?: {
    detect?: string;
    unpack?: string;
    decompile?: string;
    extract?: string;
  },
  fill?: (text: string, vars: Record<string, string | number>) => string,
): string[];
