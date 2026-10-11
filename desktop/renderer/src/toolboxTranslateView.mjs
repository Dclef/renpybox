// 工具箱「直接翻译 RPY / 源码翻译 / 补全」纯逻辑：不依赖 React，便于 node:test 覆盖。

/** 与后端 TRANSLATION_TOOLBOX_MODES 对齐的白名单（hook 走独立路由）。 */
export const TOOLBOX_TRANSLATE_MODES = Object.freeze(['direct', 'source', 'supplement']);

/** 工具箱语言选项：简/繁中文共用 ZH，繁体靠 traditional 标志。 */
export const TOOLBOX_LANG_OPTIONS = Object.freeze([
  { value: 'ZH', traditional: false, label: '简体中文' },
  { value: 'ZH', traditional: true, label: '繁体中文' },
  { value: 'EN', traditional: false, label: '英语' },
  { value: 'JA', traditional: false, label: '日语' },
  { value: 'KO', traditional: false, label: '韩语' },
]);

/**
 * 规范化路径：去首尾空白、统一分隔符、去掉尾部斜杠（根路径除外）。
 * 不做文件系统访问；后端仍会再 resolve 一次。
 */
export function normalizePath(value) {
  let text = String(value ?? '').trim().replace(/\//g, '\\');
  if (!text) return '';
  // 保留盘符根如 E:\，其余去掉尾部分隔符便于比较。
  if (/^[a-zA-Z]:\\$/.test(text) || text === '\\') return text;
  return text.replace(/[\\/]+$/, '');
}

function pathKey(value) {
  return normalizePath(value).toLowerCase();
}

/** 判断 child 是否等于 parent，或位于 parent 之下。 */
export function isPathWithin(child, parent) {
  const c = pathKey(child);
  const p = pathKey(parent);
  if (!c || !p) return false;
  if (c === p) return true;
  const prefix = p.endsWith('\\') ? p : `${p}\\`;
  return c.startsWith(prefix);
}

/** 输入输出相同或互相包含。 */
export function pathsOverlap(left, right) {
  const a = normalizePath(left);
  const b = normalizePath(right);
  if (!a || !b) return false;
  return isPathWithin(a, b) || isPathWithin(b, a);
}

/**
 * 目录模式默认输出：input.parent / `${input.name}_source_out`
 *（对齐 Qt SourceTranslatePage）。
 */
export function defaultSourceOutputDir(inputFolder) {
  const input = normalizePath(inputFolder);
  if (!input) return '';
  const sep = input.lastIndexOf('\\');
  const parent = sep >= 0 ? input.slice(0, sep) : '';
  const name = sep >= 0 ? input.slice(sep + 1) : input;
  if (!parent || !name) return '';
  return `${parent}\\${name}_source_out`;
}

/**
 * 单文件模式默认输出：输入文件同目录 `<stem>_source_out`
 *（对齐 Qt：input.parent / f"{input.stem}_source_out"）。
 */
export function defaultSourceFileOutputDir(inputFile) {
  const input = normalizePath(inputFile);
  if (!input) return '';
  const sep = input.lastIndexOf('\\');
  const parent = sep >= 0 ? input.slice(0, sep) : '';
  const name = sep >= 0 ? input.slice(sep + 1) : input;
  if (!parent || !name) return '';
  const dot = name.lastIndexOf('.');
  const stem = dot > 0 ? name.slice(0, dot) : name;
  if (!stem) return '';
  return `${parent}\\${stem}_source_out`;
}

/**
 * 源码翻译路径校验。
 * @returns {{ ok: boolean, message: string }}
 */
export function validateSourceLayout(inputFolder, outputFolder) {
  const input = normalizePath(inputFolder);
  const output = normalizePath(outputFolder);
  if (!input) return { ok: false, message: '请选择 game 目录或 .rpy 文件作为输入' };
  if (!output) return { ok: false, message: '请设置独立的输出目录' };
  if (pathsOverlap(input, output)) {
    return { ok: false, message: '源码翻译的输入与输出不能相同或互相包含' };
  }
  // 单文件：输出目录写出同名文件即覆盖原文。
  if (/\.rpy$/i.test(input)) {
    const name = input.split(/[\\/]/).pop() || '';
    if (name && pathKey(`${output}\\${name}`) === pathKey(input)) {
      return { ok: false, message: '源码翻译的输出目录不能直接写回原文件所在位置' };
    }
  }
  return { ok: true, message: '' };
}

/** 翻译方式摘要：明确 mode，不把 single_line / protocol 当方式。 */
export function translationModeSummary(mode) {
  if (mode === 'direct') {
    return '翻译方式：直接翻译 tl/*.rpy（输入=输出=tl 语言目录；source/hook 关闭）';
  }
  if (mode === 'source') {
    return '翻译方式：源码翻译 game/*.rpy（独立输出目录；source 开启 / hook 关闭）';
  }
  if (mode === 'supplement') {
    return '翻译方式：补全翻译（replace_text_auto；source 关闭 / hook 开启）';
  }
  if (mode === 'hook') {
    return '翻译方式：运行时 EXE HOOK（先抽取再翻译；翻译阶段 source/hook 均关闭）';
  }
  return '';
}

/**
 * 从 state.translation.progress 计算百分比。
 * @returns {{ percent: number, label: string }}
 */
export function translationProgressView(progress) {
  const total = Number(progress?.total_line ?? 0) || 0;
  const current = Number(progress?.line ?? 0) || 0;
  if (total > 0) {
    const percent = Math.max(0, Math.min(100, Math.round((current / total) * 100)));
    return { percent, label: `翻译中… ${current}/${total}` };
  }
  if (progress?.phase === 'preparing') {
    return { percent: 0, label: '预处理中…' };
  }
  return { percent: 0, label: '' };
}

/**
 * 启动按钮是否可用（前端预检；最终以后端为准）。
 * @returns {{ canStart: boolean, hint: string }}
 */
export function toolboxStartGate({
  mode,
  hasProject,
  linkOpen,
  engineBusy,
  tlDir,
  gamePath,
  tlParent,
  tlName,
  inputFolder,
  outputFolder,
} = {}) {
  if (!linkOpen) return { canStart: false, hint: '后端未连接，请稍候' };
  if (engineBusy) return { canStart: false, hint: '翻译引擎忙碌，请结束后再开始' };

  if (mode === 'direct') {
    const hasExplicitTl = Boolean(normalizePath(tlParent) && String(tlName || '').trim());
    const hasTl = Boolean(normalizePath(tlDir) || hasExplicitTl || normalizePath(tlParent));
    const hasGame = Boolean(normalizePath(gamePath));
    if (!hasTl && !hasGame && !hasProject) {
      return { canStart: false, hint: '请选择游戏/EXE，或显式指定 tl 父目录与语言名' };
    }
    return { canStart: true, hint: '' };
  }

  if (mode === 'source') {
    const layout = validateSourceLayout(inputFolder, outputFolder);
    if (!layout.ok) return { canStart: false, hint: layout.message };
    return { canStart: true, hint: '' };
  }

  if (mode === 'supplement') {
    if (!normalizePath(gamePath) && !hasProject) {
      return { canStart: false, hint: '请先选择项目目录' };
    }
    return { canStart: true, hint: '' };
  }

  if (mode === 'hook') {
    if (!normalizePath(gamePath)) {
      return { canStart: false, hint: '请选择游戏 EXE 或项目目录' };
    }
    return { canStart: true, hint: '' };
  }

  return { canStart: false, hint: '未知翻译方式' };
}

/** 语言下拉值编码：`ZH` / `ZH:trad` / `EN` … */
export function encodeLangChoice(code, traditional) {
  const c = String(code || 'ZH').toUpperCase();
  if (c === 'ZH' && traditional) return 'ZH:trad';
  return c;
}

export function decodeLangChoice(value) {
  const text = String(value || 'ZH');
  if (text === 'ZH:trad') return { code: 'ZH', traditional: true };
  return { code: text.toUpperCase(), traditional: false };
}

/**
 * 近似后端 RenpyProjectPaths.project_key：normcase(normpath(root))|language。
 * 仅用于前端携带 owner；最终以后端校验为准。
 */
export function toolboxOwnerKey(projectPath, language = 'chinese') {
  const root = normalizePath(projectPath).toLowerCase();
  const lang = String(language || 'chinese').trim().toLowerCase() || 'chinese';
  if (!root) return '';
  return `${root}|${lang}`;
}

/**
 * 将游戏 EXE / 项目目录 / game 目录规范为项目根，对齐 RenpyProjectPaths.from_path。
 * 不做文件系统访问；.exe/.py/.rpy 先退回父目录，basename 为 game 再上退一层。
 */
export function toolboxProjectRootFromGamePath(rawPath) {
  let path = normalizePath(rawPath);
  if (!path) return '';
  const lower = path.toLowerCase();
  // 与后端一致：文件选择（含尚未落盘的 .exe 路径）统一从所在目录推导。
  if (
    lower.endsWith('.exe')
    || lower.endsWith('.py')
    || lower.endsWith('.rpy')
  ) {
    const cut = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'));
    path = cut > 0 ? path.slice(0, cut) : path;
  }
  // 向上定位最近 tl：game/tl/<lang>/... → 项目根；否则 tl 父目录。
  const segments = path.split(/[\\/]+/).filter(Boolean);
  // 保留盘符段如 C:
  const rebuilt = [];
  for (let i = 0; i < segments.length; i += 1) {
    rebuilt.push(segments[i]);
  }
  for (let i = rebuilt.length - 1; i >= 0; i -= 1) {
    if (String(rebuilt[i]).toLowerCase() !== 'tl') continue;
    const tlParent = rebuilt.slice(0, i);
    if (
      tlParent.length
      && String(tlParent[tlParent.length - 1]).toLowerCase() === 'game'
    ) {
      path = tlParent.slice(0, -1).join('\\');
    } else {
      path = tlParent.join('\\');
    }
    // 盘符根 C: → C:\
    if (/^[a-zA-Z]:$/i.test(path)) path = `${path}\\`;
    break;
  }
  path = normalizePath(path);
  const base = path.split(/[\\/]/).pop() || '';
  if (base.toLowerCase() === 'game') {
    const cut = Math.max(path.lastIndexOf('\\'), path.lastIndexOf('/'));
    path = cut > 0 ? normalizePath(path.slice(0, cut)) : path;
  }
  return path;
}

/** 手动目标的 canonical owner key：先规范到项目根再算 key。 */
export function toolboxTargetKeyFromGamePath(rawPath, language = 'chinese') {
  return toolboxOwnerKey(toolboxProjectRootFromGamePath(rawPath), language);
}

/** 从绑定 tl 路径取语言目录名。 */
export function toolboxTlLanguageName(tlFolder, fallback = 'chinese') {
  const bound = normalizePath(tlFolder);
  if (!bound) return fallback;
  const name = bound.split(/[\\/]/).pop();
  return name || fallback;
}
