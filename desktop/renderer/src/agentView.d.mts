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

export function budgetParts(budget: { context_window?: number; max_iterations?: number } | null | undefined): { context: string; iterations: string };
