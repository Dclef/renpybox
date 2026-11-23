export const ANDROID_COPY: Record<string, { ZH: string; EN: string }>;

export function androidCopy(table: { ZH: string; EN: string } | null | undefined, lang?: string): string;

export type AndroidFormState = {
  sdkPath: string;
  appName: string;
  packageName: string;
  version: string;
  archiveSourceDir: string;
  shellBackupEnable: boolean;
  shellRemoveDirs: string;
  dname: string;
  updateAlways: boolean;
  updateIcons: boolean;
};

export function defaultAndroidForm(config?: object | null): AndroidFormState;

export function shouldHydrateAndroidForm(flags?: {
  hydrated?: boolean;
  dirty?: boolean;
}): boolean;

export function mergeAndroidForm(
  current: AndroidFormState,
  config?: object | null,
  flags?: { hydrated?: boolean; dirty?: boolean },
): AndroidFormState;

export function androidFormIdentityKey(statusPath?: string, suiteIdentity?: string): string;

export const ANDROID_DRAFT_STORAGE_PREFIX: string;

export function androidDraftKey(projectPath?: string): string;

export function serializeAndroidDraft(
  form: AndroidFormState,
  extra?: { prefixDir?: string; prefixText?: string },
): string;

export function restoreAndroidDraft(raw: unknown): AndroidFormState;

export function parseAndroidDraftBundle(raw: unknown): {
  form: AndroidFormState;
  prefixDir: string;
  prefixText: string;
};

export function androidDraftHasContent(
  form: AndroidFormState,
  extra?: { prefixDir?: string; prefixText?: string },
): boolean;

export function androidStatusPath(projectPath?: string): string;

export function androidOwnerProjectKey(
  status: { owner_project_key?: string; project_key?: string } | null | undefined,
  fallback?: string,
): string;

export function sameAndroidPath(a: unknown, b: unknown): boolean;

export function androidConfigPayload(
  form: {
    sdkPath?: string;
    appName?: string;
    packageName?: string;
    version?: string;
    archiveSourceDir?: string;
    shellBackupEnable?: boolean;
    shellRemoveDirs?: string;
    dname?: string;
    updateAlways?: boolean;
    updateIcons?: boolean;
  },
  projectPath?: string,
): Record<string, unknown>;

export function androidAppFieldsReady(form: {
  appName?: string;
  packageName?: string;
  version?: string;
} | null | undefined): boolean;

export function androidSdkReady(form: { sdkPath?: string } | null | undefined): boolean;

export function androidJobCancellable(job: { result?: { cancellable?: boolean } | null } | null | undefined): boolean;

export function appendArchiveSource(current: unknown, folder: unknown): string;

export function formatAndroidOutputs(
  outputs?: Array<string | { name?: string }>,
  limit?: number,
): string[];

export function prefixRequestBody(
  directory: unknown,
  prefix: unknown,
  action: unknown,
  apply: unknown,
): {
  directory: string;
  prefix: string;
  action: unknown;
  apply: boolean;
};

export function formatPrefixPlan(
  payload: {
    total?: number;
    files?: number;
    dirs?: number;
    skipped?: number;
  } | null | undefined,
  lang?: string,
): string;

export function formatPrefixResult(
  payload: {
    renamed?: number;
    files?: number;
    dirs?: number;
    skipped?: number;
    new_root?: string | null;
  } | null | undefined,
  lang?: string,
): string;
