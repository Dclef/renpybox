/**
 * RPY 抽取设置纯函数：生效/未保存摘要、模式与方案校验、分页与脏检查，对齐 Qt5。
 */

const DEFAULT_MODE_LABELS = {
  builtin: '只用内置',
  combined: '内置＋自定义',
  custom: '仅自定义',
};

export const RPY_PAGE_SIZE = 200;

/** 抽取方式是否需要自定义方案。 */
export function modeNeedsProfile(mode) {
  return String(mode || 'builtin') !== 'builtin';
}

/** 下拉与已生效选择是否不一致（仅 UI 态，不等于已落盘）。 */
export function isSelectionDirty(applied, pending) {
  const aMode = String(applied?.mode ?? 'builtin');
  const pMode = String(pending?.mode ?? 'builtin');
  const aId = applied?.profileId ?? null;
  const pId = pending?.profileId ?? null;
  return aMode !== pMode || aId !== pId;
}

/** 编辑器相对基线是否有未保存修改。 */
export function isEditorDirty(editor, baselineJson) {
  if (!editor) return false;
  try {
    return JSON.stringify(editor) !== String(baselineJson ?? '');
  } catch {
    return true;
  }
}

/** 页面级 dirty：方式未应用或编辑器未保存。 */
export function isPageDirty(selectionDirty, editorDirty) {
  return Boolean(selectionDirty || editorDirty);
}

/** 显式应用前校验：非 builtin 必须有方案；custom 需至少一条启用规则（若提供 profile）。 */
export function canApplySelection(mode, profileId, profile = null) {
  const current = String(mode || 'builtin');
  if (current === 'builtin') return true;
  if (!profileId) return false;
  if (current === 'custom' && profile && Array.isArray(profile.rules)) {
    return profile.rules.some((rule) => rule && rule.enabled === true);
  }
  return true;
}

/** 高级区在 combined/custom 时不可折叠。 */
export function advancedMustStayOpen(mode) {
  return modeNeedsProfile(mode);
}

/**
 * 摘要文案：与已生效一致显示「当前已生效」，否则「未保存」。
 * labels: { current, pending, modes, noProfile }
 */
export function formatSelectionSummary(applied, pending, labels = {}) {
  const modes = labels.modes || DEFAULT_MODE_LABELS;
  const noProfile = labels.noProfile || '未选择自定义方案';
  const currentTpl = labels.current || '当前已生效：{mode} · {name}';
  const pendingTpl = labels.pending || '未保存：{mode} · {name}（点「应用设置」后生效）';
  const dirty = isSelectionDirty(applied, pending);
  const mode = String((dirty ? pending?.mode : applied?.mode) || 'builtin');
  const name = String(
    (dirty ? pending?.name : applied?.name) || noProfile,
  );
  const modeLabel = modes[mode] || mode;
  const tpl = dirty ? pendingTpl : currentTpl;
  return String(tpl)
    .replaceAll('{mode}', modeLabel)
    .replaceAll('{name}', name);
}

/** 分类说明：source / tl。 */
export function categoryScopeKey(category) {
  return String(category || 'source') === 'tl' ? 'tl' : 'source';
}

/** 预览结果是否允许保存绑定（本地已失效的 scan 不可用）。 */
export function canSaveBind(scan) {
  return Boolean(scan && scan.has_scan !== false && scan.completed && !scan.error);
}

/** 预览是否可继续。 */
export function canContinuePreview(scan) {
  return Boolean(scan && scan.has_scan !== false && !scan.completed && !scan.error);
}

/** 规范化页码：1-based，受 total/pageSize 约束。 */
export function clampScanPage(page, total, pageSize = RPY_PAGE_SIZE) {
  const size = Math.max(1, Number(pageSize) || RPY_PAGE_SIZE);
  const count = Math.max(1, Math.ceil(Math.max(0, Number(total) || 0) / size) || 1);
  const current = Math.max(1, Math.floor(Number(page) || 1));
  return Math.min(current, count);
}

/** 页码标签：`当前 / 总页`。 */
export function formatPageLabel(page, total, pageSize = RPY_PAGE_SIZE) {
  const size = Math.max(1, Number(pageSize) || RPY_PAGE_SIZE);
  const count = Math.max(1, Math.ceil(Math.max(0, Number(total) || 0) / size) || 1);
  const current = clampScanPage(page, total, size);
  return `${current} / ${count}`;
}

/** 从分类模板构造新增规则（id/name 由调用方覆盖）。 */
export function buildNewRule(template, index) {
  const base = template && typeof template === 'object' ? { ...template } : {
    include_globs: ['*.rpy', '**/*.rpy'],
    pattern: String.raw`\bcall\s+reply_message\(\s*(?P<text>"(?:\\.|[^"\\])*")\s*\)`,
    flags: [],
    text_group: 'text',
    note: '',
    positive_samples: ['call reply_message("Try again.")'],
    negative_samples: ['call reply_message(player_name)'],
  };
  const id = `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
  return {
    ...base,
    id,
    name: `规则 ${index}`,
    enabled: true,
    include_globs: Array.isArray(base.include_globs) ? [...base.include_globs] : ['*.rpy', '**/*.rpy'],
    flags: Array.isArray(base.flags) ? [...base.flags] : [],
    positive_samples: Array.isArray(base.positive_samples) ? [...base.positive_samples] : [],
    negative_samples: Array.isArray(base.negative_samples) ? [...base.negative_samples] : [],
  };
}

/** 克隆当前方案为新编辑稿（新 id，不落盘）。 */
export function cloneProfileDraft(profile, copySuffix = '（副本）') {
  if (!profile || typeof profile !== 'object') return null;
  const id = `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
  return {
    ...JSON.parse(JSON.stringify(profile)),
    id,
    name: `${profile.name || ''}${copySuffix}`,
  };
}
