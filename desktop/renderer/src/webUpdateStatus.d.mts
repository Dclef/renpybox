import type { UpdateState } from './types';

export interface WebUpdateUi {
  status: string;
  statusText: string;
  progress: number;
  offerUpdate: boolean;
  showProgress: boolean;
  showCancel: boolean;
  showInstall: boolean;
  tag: string;
}

export function displayVersion(tag: string): string;
export function formatMegabytes(size: number): string;
export function resolveWebUpdateUi(update: Partial<UpdateState> | null | undefined, checking?: boolean): WebUpdateUi;
