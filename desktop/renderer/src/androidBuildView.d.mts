export const ANDROID_COPY: Record<string, { ZH: string; EN: string }>;

export function androidCopy(table: { ZH: string; EN: string } | null | undefined, lang?: string): string;

export function defaultAndroidForm(config?: object | null): {
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
