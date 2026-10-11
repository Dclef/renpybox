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
