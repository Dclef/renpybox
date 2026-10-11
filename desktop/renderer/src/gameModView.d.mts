export const MOD_KEYS: string[];

export const MOD_COPY: Record<string, { ZH: string; EN: string }>;

export function modCopy(table: { ZH: string; EN: string }, lang?: string): string;

export function gameModStatusPath(gamePath?: string): string;

export function gamePathReady(gamePath?: string): boolean;

export function modStatusLabel(installed: boolean, lang?: string): string;

export function isSupportedModKey(key: unknown): boolean;

export function gameModOwnerIdentity(status: { owner_identity?: unknown } | null | undefined): string[] | undefined;

export function gameModStatusTone(input?: {
  active?: boolean;
  checking?: boolean;
  job?: { status?: string } | null;
  result?: { success?: boolean; partial?: boolean; written?: boolean } | null;
}): 'info' | 'warning' | 'error' | 'success';
