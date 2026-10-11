/** 译文复用页：状态路径与摘要。 */

/**
 * @param {{ sourceDir?: string, targetDir?: string }} opts
 */
export function translationReuseStatusPath(opts = {}) {
  const params = new URLSearchParams();
  const source = String(opts.sourceDir || '').trim();
  const target = String(opts.targetDir || '').trim();
  if (source) params.set('source_dir', source);
  if (target) params.set('target_dir', target);
  const qs = params.toString();
  return qs ? `/api/translation-reuse?${qs}` : '/api/translation-reuse';
}

/**
 * @param {object | null | undefined} result
 * @param {'ZH'|'EN'} lang
 */
export function formatReuseSummary(result, lang = 'ZH') {
  if (!result) return lang === 'EN' ? 'Not previewed' : '尚未预览';
  const parts = lang === 'EN'
    ? [
      `Reusable ${result.reusable_entries ?? 0}`,
      `conflicts ${result.conflicts ?? 0}`,
      `already ${result.already_reused ?? 0}`,
      `unmatched ${result.unmatched_entries ?? 0}`,
    ]
    : [
      `可复用 ${result.reusable_entries ?? 0}`,
      `冲突 ${result.conflicts ?? 0}`,
      `已复用 ${result.already_reused ?? 0}`,
      `未匹配 ${result.unmatched_entries ?? 0}`,
    ];
  let text = parts.join(lang === 'EN' ? ', ' : '，');
  if (result.applied_entries) {
    text = (lang === 'EN' ? `Applied ${result.applied_entries}. ` : `已写入 ${result.applied_entries} 条。`) + text;
  }
  if (result.hook_updated) {
    text += lang === 'EN' ? '\nReplace hook updated.' : '\n已更新替换钩子。';
  }
  if (result.unmatched_entries) {
    text += lang === 'EN'
      ? '\nUnmatched entries keep empty; ambiguous old translations are skipped.'
      : '\n未匹配条目保持空白；旧译文歧义已跳过。';
  }
  if (result.backup_path) {
    text += (lang === 'EN' ? `\nBackup: ${result.backup_path}` : `\n备份: ${result.backup_path}`);
  }
  const failed = Array.isArray(result.failed_files) ? result.failed_files : [];
  if (failed.length) {
    text += lang === 'EN'
      ? `\n${failed.length} file(s) failed to write.`
      : `\n${failed.length} 个文件写入失败。`;
  }
  return text;
}

/** 提交用的 owner 快照：有绑定则用 status.owner_project_key，未绑定为空。 */
export function reuseOwnerProjectKey(status) {
  return String(status?.owner_project_key ?? '').trim();
}

/** 路径相同或祖孙重叠时禁止提交 */
export function reusePathsConflict(sourceDir, targetDir) {
  const a = String(sourceDir || '').trim().replace(/[\\/]+$/, '');
  const b = String(targetDir || '').trim().replace(/[\\/]+$/, '');
  if (!a || !b) return false;
  const na = a.replace(/\\/g, '/').toLowerCase();
  const nb = b.replace(/\\/g, '/').toLowerCase();
  if (na === nb) return true;
  return na.startsWith(`${nb}/`) || nb.startsWith(`${na}/`);
}
