/**
 * 网页/AI 翻译向导纯函数与双语文案（就地 const，避免并行改 i18n）。
 * 对齐 Qt5 HtmlImportPage 默认值与三步 + 高级折叠互转。
 */

export const HTML_COPY = {
  title: { ZH: '网页 / AI 翻译向导', EN: 'Web / AI Translation Wizard' },
  desc: {
    ZH: '把一键翻译抽取后的 game/tl/<语言> 目录变成 TXT，交给 AI 或 Google 网页翻译，再一键回填生成翻译完成的 TL 目录。全程只需三步。',
    EN: 'Turn the extracted game/tl/<language> folder into a TXT, translate it with AI or Google web translation, then write back a finished TL folder. Three steps.',
  },
  step1Title: { ZH: '第 1 步：提取待翻译文本', EN: 'Step 1: Extract pending text' },
  step1Hint: {
    ZH: '选择一键翻译抽取后的 game/tl/<语言> 目录（例如 game/tl/chinese）。只会提取官方抽取产生、还没翻译的条目，补充抽取的内容不参与。',
    EN: 'Pick the game/tl/<language> folder produced by extraction (e.g. game/tl/chinese). Only untranslated official entries are exported; supplemental entries are skipped.',
  },
  tlDir: { ZH: 'TL 目录', EN: 'TL Folder' },
  txtOut: { ZH: '输出 TXT', EN: 'Output TXT' },
  extract: { ZH: '① 提取成 TXT', EN: '① Extract to TXT' },
  step2Title: { ZH: '第 2 步：拿去翻译', EN: 'Step 2: Translate the TXT' },
  step2Hint: {
    ZH: '把 TXT 粘贴给 AI 或上传到 Google 网页翻译。每行一条译文，顺序一致，行数不能少。工具不调用任何翻译 API。',
    EN: 'Paste the TXT to an AI or upload it to Google web translation. One translation per line, same order, no fewer lines. No translation API is called here.',
  },
  step3Title: { ZH: '第 3 步：回填生成新 TL', EN: 'Step 3: Write back a new TL' },
  step3Hint: {
    ZH: '选择行号清单与译文 TXT，生成同级 <语言>_translated 新目录；原 TL 不会被改写。',
    EN: 'Select the manifest and translated TXT to build a sibling <language>_translated folder. The original TL is never modified.',
  },
  manifest: { ZH: '行号清单', EN: 'Manifest' },
  translated: { ZH: '译文 TXT', EN: 'Translated TXT' },
  outputTl: { ZH: '输出 TL 目录', EN: 'Output TL Folder' },
  apply: { ZH: '③ 生成翻译完成的 TL', EN: '③ Generate finished TL' },
  confirmOverwrite: { ZH: '确认覆盖已有输出目录', EN: 'Confirm overwrite of existing output folder' },
  advanced: { ZH: '高级：HTML / TXT / Excel 互转', EN: 'Advanced: HTML / TXT / Excel conversion' },
  htmlToTxt: { ZH: 'HTML → TXT', EN: 'HTML → TXT' },
  txtToHtml: { ZH: 'TXT → HTML', EN: 'TXT → HTML' },
  excelToTxt: { ZH: 'Excel → TXT', EN: 'Excel → TXT' },
  pairs: {
    ZH: '输出 原文→译文 对照（需 HTML 含 data payload）',
    EN: 'Export original→translation pairs (requires data payload)',
  },
  keepData: {
    ZH: '写入附加数据（保留原文/译文结构）',
    EN: 'Include additional data (preserve original/translation structure)',
  },
  column: { ZH: '导出列', EN: 'Export Column' },
  columnTranslation: { ZH: '译文', EN: 'Translation' },
  columnOriginal: { ZH: '原文', EN: 'Original' },
  browse: { ZH: '浏览', EN: 'Browse' },
  run: { ZH: '执行', EN: 'Run' },
  needTl: { ZH: '请先选择 TL 目录', EN: 'Select a TL folder first.' },
  needApply: { ZH: '请先选行号清单和译文 TXT', EN: 'Select the manifest and translated TXT first.' },
  emptyOk: {
    ZH: '没有待翻译的条目（可能已全部翻译，或只有补充抽取内容）。',
    EN: 'Nothing to translate (already translated, or only supplemental entries).',
  },
};

export function htmlCopy(table, lang = 'ZH') {
  return table[lang === 'EN' ? 'EN' : 'ZH'] || table.ZH;
}

/** 浏览 TL 后若 TXT 为空，填 pending_translate.txt（对齐 Qt）。 */
export function defaultPendingTxt(tlDir = '') {
  const trimmed = String(tlDir || '').trim();
  if (!trimmed) return '';
  const sep = trimmed.includes('\\') && !trimmed.includes('/') ? '\\' : '/';
  return `${trimmed.replace(/[\\/]+$/, '')}${sep}pending_translate.txt`;
}

export function htmlImportStatusPath({ tlDir = '', manifestPath = '' } = {}) {
  const params = new URLSearchParams();
  const tl = String(tlDir || '').trim();
  const manifest = String(manifestPath || '').trim();
  if (tl) params.set('tl_dir', tl);
  if (manifest) params.set('manifest_path', manifest);
  const query = params.toString();
  return query ? `/api/html-import?${query}` : '/api/html-import';
}

export function extractReady(tlDir = '') {
  return Boolean(String(tlDir || '').trim());
}

export function applyReady({ manifestPath = '', translatedTxt = '' } = {}) {
  return Boolean(String(manifestPath || '').trim() && String(translatedTxt || '').trim());
}

export function siblingOutput(inputPath = '', suffix = '.txt') {
  const value = String(inputPath || '').trim();
  if (!value) return '';
  return value.replace(/\.[^.\\/]+$/, '') + suffix;
}

export function excelColumnValue(uiValue) {
  return uiValue === '原文' ? '原文' : '译文';
}

/** 从 status 快照取 owner_identity；非法或缺省返回 undefined（不发送）。 */
export function htmlImportOwnerIdentity(status) {
  const value = status?.owner_identity;
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) return undefined;
  return value;
}

/** 终态 Banner：取消/部分写入/业务失败不用绿色成功。 */
export function htmlImportStatusTone({ active = false, checking = false, job = null, result = null } = {}) {
  if (active || checking) return 'info';
  const status = job?.status;
  const partial = Boolean(result?.partial);
  const failedBiz = result?.success === false;
  if (status === 'cancelled' || partial || (status === 'done' && failedBiz)) return 'warning';
  if (status === 'failed') return result?.written || partial ? 'warning' : 'error';
  if (status === 'done') return 'success';
  return 'info';
}
