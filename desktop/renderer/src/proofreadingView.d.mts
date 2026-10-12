export const GLOSSARY_WARNING: 'GLOSSARY';
export const NO_WARNING: 'NO_WARNING';
export const TERM_ANY: '__ANY__';

export interface GlossaryTerm {
  src?: string;
  dst?: string;
}

export interface ProofreadingViewRow {
  id: number;
  version: string;
  src: string;
  dst: string;
  status?: string;
  file_path?: string;
  warnings?: string[];
  glossary_terms?: GlossaryTerm[];
}

export interface KeywordOptions {
  regex?: boolean;
  caseSensitive?: boolean;
}

export interface CompiledPattern {
  ok: boolean;
  pattern: RegExp | null;
  error?: string;
}

export interface GlossaryTermOption {
  key: string;
  src: string;
  dst: string;
  label: string;
}

export interface ReplaceImpactRow {
  id: number;
  version: string;
  before: string;
  after: string;
}

export interface ReplaceImpact {
  rows: ReplaceImpactRow[];
  matchCount: number;
  invalidRegex: boolean;
  error?: string;
}

export interface FilterSelection {
  statuses?: string[] | Set<string> | null;
  files?: string[] | Set<string> | null;
  warnings?: string[] | Set<string> | null;
  terms?: string[] | Set<string> | null;
}

export interface PageSlice<T> {
  items: T[];
  page: number;
  pages: number;
}

export function compilePattern(
  source: string | null | undefined,
  options?: { regex?: boolean; caseSensitive?: boolean },
): CompiledPattern;

export function matchesKeyword(
  text: string | null | undefined,
  keyword: string | null | undefined,
  options?: KeywordOptions,
): boolean;

export function matchRowIndices(
  rows: ProofreadingViewRow[] | null | undefined,
  keyword: string | null | undefined,
  options?: KeywordOptions,
): number[];

export function stepMatch(current: number, total: number, delta: number): number;

export function makeReplacer(
  find: string | null | undefined,
  replacement: string | null | undefined,
  options?: KeywordOptions,
): (text: string | null | undefined) => string;

export function countMatches(
  text: string | null | undefined,
  find: string | null | undefined,
  options?: KeywordOptions,
): number;

export function replaceImpact<T extends ProofreadingViewRow>(
  rows: T[] | null | undefined,
  find: string | null | undefined,
  replacement: string | null | undefined,
  options?: KeywordOptions,
): ReplaceImpact;

export function glossaryTermsOf(row: ProofreadingViewRow | null | undefined): GlossaryTerm[];

export function collectGlossaryTerms(rows: ProofreadingViewRow[] | null | undefined): GlossaryTermOption[];

export function collectWarnings(rows: ProofreadingViewRow[] | null | undefined): string[];

export function filterRows<T extends ProofreadingViewRow>(
  rows: T[] | null | undefined,
  filters?: FilterSelection,
): T[];

export function pageSlice<T>(rows: T[] | null | undefined, page: number, limit: number): PageSlice<T>;

export function buildExportRecords(rows: ProofreadingViewRow[] | null | undefined): Array<{
  file_path: string;
  status: string;
  warnings: string[];
  src: string;
  dst: string;
}>;

export function exportFilename(now?: Date): string;

export function exportText(rows: ProofreadingViewRow[] | null | undefined): string;
