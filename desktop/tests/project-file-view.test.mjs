/**
 * .rbox 工程文件界面的静态契约。
 *
 * 运行（pwsh）：
 *   cd desktop; node --test tests/project-file-view.test.mjs
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const src = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'renderer', 'src');
const read = (...parts) => fs.readFileSync(path.join(src, ...parts), 'utf8');

test('API 封装三条 .rbox 路由且都走 POST', () => {
  const api = read('api.ts');
  for (const [fn, route] of [
    ['inspectProjectFile', 'inspect'],
    ['exportProjectFile', 'export'],
    ['importProjectFile', 'import'],
  ]) {
    const body = api.match(new RegExp(`export function ${fn}\\([\\s\\S]*?\\n\\}`))?.[0] ?? '';
    assert.ok(body, `${fn} 缺失`);
    assert.match(body, new RegExp(`'/api/project/file/${route}'`));
    assert.match(body, /method: 'POST'/);
  }
});

test('项目页用原生对话框和 rbox 过滤器，保存时补全后缀', () => {
  const page = read('pages', 'ProjectPage.tsx');
  assert.match(page, /\{ name: 'RenpyBox Project', extensions: \['rbox'\] \}/);
  assert.match(page, /window\.renpy\?\.saveFile\(\{.*filters: RBOX_FILTERS \}\)/);
  assert.match(page, /window\.renpy\?\.pickFile\(\{ filters: RBOX_FILTERS \}\)/);
  assert.match(page, /\/\\\.rbox\$\/i\.test\(path\) \? path : `\$\{path\}\.rbox`/);
  assert.match(page, /exportProjectFile\(withRboxSuffix\(picked\)\)|const target = withRboxSuffix\(picked\)/);
});

test('导入先 inspect，确认对话框里才调用 import，成功后刷新三份状态', () => {
  const page = read('pages', 'ProjectPage.tsx');
  // 按钮与双击 .rbox 都走 beginImport：先 inspect，把 import 留在确认框里。
  const begin = page.match(/const beginImport = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(begin, /inspectProjectFile\(path\)/);
  assert.doesNotMatch(begin, /importProjectFile/);

  const pick = page.match(/const pickImportFile = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(pick, /beginImport\(picked\)/);
  assert.doesNotMatch(pick, /importProjectFile/);

  const confirm = page.match(/const confirmImport = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(confirm, /importProjectFile\(pending\.info\.path, bind\)/);
  assert.match(confirm, /state\.reloadProject\(\), state\.reloadSettings\(\), state\.reloadTranslation\(\)/);
  assert.match(page, /onConfirm=\{busy \? undefined : \(\) => void confirmImport\(pendingImport, importBind\)\}/);
  // 单文件工程：确认框提供绑定开关（默认开启），bind 透传给接口。
  assert.match(page, /project_file_import_bind/);
  assert.match(page, /project_root_matches/);
  assert.match(page, /project_file_root_mismatch/);
});

test('导入结果同时展示并可打开项目资料缓存备份', () => {
  const types = read('types.ts');
  const result = types.match(/export interface ProjectFileImportResult[\s\S]*?\n\}/)?.[0] ?? '';
  assert.match(result, /assets_output_folder: string;/);
  assert.match(result, /assets_backup_folder: string;/);

  const page = read('pages', 'ProjectPage.tsx');
  const confirm = page.match(/const confirmImport = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(confirm, /assetsBackup: result\.assets_backup_folder/);
  assert.match(confirm, /project_file_import_success_assets/);
  assert.match(page, /openFolder\(fileResult\.assetsBackup\)/);
  assert.match(page, /project_file_assets_backup/);
});

test('旧数据先预览显式目录，取消或失败都不算导出成功', () => {
  const api = read('api.ts');
  for (const [fn, route] of [
    ['inspectLegacyProjectCache', 'legacy/inspect'],
    ['exportLegacyProjectFile', 'legacy/export'],
  ]) {
    const body = api.match(new RegExp(`export function ${fn}\\([\\s\\S]*?\\n\\}`))?.[0] ?? '';
    assert.match(body, new RegExp(`'/api/project/file/${route}'`));
    assert.match(body, /method: 'POST'/);
  }
  assert.match(api, /body: JSON\.stringify\(\{ folder \}\)/);
  assert.match(api, /body: JSON\.stringify\(\{ folder, path \}\)/);

  const page = read('pages', 'ProjectPage.tsx');
  const pick = page.match(/const pickLegacyCache = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(pick, /pickFolder\(/);
  assert.match(pick, /inspectLegacyProjectCache\(picked\)/);
  assert.doesNotMatch(pick, /exportLegacyProjectFile|exportProjectFile/);

  const save = page.match(/const saveLegacyCache = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(save, /if \(legacyFlight\.current\) return/);
  assert.match(save, /if \(!picked\) return/);
  const exportAt = save.indexOf('exportLegacyProjectFile(pending.cache_folder, target)');
  const clearAt = save.indexOf('setPendingLegacy(null)');
  assert.ok(exportAt > 0 && clearAt > exportAt);
  assert.doesNotMatch(save, /exportProjectFile\(/);
  assert.match(page, /onCancel=\{\(\) => \{ if \(!busy\) setPendingLegacy\(null\); \}\}/);
  assert.match(page, /onConfirm=\{busy \? undefined : \(\) => void saveLegacyCache\(pendingLegacy\)\}/);
});

test('未绑定或任务进行中时先说明原因，成功后打开工程文件所在目录', () => {
  const page = read('pages', 'ProjectPage.tsx');
  assert.match(page, /state\.saving \|\| engineBusy/);
  assert.match(page, /engine_status !== 'IDLE'/);
  const reason = page.indexOf('project_file_need_project');
  const busy = page.indexOf('project_file_busy');
  const button = page.indexOf('project_file_legacy_migrate');
  assert.ok(reason >= 0 && busy > reason && button > busy);
  assert.match(page, /openFolder\(parentFolder\(fileResult\.path\)\)/);
  assert.match(page, /source: result\.source_output_folder/);
  assert.match(page, /pendingLegacy\.output_folder/);
  assert.match(page, /pendingLegacy\.cache_folder/);
  assert.match(page, /project_file_legacy_format_sqlite/);
  assert.match(page, /project_file_legacy_next/);
  assert.match(page, /rb-project-file-actions/);
});

test('双击 .rbox 直接打开：主进程推路径，项目页接着走确认导入', () => {
  const main = fs.readFileSync(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'main', 'main.js'),
    'utf8',
  );
  assert.match(main, /project-file:open/);
  assert.match(main, /\.rbox/);
  // 启动参数与已运行实例转交两条路都要覆盖。
  assert.match(main, /sendProjectFileOpen\(projectFileFromArgv\(process\.argv\)\)/);
  assert.match(main, /app\.on\('second-instance', \(_event, argv\)/);

  const preload = fs.readFileSync(
    path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', 'main', 'preload-main.cjs'),
    'utf8',
  );
  assert.match(preload, /onProjectFileOpen: \(callback\)/);

  const app = read('App.tsx');
  assert.match(app, /onProjectFileOpen\?\.\(\(file\)/);
  assert.match(app, /navigate\('project'\)/);

  const page = read('pages', 'ProjectPage.tsx');
  assert.match(page, /incomingFile\?: string \| null/);
  assert.match(page, /beginImport\(file\)/);
});

test('工程文件文案中英文齐全', () => {
  const page = read('pages', 'ProjectPage.tsx');
  const zh = read('i18n', 'zh.ts');
  const en = read('i18n', 'en.ts');
  const keys = [...new Set(page.match(/project_file_[a-z_]+/g))];
  assert.ok(keys.length > 10);
  for (const key of keys) {
    assert.match(zh, new RegExp(`\\n  ${key}: `), `zh 缺少 ${key}`);
    assert.match(en, new RegExp(`\\n  ${key}: `), `en 缺少 ${key}`);
  }
});

test('当前工程文件面板：绑定状态可见，缺失与网盘同步都要有提示', () => {
  const api = read('api.ts');
  const bindingGet = api.match(/export function getProjectFileBinding\([\s\S]*?\n\}/)?.[0] ?? '';
  assert.match(bindingGet, /'\/api\/project\/file\/binding'/);
  assert.doesNotMatch(bindingGet, /method: 'POST'/);
  const bindingPost = api.match(/export function unbindProjectFile\([\s\S]*?\n\}/)?.[0] ?? '';
  assert.match(bindingPost, /'\/api\/project\/file\/unbind'/);
  assert.match(bindingPost, /method: 'POST'/);

  const types = read('types.ts');
  const contract = types.match(/export interface ProjectFileBinding[\s\S]*?\n\}/)?.[0] ?? '';
  assert.match(contract, /exists: boolean;/);
  assert.match(contract, /item_count: number;/);

  const page = read('pages', 'ProjectPage.tsx');
  const panel = page.match(/project_file_binding_title[\s\S]*?project_file_title/)?.[0] ?? '';
  assert.ok(panel, '缺少当前工程文件面板');
  const reload = page.match(/const reloadBinding = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(reload, /getProjectFileBinding\(\)/);
  assert.match(panel, /binding\?\.bound/);
  assert.match(panel, /project_file_binding_missing/);
  assert.match(panel, /project_file_unbind/);
  // 解除绑定必须过确认框，成功后刷新三份状态
  const unbind = page.match(/const unbindProject = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(unbind, /unbindProjectFile\(\)/);
  assert.match(unbind, /state\.reloadProject\(\), state\.reloadSettings\(\), state\.reloadTranslation\(\)/);
  assert.match(page, /void reloadBinding\(\);/);
});

test('标题栏常驻当前工程文件：绑定时显示文件名，丢失换色提示', () => {
  const app = read('App.tsx');
  assert.match(app, /state\.projectFileBinding\?\.bound/);
  assert.match(app, /className="rb-project-file"/);
  assert.match(app, /data-missing=\{binding\.exists \? undefined : 'true'\}/);
  assert.match(app, /project_file_binding_missing/);
  assert.match(app, /onClick=\{\(\) => navigate\('project'\)\}/);

  const store = read('useAppState.ts');
  assert.match(store, /projectFileBinding: ProjectFileBinding \| null;/);
  assert.match(store, /const reloadProjectFileBinding = useCallback/);
  assert.match(store, /api\.getProjectFileBinding\(\)/);
  // 项目切换事件要跟着刷新标题栏，不然会一直显示上一个 .rbox
  assert.match(store, /void reloadProjectFileBinding\(\);\s*\n\s*void Promise\.all\(\[reloadProject\(\)/);

  const page = read('pages', 'ProjectPage.tsx');
  // 保存 / 导入 / 解除绑定 / 创建 四处写操作 + 绑定后自动创建，都要刷新标题栏。
  assert.equal((page.match(/state\.reloadProjectFileBinding\(\)/g) ?? []).length, 5);

  const css = fs.readFileSync(path.join(src, 'styles', 'app.css'), 'utf8');
  assert.match(css, /\.rb-titlebar \.rb-project-file \{/);
  assert.match(css, /\.rb-titlebar \.rb-project-file\[data-missing='true'\]/);
});

test('未绑定时可一键创建工程文件，默认位置来自后端', () => {
  const api = read('api.ts');
  const body = api.match(/export function createProjectFile\([\s\S]*?\n\}/)?.[0] ?? '';
  assert.ok(body, 'createProjectFile 缺失');
  assert.match(body, /'\/api\/project\/file\/create'/);
  assert.match(body, /method: 'POST'/);

  const page = read('pages', 'ProjectPage.tsx');
  // 只有未绑定时才出现创建入口：绑定了就该走解除绑定，而不是换个文件。
  assert.match(page, /binding && !binding\.bound/);
  assert.match(page, /binding\.default_path/);
  assert.match(page, /project_file_create_hint/);
  assert.match(page, /createProjectFile\(target\)/);
  // 「另存到」走原生对话框，后缀照旧补全
  assert.match(page, /defaultPath: binding\?\.default_path \|\| `\$\{projectLabel \|\| 'project'\}\.rbox`/);

  // 自动创建开关直接写配置项，默认开启
  assert.match(page, /values\?\.project_file_auto_create !== false/);
  assert.match(page, /state\.setSetting\('project_file_auto_create', next\)/);
  // 绑定后只提示自动创建结果，失败不阻塞绑定
  assert.match(page, /project_file_auto_created/);
  assert.match(page, /project_file_auto_create_failed/);
  const bind = page.match(/const pickProject = useCallback\([\s\S]*?\n {2}\}, /)?.[0] ?? '';
  assert.match(bind, /noteAutoCreate\(info\)/);
});
