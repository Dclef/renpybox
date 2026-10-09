/**
 * 项目设置页 —— 对齐 frontend/Project/ProjectPage.py 的实测几何。
 *
 * 实测（nav=256、页宽 1023）：
 *   头部 975x36 @ (24,24)：TitleLabel 18px + CaptionLabel 12px（间距 2）
 *   滚动区 975x669 @ (24,68)（头部底 60 之后 8px）
 *   恰好 6 张卡、每张 975x66、纵向节距 74（卡高 66 + 间距 8）
 *     卡内边距左 17、标题 fpx=14 @y=17、说明 fpx=12 @y=37、控件右侧垂直居中
 *     ComboBox 72x27 / PushButton 78x27 / SwitchButton 56x22
 *
 * 顺序同 renpybox/frontend/Project/ProjectPage.py:81-86。
 * 目录选择走主进程原生 dialog（`window.renpy.pickFolder`），对应原壳的
 * `QFileDialog.getExistingDirectory`；「打开」对应 `webbrowser.open`。
 *
 * 注意：真实 ProjectPage **没有「工程路径」卡片** —— 项目身份是选输入目录时
 * 由 `_sync_renpy_paths_from_selection()` 顺带绑定的，所以这里选完目录会调
 * `POST /api/project/resolve`（后端只在目录确实含 Ren'Py 结构时才认）。
 */

import { useCallback, useEffect, useState } from 'react';

import { resolveProject } from '../api';
import { LANGUAGE_OPTIONS } from '../settingsSchema';
import type { AppState } from '../useAppState';
import { SettingCard } from '../ui';

export function ProjectPage(props: { state: AppState }) {
  const { state } = props;
  const [inputFolder, setInputFolder] = useState('');
  const [outputFolder, setOutputFolder] = useState('');
  const [busy, setBusy] = useState(false);

  const values = state.settings?.values;
  const sourceLanguage = String(values?.source_language ?? 'EN');
  const targetLanguage = String(values?.target_language ?? 'ZH');

  // 重新显示时刷新路径，避免沿用旧页面创建时的配置快照（对齐 showEvent）。
  useEffect(() => {
    if (!values) return;
    setInputFolder(String(values.input_folder ?? ''));
    setOutputFolder(String(values.output_folder ?? ''));
  }, [values]);

  /**
   * 选目录。原壳的 `_sync_renpy_paths_from_selection` 语义：
   * 只有目录本身带 Ren'Py 项目结构时才同步项目身份，否则仅保留为输入目录
   * —— 用户自建的翻译目录被当成项目根，会让 renpy_tl_folder 指向不存在的路径。
   */
  const pickFolder = useCallback(
    async (which: 'input' | 'output', current: string) => {
      const picked = await window.renpy?.pickFolder(current || undefined);
      if (!picked) return;
      setBusy(true);
      try {
        state.setSetting(which === 'input' ? 'input_folder' : 'output_folder', picked);
        if (which === 'input') {
          try {
            await resolveProject(picked);
            await Promise.all([state.reloadProject(), state.reloadSettings()]);
            state.pushToast('success', '已识别 Ren\'Py 项目并绑定工程');
          } catch (error) {
            const message = error instanceof Error ? error.message : '';
            state.pushToast(
              'info',
              message || '该目录不含 Ren\'Py 项目结构，只作为翻译输入目录保留',
            );
          }
        }
      } finally {
        setBusy(false);
      }
    },
    [state],
  );

  const pickProject = useCallback(async () => {
    const current = String(state.project?.renpy_project_path ?? inputFolder);
    const picked = await window.renpy?.pickFolder(current || undefined);
    if (!picked) return;
    setBusy(true);
    try {
      await resolveProject(picked);
      await Promise.all([state.reloadProject(), state.reloadSettings()]);
      state.pushToast('success', 'Ren\'Py 项目已绑定');
    } catch (error) {
      state.pushToast('error', error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }, [inputFolder, state]);

  const openFolder = useCallback((target: string) => {
    if (!target) return;
    void window.renpy?.openPath(target);
  }, []);

  const projectRoot = String(state.project?.renpy_project_path ?? '');
  const gameFolder = String(state.project?.renpy_game_folder ?? '');
  const tlFolder = String(state.project?.renpy_tl_folder ?? '');
  const projectLabel = projectRoot.split(/[\\/]/).filter(Boolean).at(-1) || '';

  return (
    <div className="settings-layout">
      <header className="settings-header">
        <h1 className="settings-title">项目设置</h1>
        <p className="settings-subtitle">先绑定带 game/ 的 Ren'Py 工程，再指定翻译读取和写出的目录</p>
      </header>

      <div className="settings-scroll">
        <section className="project-identity" data-bound={projectRoot ? 'true' : 'false'}>
          <div className="project-identity-copy">
            <span className="project-identity-kicker">{projectRoot ? '已绑定工程' : '尚未绑定工程'}</span>
            <h2>{projectLabel || '选择 Ren\'Py 项目文件夹'}</h2>
            <p>
              {projectRoot
                ? '工程根、game 与 tl 目录来自项目结构。输入目录可以另选，不含 game/ 时不会改写工程身份。'
                : '请选择包含 game/ 的项目根目录。只选译文文件夹不会绑定工程。'}
            </p>
          </div>
          <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void pickProject()}>
            {projectRoot ? '重新选择工程' : '选择工程'}
          </button>
          <dl className="project-identity-paths">
            <div>
              <dt>工程根</dt>
              <dd title={projectRoot || undefined}>{projectRoot || '未绑定'}</dd>
            </div>
            <div>
              <dt>game</dt>
              <dd title={gameFolder || undefined}>{gameFolder || '—'}</dd>
            </div>
            <div>
              <dt>tl</dt>
              <dd title={tlFolder || undefined}>{tlFolder || '—'}</dd>
            </div>
          </dl>
        </section>

        <div className="setting-card-list">
          <SettingCard title="原文语言" description="设置当前项目中输入文本的语言">
            <select
              aria-label="原文语言"
              value={sourceLanguage}
              disabled={state.saving}
              onChange={(event) => state.setSetting('source_language', event.target.value)}
            >
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </SettingCard>

          <SettingCard title="译文语言" description="设置当前项目中输出文本的语言">
            <select
              aria-label="译文语言"
              value={targetLanguage}
              disabled={state.saving}
              onChange={(event) => state.setSetting('target_language', event.target.value)}
            >
              {LANGUAGE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </SettingCard>

          <SettingCard
            title="输入文件夹"
            description={inputFolder || '未设置。翻译从这里读取待译文本'}
          >
            <button type="button" className="btn" disabled={busy} onClick={() => void pickFolder('input', inputFolder)}>
              选择
            </button>
            <button type="button" className="btn" disabled={!inputFolder} onClick={() => openFolder(inputFolder)}>
              打开
            </button>
          </SettingCard>

          <SettingCard
            title="输出文件夹"
            description={outputFolder || '未设置。不能与输入文件夹相同'}
          >
            <button type="button" className="btn" disabled={busy} onClick={() => void pickFolder('output', outputFolder)}>
              选择
            </button>
            <button type="button" className="btn" disabled={!outputFolder} onClick={() => openFolder(outputFolder)}>
              打开
            </button>
          </SettingCard>

          <SettingCard
            title="任务完成时打开输出文件夹"
            description="启用此功能后，将在任务完成时自动打开输出文件夹"
          >
            <button
              type="button"
              className="switch"
              role="switch"
              aria-checked={values?.output_folder_open_on_finish === true}
              aria-label="任务完成时打开输出文件夹"
              disabled={state.saving}
              onClick={() =>
                state.setSetting('output_folder_open_on_finish', values?.output_folder_open_on_finish !== true)
              }
            />
          </SettingCard>

          <SettingCard
            title="使用繁体输出中文"
            description="启用此功能后，在译文语言设置为中文时，将使用繁体字形输出中文文本"
          >
            <button
              type="button"
              className="switch"
              role="switch"
              aria-checked={values?.traditional_chinese_enable === true}
              aria-label="使用繁体输出中文"
              disabled={state.saving}
              onClick={() =>
                state.setSetting('traditional_chinese_enable', values?.traditional_chinese_enable !== true)
              }
            />
          </SettingCard>
        </div>
      </div>
    </div>
  );
}
