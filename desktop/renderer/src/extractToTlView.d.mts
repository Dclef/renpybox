export function isEffectiveTlRpy(fileName: unknown): boolean;

export function shouldUseIncremental(fileNames: unknown): boolean;

export function resolveExtractSwitches(input?: {
  useOfficial?: unknown;
  useCustom?: unknown;
  ruleMode?: unknown;
  hasExe?: unknown;
}): { useOfficial: boolean; useCustom: boolean; ruleMode: string };

export function normalizeSupplementMode(value: unknown): 'precise' | 'aggressive';

export function preferredSuspiciousOpenPath(status: {
  suspicious_manifests?: Array<{ path?: string }>;
  open_path?: string;
  tl_dir?: string;
} | null | undefined): string;

export function extractToTlStatusPath(input?: {
  gameDir?: unknown;
  language?: unknown;
}): string;

export function extractToTlStatusTone(input?: {
  active?: boolean;
  checking?: boolean;
  job?: { status?: string } | null;
  result?: { success?: boolean; partial?: boolean; written?: boolean } | null;
}): 'info' | 'success' | 'warning' | 'error';
