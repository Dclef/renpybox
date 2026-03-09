# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_all, collect_submodules, collect_data_files
from pathlib import Path
import importlib.util
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

# 收集需要作为脚本运行的 .py 文件（不是模块导入的）
# PyInstaller 6.x: datas 目标路径是相对于 _internal 目录的
script_files = [
    ('module/Tool/android_build_runner.py', 'module/Tool'),
    ('module/Tool/rpatool_core.py', 'module/Tool'),
]
for src, dest in script_files:
    src_path = project_root / src
    if src_path.exists():
        datas.append((str(src_path), dest))
        print(f"[DATA] Script: {src} -> _internal/{dest}")

binaries = []
hiddenimports = []

# -------------------------------------------------------------------
# 通用包数据目录补全工具
# -------------------------------------------------------------------

def _pkg_root(pkg_name):
    """获取包安装根目录，失败返回 None"""
    try:
        spec = importlib.util.find_spec(pkg_name)
        if spec and spec.origin:
            return Path(spec.origin).parent
    except Exception:
        pass
    return None

def _add_dir(datas_list, src_dir, dest):
    """将整个目录追加进 datas（目录不存在则打印警告跳过）"""
    src_dir = Path(src_dir)
    if src_dir.exists():
        datas_list.append((str(src_dir), dest))
        print(f"[DATA+] {src_dir} -> _internal/{dest}")
    else:
        print(f"[WARN ] not found, skip: {src_dir}")

# -------------------------------------------------------------------
# 收集第三方依赖
# -------------------------------------------------------------------

# 全量收集（datas + binaries + hiddenimports）
full_collect_packages = [
    'qfluentwidgets', 'rich', 'opencc', 'tiktoken', 'httpx',
    'openai', 'anthropic', 'translators', 'pygtrans', 'json_repair'
]

# 仅收集子模块（减小体积）
submodule_packages = [
    'google.generativeai', 'google.genai', 'google.auth', 'google.api_core',
    'chardet', 'lxml', 'bs4', 'openpyxl', 'yaml',
    'pandas', 'spacy', 'thinc', 'psutil'
]

# 项目内部模块
internal_modules = ['base', 'widget', 'utils', 'frontend', 'module']

# -------------------------------------------------------------------
# 已知 collect_all 无法完整收集数据文件的包，在此手动补充
#
# 格式：包名 -> [(相对于包根的子路径, _internal 中的目标路径), ...]
#   子路径为空字符串 '' 表示包根目录本身
#
# 新增问题时只需在此 dict 中追加，无需修改其他代码。
# -------------------------------------------------------------------
MANUAL_DATA_DIRS = {
    # opencc-python-reimplemented：JSON 转换配置存放在 cLib/ 下，collect_all 会遗漏
    'opencc': [
        ('cLib', 'opencc/cLib'),
    ],
    # tiktoken_ext 是独立命名空间包，collect_all('tiktoken') 不会一并处理
    'tiktoken': [
        ('',  'tiktoken'),
    ],
    # spacy 的语言数据（lang/*/）通过 collect_all 有时不完整
    'spacy': [
        ('lang', 'spacy/lang'),
    ],
    # openpyxl 内嵌 XML 模板，collect_data_files 有时遗漏
    'openpyxl': [
        ('templates', 'openpyxl/templates'),
        ('reader',    'openpyxl/reader'),
    ],
}

# -------------------------------------------------------------------
# 打包策略说明
# requests 运行时会动态导入字符集检测库，PyInstaller 默认不一定能自动识别。
# 这里显式收集 chardet 作为兜底，并避免额外手动打包 charset_normalizer 的 mypyc 扩展，
# 以规避冻结环境下 __mypyc 缺失导致的启动崩溃。

# 执行收集
# -------------------------------------------------------------------

for pkg in full_collect_packages:
    try:
        tmp = collect_all(pkg)
        datas += tmp[0]; binaries += tmp[1]; hiddenimports += tmp[2]
        print(f"[OK] collect_all: {pkg}")
    except Exception as e:
        print(f"[SKIP] collect_all {pkg}: {e}")

for pkg in submodule_packages + internal_modules:
    try:
        hiddenimports += collect_submodules(pkg)
        print(f"[OK] collect_submodules: {pkg}")
    except Exception as e:
        print(f"[SKIP] collect_submodules {pkg}: {e}")

# 手动补充已知问题包的数据目录（幂等：PyInstaller 会自动去重）
for pkg, entries in MANUAL_DATA_DIRS.items():
    pkg_root = _pkg_root(pkg)
    if pkg_root is None:
        print(f"[SKIP] manual data: {pkg} not installed / not found")
        continue
    for sub, dest in entries:
        _add_dir(datas, pkg_root / sub if sub else pkg_root, dest)

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
