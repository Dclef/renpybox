export const CANCELLABLE_ARCHIVE_KINDS: readonly string[];

export function archiveJobCancellable(job: { kind?: string } | null | undefined): boolean;

export function isGameFolder(source: string): boolean;

export function derivePackOutput(source: string): string;

export function resolvePackOutput(source: string, output: string): string;
