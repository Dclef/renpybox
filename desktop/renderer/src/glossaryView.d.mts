export interface GlossaryScanOutcome {
  applyRows: boolean;
  applyIds: boolean;
  markDirty: boolean;
  warning: string;
  hasWarning: boolean;
  cancelled: boolean;
  partial: boolean;
  zeroSuccess: boolean;
}

export function glossaryScanOutcome(
  result?: Record<string, unknown> | null,
  status?: string | null,
  partialFallback?: string,
): GlossaryScanOutcome;

export interface ExtractionProgressView {
  phase: string;
  totalChunks: number;
  completedChunks: number;
  successfulChunks: number;
  failedChunks: number;
  pendingChunks: number;
  elapsedSeconds: number;
  activeChunks: Array<{ index: number; sources: string[]; elapsedSeconds: number }>;
  candidateCount: number;
  candidates: Array<{ src: string; type: string; evidence: string; source: string; line: number }>;
  candidatesTruncated: boolean;
}

export interface WarningDigest {
  total: number;
  items: string[];
  preview: string[];
  hasMore: boolean;
  collapsed: boolean;
}

export interface WarningHeadline {
  hasChunkSummary: boolean;
  successful: number;
  total: number;
  failed: number;
  pending: number;
  warningCount: number;
  coverageIncomplete: boolean;
}

export function jobProgressPercent(fraction?: unknown): number;
export function fillTemplate(text?: unknown, vars?: Record<string, string | number>): string;
export function formatSeconds(seconds?: unknown): number;
export function jobElapsedSeconds(createdAt?: unknown, updatedAt?: unknown): number | null;
export function normalizeExtractionProgress(raw?: unknown): ExtractionProgressView | null;
export function warningDigest(warnings?: unknown, warningText?: string | null): WarningDigest;
export function warningHeadline(view?: ExtractionProgressView | null, digest?: WarningDigest | null, result?: unknown): WarningHeadline;

export interface CheckpointFeedback {
  reusedChunks: number | null;
  requestedChunks: number | null;
  status: '' | 'new' | 'resumed' | 'complete' | 'corrupt' | 'incompatible' | 'unavailable' | 'superseded';
  resumeAvailable: boolean;
}
export function isCheckpointScanPath(path?: unknown): boolean;
export function hasCheckpointResumeCapability(response?: unknown): boolean;
export function checkpointScanRequestBody(path: string, body: Record<string, unknown>, capabilities?: unknown, mode?: 'resume' | 'restart'): Record<string, unknown>;
export function checkpointFeedback(result?: unknown): CheckpointFeedback;

