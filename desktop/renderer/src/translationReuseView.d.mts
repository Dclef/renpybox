export function translationReuseStatusPath(opts?: { sourceDir?: string; targetDir?: string }): string;
export function formatReuseSummary(result: object | null | undefined, lang?: 'ZH' | 'EN'): string;
export function reuseOwnerProjectKey(
  status: { owner_project_key?: string } | null | undefined,
): string;
export function reusePathsConflict(sourceDir: string, targetDir: string): boolean;
