export type AgentToolTone = 'running' | 'done' | 'cancelled' | 'failed';

export function toolStatusInfo(tool: { status?: string; code?: string } | null | undefined): { label: string; tone: AgentToolTone };

export function languageFromTlPath(path: string | null | undefined): string;
