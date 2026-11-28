export function translateTargetRows<T extends { src: string; dst: string }>(rows: readonly T[], checked: readonly number[]): { rows: T[]; indices: number[] };
export function mapSubsetResults(indices: readonly number[] | null | undefined, results: readonly (readonly [number, string])[]): Array<[number, string]>;
export function applyTranslate<T extends { src: string; dst: string; candidate?: boolean; candidate_confirmed?: boolean }>(rows: readonly T[], results: readonly (readonly [number, string])[], indices?: readonly number[]): { rows: T[]; applied: number };
export function translateSnapshotsMatch(rows: readonly { src?: string; dst?: string }[], snapshots: readonly { src?: string; dst?: string }[] | undefined, indices?: readonly number[]): boolean;
