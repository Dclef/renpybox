/** 网页/AI 翻译向导：对齐 Qt5 HtmlImportPage，走 /api/html-import。 */
import { useEffect, useMemo, useState } from 'react';
import { Button, Checkbox, Collapse, Form, Input, Progress, Select } from 'antd';

import {
  HTML_COPY,
  applyReady,
  defaultPendingTxt,
  excelColumnValue,
  extractReady,
  htmlCopy,
  htmlImportStatusPath,
  htmlImportStatusTone,
  siblingOutput,
} from '../htmlImportView.mjs';
import { useT } from '../i18n';
import type { AppState } from '../useAppState';
import { Banner, SettingsGroup } from '../ui';
import {
  toolStatusText,
  useProjectToolJob,
  type ToolJob,
  type ToolResultBase,
} from './projectToolJob';

interface HtmlResult extends ToolResultBase {
  count?: number;
  filled?: number;
  txt_path?: string;
  manifest_path?: string;
  output_tl_dir?: string;
  output_path?: string;
  success?: boolean;
}

interface HtmlStatus {
  project_key?: string;
  tl_dir?: string;
  manifest_path?: string;
  default_txt_output?: string;
  default_output_tl_dir?: string;
  owner_identity?: string[];
  job?: ToolJob<HtmlResult> | null;
}

const KINDS = [
  'html_import_extract',
  'html_import_apply',
  'html_import_html_to_txt',
  'html_import_txt_to_html',
  'html_import_excel_to_txt',
] as const;

export function HtmlImportPage(props: { state: AppState }) {
  const { state } = props;
  const i18n = useT();
  const uiLang = state.bootLanguage === 'EN' ? 'EN' : 'ZH';
  const t = (table: { ZH: string; EN: string }) => htmlCopy(table, uiLang);

  const [tlDir, setTlDir] = useState('');
  const [txtOut, setTxtOut] = useState('');
  const [manifestPath, setManifestPath] = useState('');
  const [translatedTxt, setTranslatedTxt] = useState('');
  const [outputTl, setOutputTl] = useState('');
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const [htmlPath, setHtmlPath] = useState('');
  const [htmlTxtOut, setHtmlTxtOut] = useState('');
  const [htmlPairs, setHtmlPairs] = useState(false);
  const [txtPath, setTxtPath] = useState('');
  const [htmlOut, setHtmlOut] = useState('');
  const [keepData, setKeepData] = useState(false);
  const [excelPath, setExcelPath] = useState('');
  const [excelTxtOut, setExcelTxtOut] = useState('');
  const [excelColumn, setExcelColumn] = useState<'译文' | '原文'>('译文');

  const statusPath = useMemo(
    () => htmlImportStatusPath({ tlDir, manifestPath }),
    [tlDir, manifestPath],
  );
  const suite = useProjectToolJob<HtmlResult, HtmlStatus>(state, statusPath, KINDS);
  const { status, keyReady, job, result, active, error, cancelling, busy } = suite;
  const engineBusy = state.translation.engine_status !== 'IDLE' || state.translation.stop_barrier || state.translation.single_tasks;
  const blocked = busy || engineBusy || !keyReady || state.link !== 'open';
  const statusText = toolStatusText(i18n, suite, t(HTML_COPY.title));
  const statusTone = htmlImportStatusTone({
    active,
    checking: suite.checking,
    job,
    result,
  });

  useEffect(() => {
    setTlDir('');
    setTxtOut('');
    setManifestPath('');
    setTranslatedTxt('');
    setOutputTl('');
    setConfirmOverwrite(false);
    setAdvancedOpen(false);
    setHtmlPath('');
    setHtmlTxtOut('');
    setHtmlPairs(false);
    setTxtPath('');
    setHtmlOut('');
    setKeepData(false);
    setExcelPath('');
    setExcelTxtOut('');
    setExcelColumn('译文');
  }, [suite.identity]);

  useEffect(() => {
    if (result?.action === 'extract' && result.manifest_path && job?.status === 'done') {
      setManifestPath(String(result.manifest_path));
    }
  }, [result?.action, result?.manifest_path, job?.status, job?.id]);

  async function pickDir(setter: (value: string) => void, onPicked?: (value: string) => void) {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFolder?.();
    if (next && context === suite.identityRef.current) {
      setter(next);
      onPicked?.(next);
    }
  }

  async function pickFile(
    setter: (value: string) => void,
    filters: { name: string; extensions: string[] }[],
  ) {
    const context = suite.identityRef.current;
    const next = await window.renpy?.pickFile?.({ filters });
    if (next && context === suite.identityRef.current) setter(next);
  }

  async function pickSave(
    setter: (value: string) => void,
    defaultPath: string,
    filters: { name: string; extensions: string[] }[],
  ) {
    const context = suite.identityRef.current;
    const next = await window.renpy?.saveFile?.({ defaultPath, filters });
    if (next && context === suite.identityRef.current) setter(next);
  }

  return (
    <div className="rb-asset-page rb-page-scroll" data-rb-page="html-import">
      <Banner tone="info">{t(HTML_COPY.desc)}</Banner>
      {error ? <Banner tone="error">{error}</Banner> : null}
      <Banner tone={statusTone}>{statusText}</Banner>
      {result?.txt_path || result?.manifest_path || result?.output_tl_dir || result?.output_path ? (
        <p className="card-description">
          {[result.txt_path, result.manifest_path, result.output_tl_dir, result.output_path].filter(Boolean).join(' · ')}
        </p>
      ) : null}
      {active ? <Progress percent={Math.min(100, Math.round(((job?.done || 0) / Math.max(job?.total || 1, 1)) * 100))} /> : null}
      {active ? (
        <div className="rb-tool-actions">
          <Button onClick={() => void suite.cancel()} disabled={cancelling || Boolean(job?.cancel_requested)}>
            {i18n('tool_job_cancel')}
          </Button>
        </div>
      ) : null}

      <SettingsGroup title={t(HTML_COPY.step1Title)} description={t(HTML_COPY.step1Hint)}>
        <Form layout="vertical">
          <Form.Item label={t(HTML_COPY.tlDir)}>
            <Input.Group compact style={{ display: 'flex' }}>
              <Input value={tlDir} onChange={(event) => setTlDir(event.target.value)} style={{ flex: 1 }} disabled={blocked} />
              <Button
                disabled={blocked}
                onClick={() => void pickDir(setTlDir, (value) => {
                  if (!txtOut.trim()) setTxtOut(defaultPendingTxt(value));
                })}
              >
                {t(HTML_COPY.browse)}
              </Button>
            </Input.Group>
          </Form.Item>
          <Form.Item label={t(HTML_COPY.txtOut)}>
            <Input.Group compact style={{ display: 'flex' }}>
              <Input value={txtOut} onChange={(event) => setTxtOut(event.target.value)} style={{ flex: 1 }} disabled={blocked} />
              <Button
                disabled={blocked}
                onClick={() => void pickSave(setTxtOut, txtOut || defaultPendingTxt(tlDir) || 'pending_translate.txt', [{ name: 'TXT', extensions: ['txt'] }])}
              >
                {t(HTML_COPY.browse)}
              </Button>
            </Input.Group>
          </Form.Item>
          <Button
            type="primary"
            disabled={blocked || !extractReady(tlDir)}
            onClick={() => void suite.submit('/api/html-import/extract', {
              tl_dir: tlDir.trim(),
              txt_output: txtOut.trim(),
              manifest_output: '',
            })}
          >
            {t(HTML_COPY.extract)}
          </Button>
        </Form>
      </SettingsGroup>

      <SettingsGroup title={t(HTML_COPY.step2Title)} description={t(HTML_COPY.step2Hint)} />

      <SettingsGroup title={t(HTML_COPY.step3Title)} description={t(HTML_COPY.step3Hint)}>
        <Form layout="vertical">
          <Form.Item label={t(HTML_COPY.manifest)}>
            <Input.Group compact style={{ display: 'flex' }}>
              <Input value={manifestPath} onChange={(event) => setManifestPath(event.target.value)} style={{ flex: 1 }} disabled={blocked} />
              <Button disabled={blocked} onClick={() => void pickFile(setManifestPath, [{ name: 'Manifest', extensions: ['json'] }])}>
                {t(HTML_COPY.browse)}
              </Button>
            </Input.Group>
          </Form.Item>
          <Form.Item label={t(HTML_COPY.translated)}>
            <Input.Group compact style={{ display: 'flex' }}>
              <Input value={translatedTxt} onChange={(event) => setTranslatedTxt(event.target.value)} style={{ flex: 1 }} disabled={blocked} />
              <Button disabled={blocked} onClick={() => void pickFile(setTranslatedTxt, [{ name: 'TXT', extensions: ['txt'] }])}>
                {t(HTML_COPY.browse)}
              </Button>
            </Input.Group>
          </Form.Item>
          <Form.Item label={t(HTML_COPY.outputTl)}>
            <Input.Group compact style={{ display: 'flex' }}>
              <Input
                value={outputTl}
                onChange={(event) => setOutputTl(event.target.value)}
                placeholder={status?.default_output_tl_dir || ''}
                style={{ flex: 1 }}
                disabled={blocked}
              />
              <Button disabled={blocked} onClick={() => void pickDir(setOutputTl)}>
                {t(HTML_COPY.browse)}
              </Button>
            </Input.Group>
          </Form.Item>
          <Checkbox
            checked={confirmOverwrite}
            onChange={(event) => setConfirmOverwrite(event.target.checked)}
            disabled={blocked}
          >
            {t(HTML_COPY.confirmOverwrite)}
          </Checkbox>
          <div style={{ marginTop: 12 }}>
            <Button
              type="primary"
              disabled={blocked || !applyReady({ manifestPath, translatedTxt })}
              onClick={() => void suite.submit('/api/html-import/apply', {
                manifest_path: manifestPath.trim(),
                translated_txt: translatedTxt.trim(),
                output_tl_dir: outputTl.trim(),
                source_tl_dir: tlDir.trim(),
                confirm_overwrite: confirmOverwrite,
              })}
            >
              {t(HTML_COPY.apply)}
            </Button>
          </div>
        </Form>
      </SettingsGroup>

      <Collapse
        activeKey={advancedOpen ? ['advanced'] : []}
        onChange={(keys) => setAdvancedOpen(Array.isArray(keys) ? keys.includes('advanced') : keys === 'advanced')}
        items={[{
          key: 'advanced',
          label: t(HTML_COPY.advanced),
          children: (
            <>
              <SettingsGroup title={t(HTML_COPY.htmlToTxt)}>
                <Form layout="vertical">
                  <Form.Item label="HTML">
                    <Input.Group compact style={{ display: 'flex' }}>
                      <Input value={htmlPath} onChange={(event) => setHtmlPath(event.target.value)} style={{ flex: 1 }} disabled={blocked} />
                      <Button disabled={blocked} onClick={() => void pickFile(setHtmlPath, [{ name: 'HTML', extensions: ['html', 'htm'] }])}>
                        {t(HTML_COPY.browse)}
                      </Button>
                    </Input.Group>
                  </Form.Item>
                  <Form.Item label="TXT">
                    <Input value={htmlTxtOut} onChange={(event) => setHtmlTxtOut(event.target.value)} disabled={blocked} />
                  </Form.Item>
                  <Checkbox checked={htmlPairs} onChange={(event) => setHtmlPairs(event.target.checked)} disabled={blocked}>
                    {t(HTML_COPY.pairs)}
                  </Checkbox>
                  <div style={{ marginTop: 12 }}>
                    <Button
                      disabled={blocked || !htmlPath.trim()}
                      onClick={() => void suite.submit('/api/html-import/html-to-txt', {
                        html_path: htmlPath.trim(),
                        txt_output: htmlTxtOut.trim() || siblingOutput(htmlPath, '.txt'),
                        pairs: htmlPairs,
                        confirm_overwrite: true,
                      })}
                    >
                      {t(HTML_COPY.run)}
                    </Button>
                  </div>
                </Form>
              </SettingsGroup>

              <SettingsGroup title={t(HTML_COPY.txtToHtml)}>
                <Form layout="vertical">
                  <Form.Item label="TXT">
                    <Input.Group compact style={{ display: 'flex' }}>
                      <Input value={txtPath} onChange={(event) => setTxtPath(event.target.value)} style={{ flex: 1 }} disabled={blocked} />
                      <Button disabled={blocked} onClick={() => void pickFile(setTxtPath, [{ name: 'TXT', extensions: ['txt'] }])}>
                        {t(HTML_COPY.browse)}
                      </Button>
                    </Input.Group>
                  </Form.Item>
                  <Form.Item label="HTML">
                    <Input value={htmlOut} onChange={(event) => setHtmlOut(event.target.value)} disabled={blocked} />
                  </Form.Item>
                  <Checkbox checked={keepData} onChange={(event) => setKeepData(event.target.checked)} disabled={blocked}>
                    {t(HTML_COPY.keepData)}
                  </Checkbox>
                  <div style={{ marginTop: 12 }}>
                    <Button
                      disabled={blocked || !txtPath.trim()}
                      onClick={() => void suite.submit('/api/html-import/txt-to-html', {
                        txt_path: txtPath.trim(),
                        html_output: htmlOut.trim() || siblingOutput(txtPath, '.html'),
                        keep_data: keepData,
                        confirm_overwrite: true,
                      })}
                    >
                      {t(HTML_COPY.run)}
                    </Button>
                  </div>
                </Form>
              </SettingsGroup>

              <SettingsGroup title={t(HTML_COPY.excelToTxt)}>
                <Form layout="vertical">
                  <Form.Item label="Excel">
                    <Input.Group compact style={{ display: 'flex' }}>
                      <Input value={excelPath} onChange={(event) => setExcelPath(event.target.value)} style={{ flex: 1 }} disabled={blocked} />
                      <Button disabled={blocked} onClick={() => void pickFile(setExcelPath, [{ name: 'Excel', extensions: ['xlsx'] }])}>
                        {t(HTML_COPY.browse)}
                      </Button>
                    </Input.Group>
                  </Form.Item>
                  <Form.Item label="TXT">
                    <Input value={excelTxtOut} onChange={(event) => setExcelTxtOut(event.target.value)} disabled={blocked} />
                  </Form.Item>
                  <Form.Item label={t(HTML_COPY.column)}>
                    <Select
                      value={excelColumn}
                      onChange={(value) => setExcelColumn(excelColumnValue(value))}
                      options={[
                        { value: '译文', label: t(HTML_COPY.columnTranslation) },
                        { value: '原文', label: t(HTML_COPY.columnOriginal) },
                      ]}
                      disabled={blocked}
                    />
                  </Form.Item>
                  <Button
                    disabled={blocked || !excelPath.trim()}
                    onClick={() => void suite.submit('/api/html-import/excel-to-txt', {
                      excel_path: excelPath.trim(),
                      txt_output: excelTxtOut.trim() || siblingOutput(excelPath, '.txt'),
                      column: excelColumn,
                      confirm_overwrite: true,
                    })}
                  >
                    {t(HTML_COPY.run)}
                  </Button>
                </Form>
              </SettingsGroup>
            </>
          ),
        }]}
      />
    </div>
  );
}

export default HtmlImportPage;
