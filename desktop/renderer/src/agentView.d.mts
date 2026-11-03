export type AgentToolTone = 'running' | 'done' | 'cancelled' | 'failed';

export function toolStatusInfo(tool: { status?: string; code?: string } | null | undefined): { label: string; tone: AgentToolTone };

export function languageFromTlPath(path: string | null | undefined): string;

export const AGENT_API_FORMATS: readonly string[];
export const MACHINE_API_FORMATS: readonly string[];

export function isMachineApiFormat(apiFormat: string | null | undefined): boolean;
export function isAgentPlatform(platform: { api_format?: string } | null | undefined): boolean;
export function selectableAgentPlatforms(platforms: unknown): { id: number; name?: string; model?: string; api_format?: string }[];

export const PIPELINE_STAGES: readonly ['detect', 'unpack', 'decompile', 'extract', 'translate', 'apply', 'fallback', 'done'];

export function stageKey(stage: string | null | undefined): string;

export function formatTokenCount(n: number | null | undefined): string;

export function budgetParts(budget: {
  context_window?: number;
  usable_tokens?: number;
  max_output_tokens?: number;
  max_messages?: number;
  max_iterations?: number;
} | null | undefined): { context: string; usable: string; output: string; messages: string; iterations: string };

export interface AgentMetricsParts {
  rounds: number;
  steps: number;
  requests: number;
  tokensPerSecond: number;
  inputTokens: string;
  outputTokens: string;
  totalTokens: string;
  cacheHitPercent: number | null;
  contextPercent: number;
  hasData: boolean;
}

export function metricsParts(metrics: {
  iterations?: number;
  steps?: number;
  requests?: number;
  tokens_per_second?: number;
  input_tokens?: number;
  output_tokens?: number;
  total_tokens?: number;
  cache_hit_rate?: number | null;
  context_percent?: number;
} | null | undefined): AgentMetricsParts;
