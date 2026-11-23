/**
 * 安卓打包页纯函数与就地双语文案（避免并行改 i18n）。
 * 对齐 Qt5 AndroidBuildPage 默认值与请求语义。
 */

export const ANDROID_COPY = {
  title: { ZH: '安卓打包', EN: 'Android Build' },
  paths: { ZH: '路径', EN: 'Paths' },
  pathsNote: {
    ZH: '壳项目 / 修改版 SDK 需要从群里获取，群号：821152470；请选择本机 Ren\'Py SDK 与项目根目录。',
    EN: 'Get the shell project / modified SDK from our group (Group No. 821152470). Pick a local Ren\'Py SDK and project root.',
  },
  sdk: { ZH: "Ren'Py SDK", EN: "Ren'Py SDK" },
  project: { ZH: '项目目录', EN: 'Project folder' },
  browse: { ZH: '浏览', EN: 'Browse' },
  add: { ZH: '添加', EN: 'Add' },
  detect: { ZH: '检测', EN: 'Detect' },
  config: { ZH: 'Android 配置 (android.json)', EN: 'Android configuration (android.json)' },
  appName: { ZH: '应用名', EN: 'App name' },
  packageName: { ZH: '包名', EN: 'Package name' },
  version: { ZH: '版本', EN: 'Version' },
  iconsHint: {
    ZH: '图标：将 android-icon_foreground.png / android-icon_background.png 放在项目根。',
    EN: 'Icons: place android-icon_foreground.png / android-icon_background.png in the project root.',
  },
  writeJson: { ZH: '写入 android.json', EN: 'Write android.json' },
  env: { ZH: '环境与签名', EN: 'Environment & signing' },
  checkEnv: { ZH: '检查环境', EN: 'Check environment' },
  installSdk: { ZH: '安装 SDK', EN: 'Install SDK' },
  generateKeys: { ZH: '生成签名', EN: 'Generate signing key' },
  build: { ZH: '构建', EN: 'Build' },
  buildHint: {
    ZH: '仅生成 APK；构建成功后打开 rapt/bin。列表可能含历史 APK。',
    EN: 'APK only. Opens rapt/bin after a successful build. The list may include older APKs.',
  },
  startBuild: { ZH: '开始构建', EN: 'Start build' },
  openBin: { ZH: '打开 rapt/bin', EN: 'Open rapt/bin' },
  shell: { ZH: '壳包', EN: 'Shell package' },
  shellHint: {
    ZH: '将所选文件夹打成项目根 archive.rpa，并可清理资源目录。',
    EN: 'Pack selected folders into archive.rpa at the project root, then optionally clean resources.',
  },
  archiveFolders: { ZH: '打包文件夹', EN: 'Package folders' },
  archivePlaceholder: {
    ZH: '多个文件夹用分号分隔；留空=整个 game',
    EN: 'Separate folders with semicolons; empty = entire game',
  },
  backupZip: {
    ZH: '备份打包文件夹为项目根 ZIP',
    EN: 'Back up package folders as a ZIP in the project root',
  },
  cleanupFolders: { ZH: '清理文件夹', EN: 'Cleanup folders' },
  cleanupPlaceholder: {
    ZH: '逗号/分号分隔；留空=不删除',
    EN: 'Comma/semicolon separated; empty = delete nothing',
  },
  makeShell: { ZH: '生成 archive.rpa 并清理资源', EN: 'Build archive.rpa and clean resources' },
  confirmShell: {
    ZH: '将在项目根生成 archive.rpa 并清理配置的资源目录。是否继续？',
    EN: 'This builds archive.rpa at the project root and cleans configured resource folders. Continue?',
  },
  confirmBuild: {
    ZH: '将写入 android.json、创建分发目录并构建 APK。是否继续？',
    EN: 'This writes android.json, creates the distribute folder, and builds an APK. Continue?',
  },
  needsProject: { ZH: '需要先加载游戏项目', EN: 'Load a game project first' },
  idle: { ZH: '就绪', EN: 'Ready' },
  keystoreMissing: { ZH: '未找到签名文件，请先生成签名', EN: 'No signing key found; generate one first' },
  fillRequired: { ZH: '请填写应用名、包名和版本', EN: 'Enter app name, package name, and version' },
  logs: { ZH: '日志', EN: 'Logs' },
  outputs: { ZH: '输出 APK（含历史）', EN: 'Output APKs (includes history)' },
  newOutputs: { ZH: '本次新产物', EN: 'New outputs this run' },
  shellResult: { ZH: '壳包结果', EN: 'Shell result' },
  xPrefix: { ZH: 'X- 前缀', EN: 'X- prefix' },
  xPrefixHint: {
    ZH: '部分安卓版把游戏目录与文件名统一加了 X- 前缀（例如 assets/x-game/x-script.rpyc）。建议直接选 assets/x-game 目录本身：先去除前缀做翻译，放回 APK 前再对改名后的 game 目录恢复前缀。',
    EN: 'Some Android builds prefix every file and folder in the game directory with X- (for example assets/x-game/x-script.rpyc). Point this at the assets/x-game folder itself: strip the prefix before translating, then restore it on the renamed game folder before putting the files back into the APK.',
  },
  prefixDir: { ZH: '目录', EN: 'Folder' },
  prefixDirPlaceholder: { ZH: '例如 ...\\assets\\x-game', EN: 'e.g. ...\\assets\\x-game' },
  prefixLabel: { ZH: '前缀', EN: 'Prefix' },
  stripPrefix: { ZH: '去除前缀', EN: 'Strip prefix' },
  restorePrefix: { ZH: '恢复前缀', EN: 'Restore prefix' },
  prefixNothing: {
    ZH: '未发现需要处理的条目（没有需要去除或恢复前缀的文件与目录）。',
    EN: 'Nothing to change: no file or folder needs the X- prefix stripped or restored.',
  },
  prefixNeedDir: { ZH: '请先选择要处理的目录。', EN: 'Choose a folder first.' },
  confirmStrip: { ZH: '去除 X- 前缀', EN: 'Strip the X- prefix' },
  confirmRestore: { ZH: '恢复 X- 前缀', EN: 'Restore the X- prefix' },
  prefixSamples: { ZH: '将要处理的条目（示例）', EN: 'Entries to change (sample)' },
};

export function androidCopy(table, lang = 'ZH') {
  if (!table || typeof table !== 'object') return '';
  return lang === 'EN' ? (table.EN || table.ZH || '') : (table.ZH || table.EN || '');
}

/** 默认配置（对齐 Config / Qt _load_config） */
export function defaultAndroidForm(config = {}) {
  const cfg = config && typeof config === 'object' ? config : {};
  return {
    sdkPath: String(cfg.sdk_path ?? ''),
    appName: String(cfg.app_name ?? ''),
    packageName: String(cfg.package_name ?? ''),
    version: String(cfg.version ?? ''),
    archiveSourceDir: String(cfg.archive_source_dir ?? ''),
    shellBackupEnable: cfg.shell_backup_enable !== false,
    shellRemoveDirs: String(cfg.shell_remove_dirs ?? 'images,image,audio,video,videos,movies,script'),
    dname: String(cfg.dname ?? ''),
    updateAlways: cfg.update_always !== false,
    updateIcons: cfg.update_icons !== false,
  };
}

/**
 * 是否用后端 config 水合本地 form。
 * 同一身份只水合一次；用户改过表单后不再被轮询覆盖。
 * 通用纯判定，useHydratedForm 与页面均复用此函数。
 */
export function shouldHydrateAndroidForm({ hydrated = false, dirty = false } = {}) {
  return !hydrated && !dirty;
}

/**
 * 合并后端 config 到本地 form：仅在未水合且未 dirty 时替换为 defaultAndroidForm(config)。
 * 身份键变化时调用方应先重置 hydrated/dirty 再传入。
 */
export function mergeAndroidForm(current, config, { hydrated = false, dirty = false } = {}) {
  if (!shouldHydrateAndroidForm({ hydrated, dirty })) {
    return current;
  }
  return defaultAndroidForm(config);
}

/** 表单水合身份：statusPath（含手动 project_path）+ suite.identity */
export function androidFormIdentityKey(statusPath = '', suiteIdentity = '') {
  return `${String(statusPath || '')}\0${String(suiteIdentity || '')}`;
}

/** sessionStorage 键前缀：草稿按全局绑定项目路径隔离，不含手动 B。 */
export const ANDROID_DRAFT_STORAGE_PREFIX = 'renpybox.android.draft.';

const ANDROID_DRAFT_NO_PROJECT = '__no_project__';

/** 生成安卓打包页草稿的 sessionStorage 键。 */
export function androidDraftKey(projectPath = '') {
  const trimmed = String(projectPath || '').trim();
  const slug = trimmed
    ? trimmed.replace(/\\/g, '/').toLowerCase()
    : ANDROID_DRAFT_NO_PROJECT;
  return `${ANDROID_DRAFT_STORAGE_PREFIX}${encodeURIComponent(slug)}`;
}

function _coerceAndroidFormState(raw) {
  if (!raw || typeof raw !== 'object') return defaultAndroidForm();
  const src = /** @type {Record<string, unknown>} */ (raw);
  return {
    sdkPath: typeof src.sdkPath === 'string' ? src.sdkPath : String(src.sdkPath ?? ''),
    appName: typeof src.appName === 'string' ? src.appName : String(src.appName ?? ''),
    packageName: typeof src.packageName === 'string' ? src.packageName : String(src.packageName ?? ''),
    version: typeof src.version === 'string' ? src.version : String(src.version ?? ''),
    archiveSourceDir: typeof src.archiveSourceDir === 'string' ? src.archiveSourceDir : String(src.archiveSourceDir ?? ''),
    shellBackupEnable: src.shellBackupEnable !== false,
    shellRemoveDirs: typeof src.shellRemoveDirs === 'string'
      ? src.shellRemoveDirs
      : String(src.shellRemoveDirs ?? defaultAndroidForm().shellRemoveDirs),
    dname: typeof src.dname === 'string' ? src.dname : String(src.dname ?? ''),
    updateAlways: src.updateAlways !== false,
    updateIcons: src.updateIcons !== false,
  };
}

/** 序列化表单草稿（含可选 X- 前缀区字段）为 JSON 字符串。 */
export function serializeAndroidDraft(form, extra = {}) {
  const payload = {
    v: 1,
    form: _coerceAndroidFormState(form),
    prefixDir: typeof extra.prefixDir === 'string' ? extra.prefixDir : String(extra.prefixDir ?? ''),
    prefixText: typeof extra.prefixText === 'string' ? extra.prefixText : String(extra.prefixText ?? 'x-'),
  };
  return JSON.stringify(payload);
}

/** 解析草稿 JSON，仅返回表单；脏数据一律回落 defaultAndroidForm()。 */
export function restoreAndroidDraft(raw) {
  return parseAndroidDraftBundle(raw).form;
}

/** 完整解析草稿 bundle（页面用于恢复 prefix 区）。 */
export function parseAndroidDraftBundle(raw) {
  const fallback = {
    form: defaultAndroidForm(),
    prefixDir: '',
    prefixText: 'x-',
  };
  const text = String(raw ?? '').trim();
  if (!text) return fallback;
  try {
    const parsed = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object') return fallback;
    const src = /** @type {Record<string, unknown>} */ (parsed);
    const form = _coerceAndroidFormState(src.form);
    const prefixDir = typeof src.prefixDir === 'string' ? src.prefixDir : String(src.prefixDir ?? '');
    const prefixText = typeof src.prefixText === 'string' ? src.prefixText : String(src.prefixText ?? 'x-');
    return { form, prefixDir, prefixText };
  } catch {
    return fallback;
  }
}

/** 草稿是否含用户实质输入（用于恢复后标记 dirty / 提示）。 */
export function androidDraftHasContent(form, extra = {}) {
  const base = defaultAndroidForm();
  const keys = Object.keys(base);
  const formDirty = keys.some((key) => form?.[key] !== base[key]);
  const prefixDir = String(extra.prefixDir ?? '').trim();
  const prefixText = String(extra.prefixText ?? 'x-').trim();
  const prefixDirty = Boolean(prefixDir) || (prefixText && prefixText !== 'x-');
  return formDirty || prefixDirty;
}

/** status URL：手动项目 B 带 project_path，驱动 late 响应上下文失效。 */
export function androidStatusPath(projectPath = '') {
  const trimmed = String(projectPath || '').trim();
  if (!trimmed) return '/api/android-build';
  return `/api/android-build?project_path=${encodeURIComponent(trimmed)}`;
}

/** 提交用的 owner 键：优先绑定 owner，兼容手动 target 连续操作。 */
export function androidOwnerProjectKey(status, fallback = '') {
  const owner = String(status?.owner_project_key || '').trim();
  if (owner) return owner;
  return String(fallback || status?.project_key || '').trim();
}

export function sameAndroidPath(a, b) {
  return String(a || '').replace(/\\/g, '/').toLowerCase()
    === String(b || '').replace(/\\/g, '/').toLowerCase();
}

export function androidConfigPayload(form, projectPath = '') {
  return {
    project_path: String(projectPath || '').trim(),
    sdk_path: String(form.sdkPath || '').trim(),
    app_name: String(form.appName || '').trim(),
    package_name: String(form.packageName || '').trim(),
    version: String(form.version || '').trim(),
    archive_source_dir: String(form.archiveSourceDir || '').trim(),
    shell_backup_enable: Boolean(form.shellBackupEnable),
    shell_remove_dirs: String(form.shellRemoveDirs || '').trim(),
    dname: String(form.dname || '').trim(),
    update_always: form.updateAlways !== false,
    update_icons: form.updateIcons !== false,
  };
}

export function androidAppFieldsReady(form) {
  return Boolean(
    String(form?.appName || '').trim()
    && String(form?.packageName || '').trim()
    && String(form?.version || '').trim(),
  );
}

export function androidSdkReady(form) {
  return Boolean(String(form?.sdkPath || '').trim());
}

/** SDK 外部任务不可真取消 */
export function androidJobCancellable(job) {
  if (!job) return false;
  const result = job.result && typeof job.result === 'object' ? job.result : null;
  if (result && result.cancellable === false) return false;
  return false;
}

export function appendArchiveSource(current, folder) {
  const next = String(folder || '').trim();
  if (!next) return String(current || '');
  const existing = String(current || '').trim();
  if (!existing) return next;
  const parts = existing.split(/[;,\n\r]+/).map((item) => item.trim()).filter(Boolean);
  const key = (value) => value.toLowerCase();
  if (parts.some((item) => key(item) === key(next))) return existing;
  return `${existing};${next}`;
}

export function formatAndroidOutputs(outputs = [], limit = 3) {
  const list = Array.isArray(outputs) ? outputs : [];
  return list.slice(0, limit).map((item) => (typeof item === 'string' ? item : item?.name)).filter(Boolean);
}

/** 前缀处理请求体：空前缀回落 x-。 */
export function prefixRequestBody(directory, prefix, action, apply) {
  const trimmedPrefix = String(prefix ?? '').trim();
  return {
    directory: String(directory ?? '').trim(),
    prefix: trimmedPrefix || 'x-',
    action,
    apply: Boolean(apply),
  };
}

function _prefixRootName(newRoot) {
  const text = String(newRoot || '').replace(/[\\/]+$/, '');
  if (!text) return '';
  const parts = text.split(/[/\\]/);
  return parts[parts.length - 1] || '';
}

/** 干跑摘要（确认框正文）。 */
export function formatPrefixPlan(payload, lang = 'ZH') {
  const total = Number(payload?.total || 0);
  const files = Number(payload?.files || 0);
  const dirs = Number(payload?.dirs || 0);
  const skipped = Number(payload?.skipped || 0);
  if (lang === 'EN') {
    let message = `Rename ${total} entries (${files} files / ${dirs} folders)`;
    if (skipped > 0) message += `, skip ${skipped}`;
    return message;
  }
  let message = `将重命名 ${total} 个条目（文件 ${files} / 目录 ${dirs}）`;
  if (skipped > 0) message += `，跳过 ${skipped} 个`;
  return message;
}

/** 落盘结果摘要。 */
export function formatPrefixResult(payload, lang = 'ZH') {
  const renamed = Number(payload?.renamed || 0);
  const files = Number(payload?.files || 0);
  const dirs = Number(payload?.dirs || 0);
  const skipped = Number(payload?.skipped || 0);
  const rootName = _prefixRootName(payload?.new_root);
  if (lang === 'EN') {
    let message = `Renamed ${renamed} entries (${files} files / ${dirs} folders)`;
    if (skipped > 0) message += `, skip ${skipped}`;
    if (rootName) message += `, root folder renamed to ${rootName}`;
    return message;
  }
  let message = `已重命名 ${renamed} 个条目（文件 ${files} / 目录 ${dirs}）`;
  if (skipped > 0) message += `，跳过 ${skipped} 个`;
  if (rootName) message += `，根目录已改为 ${rootName}`;
  return message;
}
