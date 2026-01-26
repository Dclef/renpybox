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
# 核心第三方库 - 精确收集（避免拉入不需要的大型依赖）
third_party_packages = [
    'qfluentwidgets',    # UI 框架
    'rich',              # 日志美化
    'opencc',            # 繁简转换
    'tiktoken',          # Token 计数
    'httpx',             # HTTP 客户端（openai/anthropic 依赖）
    'openai',            # OpenAI API
    'anthropic',         # Claude API
    'translators',       # 翻译器（FastTranslator使用）
    'pygtrans',          # Google翻译（FastTranslator使用）
    'json_repair',       # JSON修复（ResponseDecoder使用）
]

# Google Gemini 需要精确指定，避免收集整个 google 命名空间
google_packages = [
    'google.generativeai',  # Gemini API 主包
    'google.genai',         # 新版 Gemini SDK
    'google.auth',          # 认证
    'google.api_core',      # API 核心
]

# 轻量级工具库 - 只收集子模块
lightweight_packages = [
    'charset_normalizer',  # 字符编码检测
    'lxml',                # XML 解析
    'bs4',                 # HTML 解析
    'openpyxl',            # Excel 处理
    'yaml',                # YAML 解析
    'pandas',              # 数据分析
    'spacy',               # NER功能
    'thinc',               # spacy依赖
]

hiddenimports = []

# 1. 核心第三方库 - 全量收集
for package in third_party_packages:
    try:
        tmp_ret = collect_all(package)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
        print(f"✓ Collected: {package}")
    except Exception as e:
        print(f"⚠ Skip {package}: {e}")

# 2. Google 包 - 精确收集子模块，避免拉入整个命名空间
for package in google_packages:
    try:
        hiddenimports += collect_submodules(package)
        print(f"✓ Collected submodules: {package}")
    except Exception as e:
        print(f"⚠ Skip {package}: {e}")

# 3. 轻量级工具库 - 只收集子模块
for package in lightweight_packages:
    try:
        hiddenimports += collect_submodules(package)
        print(f"✓ Collected submodules: {package}")
    except Exception as e:
        print(f"⚠ Skip {package}: {e}")

# 项目内部模块 - 自动收集所有子模块
internal_modules = ['base', 'widget', 'utils', 'frontend', 'module']
for mod in internal_modules:
    try:
        hiddenimports += collect_submodules(mod)
        print(f"✓ Collected submodules: {mod}")
    except Exception as e:
        print(f"⚠ Skip {mod}: {e}")

block_cipher = None

icon_file = resource_dir / "icon.ico"
if not icon_file.exists():
    icon_file = resource_dir / "icon.ico"
if icon_file.exists():
    print(f"Icon File: {icon_file}")
else:
    print(f"Warning: icon file not found under {resource_dir}")
    icon_file = None

# 排除不需要的大型依赖
excludes = [
    # NLP/ML 库
    'tensorflow',      # 深度学习
    'torch',           # PyTorch
    'transformers',    # Hugging Face
    'sklearn',         # scikit-learn
    
    # 科学计算库
    'scipy',           # 科学计算
    'matplotlib',      # 绘图
    'seaborn',         # 数据可视化
    'plotly',          # 交互式绘图
    
    # pandas可选依赖
    'pyarrow',         # Apache Arrow
    'fastparquet',     # Parquet文件
    'tables',          # HDF5
    'sqlalchemy',      # 数据库
    'xlrd',            # 旧版Excel
    'xlwt',            # 旧版Excel写入
    'odfpy',           # OpenDocument
    
    # 其他不需要的
    'tkinter',         # GUI
    'IPython',         # Jupyter
    'notebook',        # Jupyter
    'pytest',          # 测试
    'unittest',        # 测试
]

a = Analysis(
    [str(project_root / 'app.py')],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
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

# 独立更新器：使用 onefile，避免运行时依赖目标目录的 `_internal`，从而可以在应用退出后覆盖更新文件
a_updater = Analysis(
    [str(project_root / 'updater.py')],
    pathex=[str(project_root)],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz_updater = PYZ(a_updater.pure, a_updater.zipped_data, cipher=block_cipher)
updater_exe = EXE(
    pyz_updater,
    a_updater.scripts,
    a_updater.binaries,
    a_updater.zipfiles,
    a_updater.datas,
    name='RenpyBoxUpdater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file else None,
)
coll = COLLECT(
    exe,
    updater_exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='RenpyBox',
)
