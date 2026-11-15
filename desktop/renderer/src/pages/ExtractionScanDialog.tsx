import { useEffect, useRef, useState } from 'react';
import { Dialog } from '../ui';
import { checkpointScanRequestBody, hasCheckpointResumeCapability, isCheckpointScanPath } from '../glossaryView.mjs';
import type { TextKey } from '../i18n';

type T = (key: TextKey) => string;
type ScanMode = 'resume' | 'restart';

export function ExtractionResumeOptions({ supported, mode, onChange, t }: {
  supported: boolean; mode: ScanMode; onChange: (mode: ScanMode) => void; t: T;
}) {
  if (!supported) return null;
  return (
    <fieldset className="rb-extraction-resume-options" data-testid="extraction-resume-options">
      <legend>{t('lexicon_checkpoint_mode')}</legend>
      <label><input type="radio" name="checkpoint-scan-mode" value="resume" checked={mode === 'resume'} onChange={() => onChange('resume')} /> {t('lexicon_checkpoint_continue')}</label>
      <p className="rb-agent-feedback-note">{t('lexicon_checkpoint_continue_note')}</p>
      <label><input type="radio" name="checkpoint-scan-mode" value="restart" checked={mode === 'restart'} onChange={() => onChange('restart')} /> {t('lexicon_checkpoint_restart')}</label>
      <p className="rb-agent-feedback-note">{t('lexicon_checkpoint_restart_note')}</p>
    </fieldset>
  );
}

/** Capability/mode hooks live here, never in GlossaryPage or DataSheet. */
export function ExtractionScanDialog({ path, body, title, message, projectKey, loadCapabilities, onConfirm, onCancel, t }: {
  path: string; body: Record<string, unknown>; title: string; message: string; projectKey: string;
  loadCapabilities: (signal: AbortSignal) => Promise<unknown>;
  onConfirm: (body: Record<string, unknown>) => void; onCancel: () => void; t: T;
}) {
  const owner = useRef(projectKey);
  const [mode, setMode] = useState<ScanMode>('resume');
  const [capabilities, setCapabilities] = useState<unknown>(null);
  const [checking, setChecking] = useState(isCheckpointScanPath(path));

  useEffect(() => {
    if (owner.current !== projectKey) return;
    if (!isCheckpointScanPath(path)) { setChecking(false); return; }
    let alive = true;
    const controller = new AbortController();
    setChecking(true);
    const settle = (response: unknown) => {
      if (!alive) return;
      alive = false;
      setCapabilities(response);
      setChecking(false);
    };
    const timer = window.setTimeout(() => { settle(null); controller.abort(); }, 3000);
    void loadCapabilities(controller.signal).then(settle, () => settle(null)).finally(() => window.clearTimeout(timer));
    return () => { alive = false; window.clearTimeout(timer); controller.abort(); };
  }, [path, projectKey, loadCapabilities]);

  useEffect(() => {
    if (owner.current !== projectKey) onCancel();
  }, [projectKey, onCancel]);

  if (owner.current !== projectKey) return null;
  return (
    <Dialog title={title} onCancel={onCancel} onConfirm={checking ? undefined : () => {
      if (owner.current === projectKey) onConfirm(checkpointScanRequestBody(path, body, capabilities, mode));
    }}>
      <p>{message}</p>
      {checking ? <p className="rb-agent-feedback-note" role="status">{t('lexicon_checkpoint_checking')}</p> : null}
      <ExtractionResumeOptions supported={!checking && hasCheckpointResumeCapability(capabilities)} mode={mode} onChange={setMode} t={t} />
    </Dialog>
  );
}
