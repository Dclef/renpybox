# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path
import os
import sys

# 定位项目根目录
project_root = Path(os.getcwd())
if not (project_root / 'resource').exists():
    project_root = Path(SPECPATH)
    
resource_dir = project_root / 'resource'
print(f"Project Root: {project_root}")
print(f"Resource Dir: {resource_dir}")

# 收集 resource 目录（跳过 config.json）
datas = []
for file_path in resource_dir.rglob("*"):
    if file_path.is_file() and file_path.name != "config.json":
        target_dir = Path("resource") / file_path.relative_to(resource_dir).parent
        datas.append((str(file_path), str(target_dir)))

# 生成脱敏的默认配置
try:
    import json, dataclasses
    sys.path.insert(0, str(project_root))
    from module.Config import Config
    sanitized_cfg = dataclasses.asdict(Config())
    sanitized_cfg["platforms"] = None
    sanitized_cfg["activate_platform"] = 0
    sanitized_cfg_path = project_root / "build_sanitized_config.json"
    with open(sanitized_cfg_path, "w", encoding="utf-8") as f:
        json.dump(sanitized_cfg, f, indent=4, ensure_ascii=False)
    datas.append((str(sanitized_cfg_path), "resource"))
except Exception as e:
    print(f"Warning: failed to create sanitized config: {e}")

binaries = []
hiddenimports = []

# 收集第三方依赖
# 全量收集（包含二进制文件）
full_collect_packages = [
    'qfluentwidgets', 'rich', 'opencc', 'tiktoken', 'httpx',
    'openai', 'anthropic', 'translators', 'pygtrans', 'json_repair'
]

# 仅收集子模块（减小体积）
submodule_packages = [
    'google.generativeai', 'google.genai', 'google.auth', 'google.api_core',
    'charset_normalizer', 'lxml', 'bs4', 'openpyxl', 'yaml',
    'pandas', 'spacy', 'thinc', 'psutil'
]

# 项目内部模块
internal_modules = ['base', 'widget', 'utils', 'frontend', 'module']

# 执行收集
for pkg in full_collect_packages:
    try:
        tmp = collect_all(pkg)
        datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]
        print(f"[OK] {pkg}")
    except Exception as e:
        print(f"[SKIP] {pkg}: {e}")

for pkg in submodule_packages + internal_modules:
    try:
        hiddenimports += collect_submodules(pkg)
        print(f"[OK] {pkg}")
    except Exception as e:
        print(f"[SKIP] {pkg}: {e}")

# 图标和排除列表
icon_file = resource_dir / "icon.ico"
icon_file = str(icon_file) if icon_file.exists() else None

excludes = [
    'tensorflow', 'torch', 'transformers', 'sklearn',  # ML
    'scipy', 'matplotlib', 'seaborn', 'plotly',  # 科学计算
    'pyarrow', 'fastparquet', 'tables', 'sqlalchemy',  # pandas可选依赖
    'xlrd', 'xlwt', 'odfpy',  # 旧版Excel
    'pytest', 'unittest', 'test', '_pytest', 'tests',  # 测试
    'tkinter', 'IPython', 'notebook'  # 其他
]

block_cipher = None

# 主程序分析
a = Analysis(
    [str(project_root / 'app.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=excludes,
    cipher=block_cipher,
)

# 独立更新器分析
a_updater = Analysis(
    [str(project_root / 'updater.py')],
    pathex=[str(project_root)],
    cipher=block_cipher,
)

# 主程序 EXE
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='RenpyBox',
    upx=True,
    console=True,
    icon=icon_file,
)

# 更新器 EXE（单文件模式）
pyz_updater = PYZ(a_updater.pure, a_updater.zipped_data, cipher=block_cipher)
updater_exe = EXE(
    pyz_updater, a_updater.scripts,
    a_updater.binaries, a_updater.zipfiles, a_updater.datas,
    name='RenpyBoxUpdater',
    upx=True,
    console=False,
    icon=icon_file,
)

# 收集所有文件
coll = COLLECT(
    exe, updater_exe,
    a.binaries, a.zipfiles, a.datas,
    upx=True,
    name='RenpyBox',
)
