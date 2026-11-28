export interface RowSelection { active: number | null; checked: number[]; context: string; }
export type RowSelectionState = number | null | RowSelection;
export function selectionContextChanged(value: RowSelectionState, context: string): boolean;
export function readRowSelection(value: RowSelectionState, count: number, context: string): RowSelection;
export function selectActiveRow(value: RowSelectionState, key: string | number | null, count: number, context: string): RowSelection;
export function selectCheckedRows(value: RowSelectionState, keys: readonly (string | number)[], count: number, context: string): RowSelection;
export function deleteCheckedRows<T>(rows: T[], value: RowSelectionState, context: string): T[];
export function clearCheckedTranslations<T extends { dst: string }>(rows: T[], value: RowSelectionState, context: string): { rows: T[]; changed: number };
export function glossarySelectionLabels(language: unknown): { deleteSelected: string; selectPage: string; selectRow: string; selectedCount: string; confirmCurrent: string };
