/**
 * 更新提示弹窗：桌面端有结果时必须主动告诉用户。
 *
 * 以前只有一个静默的后台检查，结果写进设置页的一行文字 —— 用户永远
 * 不会主动翻到那一页，于是「检查了但没提示」＝「没检查」。
 *
 * 这里做两件事：
 *   1. 检查到新版本 → 立刻弹窗（同一版本只弹一次，关掉后记进 localStorage，
 *      有新版本再弹）。
 *   2. 启动时发现运行版本和上次记录的不同 → 弹「更新完成」并展示该版本的更新日志。
 */

import { useEffect, useState } from 'react';

import { ChangelogView } from './ChangelogView';
import { useT } from '../i18n';
import type { DesktopUpdateState } from '../preload';
import { Dialog } from '../ui';
import { latestChangelogSection, shouldAnnounceUpdate, shouldOfferUpdate } from '../updateNotice.mjs';

const DISMISS_KEY = 'renpybox.dismissedUpdateVersion';
const LAST_RUN_KEY = 'renpybox.lastRunVersion';

function readStore(key: string): string {
  try { return window.localStorage.getItem(key) ?? ''; } catch { return ''; }
}

function writeStore(key: string, value: string) {
  try { window.localStorage.setItem(key, value); } catch { /* 隐私模式等场景忽略 */ }
}

export function UpdateNotice() {
  const t = useT();
  const [update, setUpdate] = useState<DesktopUpdateState | null>(null);
  const [dismissed, setDismissed] = useState(() => readStore(DISMISS_KEY));
  const [downloading, setDownloading] = useState(false);
  const [justUpdated, setJustUpdated] = useState<{ version: string; notes: string } | null>(null);
  const [showUpdated, setShowUpdated] = useState(false);

  // 订阅主进程推送的更新状态；同时补一次初始快照（推送可能早于挂载）。
  useEffect(() => {
    const bridge = window.renpy;
    if (!bridge) return;
    let active = true;
    let received = false;
    const unsubscribe = bridge.updater.onState((next) => {
      received = true;
      if (active) setUpdate(next);
    });
    void bridge.updater.state()
      .then((next) => { if (active && !received) setUpdate(next); })
      .catch(() => { /* 设置页会报同一条错误，这里静默 */ });
    return () => { active = false; unsubscribe(); };
  }, []);

  // 更新完成检测：运行版本变了就弹一次变更说明。
  useEffect(() => {
    const bridge = window.renpy;
    if (!bridge) return;
    let active = true;
    void bridge.appInfo().then(async (info) => {
      if (!active) return;
      const current = String(info?.appVersion ?? '').trim();
      if (!current) return;
      const previous = readStore(LAST_RUN_KEY);
      writeStore(LAST_RUN_KEY, current);
      // 首次运行没有记录，不算「刚更新」。
      if (!shouldAnnounceUpdate(previous, current)) return;
      let notes = '';
      try {
        notes = latestChangelogSection(await bridge.changelog());
      } catch { /* 日志读不到就只报版本号 */ }
      if (!active) return;
      setJustUpdated({ version: current, notes });
      setShowUpdated(true);
    }).catch(() => { /* 读不到版本信息时不打扰用户 */ });
    return () => { active = false; };
  }, []);

  // shouldOfferUpdate 已经排除了 packaged/status/空版本，这里做一次显式收窄给 TS 看。
  const offered = shouldOfferUpdate(update, dismissed) && update ? update : null;

  const download = async () => {
    const updater = window.renpy?.updater;
    if (!updater || downloading) return;
    setDownloading(true);
    try { setUpdate(await updater.download()); } catch { /* 设置页与壳窗口共用同一份错误展示 */ }
    finally { setDownloading(false); }
  };

  return (
    <>
      {offered ? (
        <Dialog
          title={`${t('app_update_notice_title')} ${offered.version}`}
          confirmText={downloading ? t('app_update_checking') : t('app_update_download')}
          cancelText={t('app_update_notice_later')}
          onCancel={() => {
            const version = offered.version;
            writeStore(DISMISS_KEY, version);
            setDismissed(version);
          }}
          onConfirm={() => { void download(); }}
        >
          {offered.releaseNotes?.trim()
            ? <ChangelogView markdown={latestChangelogSection(offered.releaseNotes)} />
            : t('app_update_notice_body')}
        </Dialog>
      ) : null}
      {justUpdated && showUpdated ? (
        <Dialog
          title={`${t('app_updated_title')} ${justUpdated.version}`}
          confirmText={t('app_updated_confirm')}
          onCancel={() => setShowUpdated(false)}
          onConfirm={() => setShowUpdated(false)}
        >
          {justUpdated.notes
            ? <ChangelogView markdown={justUpdated.notes} />
            : t('app_updated_body')}
        </Dialog>
      ) : null}
    </>
  );
}
