import type { DesktopUpdateState } from './preload';

export function latestChangelogSection(markdown: string): string;
export function shouldOfferUpdate(
  update: Partial<DesktopUpdateState> | null | undefined,
  dismissed?: string,
): boolean;
export function shouldAnnounceUpdate(previous: string | null | undefined, current: string | null | undefined): boolean;
