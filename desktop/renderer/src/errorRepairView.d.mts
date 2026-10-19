/** errorRepairView.mjs 的类型声明（tsc 只读这里，实现是纯 JS）。 */

export interface RepairIssueLike {
  file?: string;
  line?: number;
  type?: string;
  message?: string;
  fixable?: boolean;
}

export interface RepairEnvironmentIssueLike {
  kind?: string;
  type?: string;
  path?: string;
  language?: string;
  message?: string;
  issue_count?: number;
  actions?: string[];
}

export interface RepairEnvironmentFixLike {
  path?: string;
  action?: string;
  ok?: boolean;
  message?: string;
  backup?: string;
}

export interface RepairScanLike {
  total_issues?: number;
  affected_files?: number;
  report?: Record<string, unknown[]>;
  fixable_issues?: number;
  manual_issues?: number;
  environment_issues?: RepairEnvironmentIssueLike[];
  manual_sample?: RepairIssueLike[];
}

export interface RepairFixLike {
  success?: boolean;
  partial?: boolean;
  fixed_files?: number;
  fixed_items?: number;
  failed_files?: number;
  fixed_by_type?: Record<string, number>;
  remaining_issues?: number | null;
  remaining_by_type?: Record<string, number>;
  environment_fixes?: RepairEnvironmentFixLike[];
  manual_sample?: RepairIssueLike[];
  rescan_skipped?: boolean;
}

export type RepairLang = 'ZH' | 'EN';

export function errorRepairStatusPath(folder: string): string;
export const REPAIR_TYPE_LABELS: Record<string, { ZH: string; EN: string } | undefined>;
export function repairTypeLabel(type: string, lang?: RepairLang): string;
export function formatScanSummary(
  result: RepairScanLike | null | undefined,
  lang?: RepairLang,
): string;
export function formatRepairSummary(
  result: RepairFixLike | null | undefined,
  lang?: RepairLang,
): string;
export function formatTypeBreakdown(
  counts: Record<string, number> | null | undefined,
  lang?: RepairLang,
): string;
export function scanIsActionable(result: (RepairScanLike & { fixable_issues?: number }) | null | undefined): boolean;
export function fixTone(result: RepairFixLike | null | undefined): 'success' | 'warning' | 'error';
export function formatFixSummary(
  result: { fixed_files?: number; fixed_items?: number; failed_files?: number } | null | undefined,
  lang?: RepairLang,
): string;
export const ERROR_REPAIR_DEFAULTS: {
  fixIndent: boolean;
  fixTrailingSpaces: boolean;
  fixEmptyBlocks: boolean;
  fixDuplicates: boolean;
  fixDialogueQuotes: boolean;
  fixIndentLevel: boolean;
  fixQuotes: boolean;
};
export function buildEnvironmentFixBody(input: {
  folder: string;
  action: 'merge' | 'move';
  path: string;
  ownerKey: string;
}): {
  folder: string;
  fix_indent: false;
  fix_trailing_spaces: false;
  fix_empty_blocks: false;
  fix_duplicates: false;
  fix_dialogue_quotes: false;
  fix_indent_level: false;
  fix_quotes: false;
  fix_environment: true;
  environment_action: 'merge' | 'move';
  environment_path: string;
  confirm: true;
  owner_project_key: string;
};
export function errorRepairOwnerProjectKey(
  status: { owner_project_key?: string } | null | undefined,
): string;
