# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules
from pathlib import Path
import os
import sys

# 尝试定位项目根目录
# 1. 优先使用当前工作目录 (通常是 build.bat 运行的地方)
project_root = Path(os.getcwd())

# 2. 检查 resource 是否存在，如果不存在，则使用 spec 文件所在目录
if not (project_root / 'resource').exists():
    project_root = Path(globals().get('__file__', SPECPATH)).resolve().parent

# 3. 再次检查，如果还不存在，打印错误
resource_dir = project_root / 'resource'
if not resource_dir.exists():
    print(f"Error: Resource directory not found at {resource_dir}")
    # 尝试硬编码修正（针对您当前的目录结构）
    if (project_root / 'oldcatporject' / 'resource').exists():
        project_root = project_root / 'oldcatporject'
        resource_dir = project_root / 'resource'
        print(f"Found resource at corrected path: {resource_dir}")

version_file = project_root / 'version.txt'

print(f"Project Root: {project_root}")
print(f"Resource Dir: {resource_dir}")
print(f"Version File: {version_file}")

datas = []
for file_path in resource_dir.rglob("*"):
    if file_path.is_file():
        if file_path.name == "config.json":
            # 跳过用户配置文件，避免把个人路径打进包
            continue
        target_dir = Path("resource") / file_path.relative_to(resource_dir).parent
        datas.append((str(file_path), str(target_dir)))

# 打包时生成一份完全脱敏的配置（仅使用默认值，不拷贝本地配置）
try:
    import json, dataclasses
    sys.path.insert(0, str(project_root))
    from module.Config import Config
    sanitized_cfg = dataclasses.asdict(Config())
    # 平台列表在运行时按语言加载预置文件，不要携带本地密钥
    sanitized_cfg["platforms"] = None
    sanitized_cfg["activate_platform"] = 0
    sanitized_cfg_path = project_root / "build_sanitized_config.json"
    with open(sanitized_cfg_path, "w", encoding = "utf-8") as writer:
        json.dump(sanitized_cfg, writer, indent = 4, ensure_ascii = False)
    datas.append((str(sanitized_cfg_path), "resource"))
except Exception as e:
    print(f"Warning: failed to create sanitized config: {e}")

# 字体文件已经包含在 resource 目录中，无需单独添加
font_file = resource_dir / 'SourceHanSansLite.ttf'
if font_file.exists():
    print(f"Font included in resource: {font_file}")
else:
    print(f"Warning: builtin font not found at {font_file}")
binaries = []
hiddenimports = [
    # QtMultimedia（启动音效）
    'PyQt5.QtMultimedia',
    # base 包的所有模块
    'base.Base',
    'base.CLIManager',
    'base.LogManager',
    'base.VersionManager',
    'base.Version',
    'base.PathHelper',
    'base.BaseLanguage',
    'base.EventManager',
    'base.compat',
    # frontend 动态导入的模块
    'frontend.RenpyToolbox.DirectRpyTranslatePage',
    'frontend.RenpyToolbox.SourceTranslatePage',
    'frontend.RenpyToolbox.OneKeyTranslatePage',
    'frontend.RenpyToolbox.LocalGlossaryPage',
    'frontend.RenpyToolbox.SetDefaultLanguagePage',
    'frontend.RenpyToolbox.AddLanguageEntrancePage',
    'frontend.RenpyToolbox.TranslateEngineTab',
    'frontend.RenpyToolbox.RenpyToolboxPage',
    'frontend.TranslationPage',
    'frontend.AppFluentWindow',
    # module 相关
    'module.Engine.Translator.Translator',
    'module.Engine.Translator.TranslatorTask',
    'module.Engine.TaskRequester',
]
tmp_ret = collect_all('qfluentwidgets')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# aiohttp (部分三方库会在运行时动态使用；未完整打包可能导致 `aiohttp.ClientSession` 缺失)
try:
    tmp_ret = collect_all('aiohttp')
    datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
except Exception as e:
    print(f"Warning: failed to collect aiohttp: {e}")
hiddenimports += collect_submodules('base')
hiddenimports += collect_submodules('widget')
hiddenimports += collect_submodules('utils')
hiddenimports += collect_submodules('frontend.RenpyToolbox')
hiddenimports += collect_submodules('module.Engine')
hiddenimports += collect_submodules('module.Extract')
hiddenimports += collect_submodules('module.Renpy')

block_cipher = None

icon_file = resource_dir / "icon.ico"
if not icon_file.exists():
    icon_file = resource_dir / "icon.ico"
if icon_file.exists():
    print(f"Icon File: {icon_file}")
else:
    print(f"Warning: icon file not found under {resource_dir}")
    icon_file = None

a = Analysis(
    [str(project_root / 'app.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RenpyBox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # 临时开启控制台以便调试
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RenpyBox',
)
