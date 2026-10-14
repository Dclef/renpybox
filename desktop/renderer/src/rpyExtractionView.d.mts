export const RPY_PAGE_SIZE: number;

export function modeNeedsProfile(mode: unknown): boolean;

export function isSelectionDirty(
  applied: { mode?: unknown; profileId?: unknown } | null | undefined,
  pending: { mode?: unknown; profileId?: unknown } | null | undefined,
): boolean;

export function isEditorDirty(editor: unknown, baselineJson: unknown): boolean;

export function isPageDirty(selectionDirty: unknown, editorDirty: unknown): boolean;

export function canApplySelection(
  mode: unknown,
  profileId: unknown,
  profile?: { rules?: Array<{ enabled?: unknown }> | null } | null,
): boolean;

export function advancedMustStayOpen(mode: unknown): boolean;

export function formatSelectionSummary(
  applied: { mode?: unknown; name?: unknown; profileId?: unknown } | null | undefined,
  pending: { mode?: unknown; name?: unknown; profileId?: unknown } | null | undefined,
  labels?: {
    current?: string;
    pending?: string;
    modes?: Record<string, string>;
    noProfile?: string;
  },
): string;

export function categoryScopeKey(category: unknown): 'source' | 'tl';

export function canSaveBind(scan: { has_scan?: unknown; completed?: unknown; error?: unknown } | null | undefined): boolean;

export function canContinuePreview(scan: { has_scan?: unknown; completed?: unknown; error?: unknown } | null | undefined): boolean;

export function clampScanPage(page: unknown, total: unknown, pageSize?: unknown): number;

export function formatPageLabel(page: unknown, total: unknown, pageSize?: unknown): string;

export function buildNewRule(template: unknown, index: number): {
  id: string;
  name: string;
  enabled: boolean;
  include_globs: string[];
  pattern: string;
  flags: string[];
  text_group: string | number;
  note: string;
  positive_samples: string[];
  negative_samples: string[];
};

export function cloneProfileDraft(
  profile: unknown,
  copySuffix?: string,
): {
  id: string;
  name: string;
  note: string;
  category: string;
  rules: unknown[];
} | null;
