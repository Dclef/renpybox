export function errorRepairStatusPath(folder: string): string;
export function formatScanSummary(
  result: { total_issues?: number; affected_files?: number; report?: Record<string, unknown[]> } | null | undefined,
  lang?: 'ZH' | 'EN',
): string;
export function formatFixSummary(
  result: { fixed_files?: number; fixed_items?: number; failed_files?: number } | null | undefined,
  lang?: 'ZH' | 'EN',
): string;
export const ERROR_REPAIR_DEFAULTS: {
  fixIndent: boolean;
  fixIndentLevel: boolean;
  fixQuotes: boolean;
  fixDialogueQuotes: boolean;
  fixEmptyBlocks: boolean;
};
export function errorRepairOwnerProjectKey(
  status: { owner_project_key?: string } | null | undefined,
): string;
