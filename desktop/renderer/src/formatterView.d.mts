export function formatterStatusPath(folder: string): string;
export const FORMATTER_DEFAULTS: {
  preserveComments: boolean;
  fixIndent: boolean;
  removeTrailing: boolean;
};
export function formatFormatterSummary(
  result: { success_count?: number; failed_files?: string[] } | null | undefined,
  lang?: 'ZH' | 'EN',
): string;
export function formatterOwnerProjectKey(
  status: { owner_project_key?: string } | null | undefined,
): string;
