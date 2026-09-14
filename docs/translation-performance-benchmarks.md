# 大文本性能实验附录

日期：2026-09-14。对应 [调查与改造方案](translation-extraction-replace-performance-plan.md)。

第 1–7 节保留历史代码基线 `0fabe18` 的实验和数值，**不代表本轮优化后的实现**。旧 UI 实验使用同步方法的替身，不能直接运行在新的后台扫描入口；要重现历史结果需使用独立的基线 checkout。优化后的运行命令和复测结果见第 9 节。运行位置为仓库根目录，命令使用 PowerShell，依赖项目现有 Python 环境。

- 不访问翻译 API，不启动游戏，不写游戏目录或配置。
- 扫描和 UI 实验仅在系统临时目录构造夹具，结束后清理；生产代码只在内存中被测试调用。
- 首次导入、文件系统缓存、杀毒扫描和机器负载会影响绝对耗时。优先比较调用次数、规则匹配结果、输出一致性，再比较耗时。
- 历史实验中的“原型”用于证明改造方向；当前前缀树、预编译、按文件批处理和惰性分块已经进入产品实现，不能再把旧原型数值当作当前代码测量。
- 测试可能产生项目正常日志与 Python 缓存；不会修改受版本控制的程序文件。

## 1. 环境与现有回归

```powershell
git rev-parse --short HEAD
python -c "import platform; print(platform.python_version()); print(platform.platform())"
python -m pytest -q tests/module/test_old_new_replace_optimization.py tests/module/test_renpy_extract.py
python -m pytest -q tests/module/engine/translator/test_translation_stop_responsiveness.py tests/module/test_task_requester.py tests/module/cache/test_translation_cache_foundation.py
```

本轮环境：3.10.11，Windows-10-10.0.26200-SP0。两组回归分别 102 和 53 项通过，已有 scipy/qfluentwidgets 弃用警告。

## 2. 实际 10 行配置能装多少条

输入为 1,000 个同文件、单行条目，长度分别为 10/30/40/50 个 `word`。使用生产 `get_token_count`，不模拟分块。

```powershell
@'
import json, statistics, time
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheItem import CacheItem

rows = []
for words in (10, 30, 40, 50):
    text = ('word ' * words).strip()
    items = [CacheItem(src=text, file_path='scene.rpy') for _ in range(1000)]
    manager = CacheManager(service=False)
    manager.items = items
    token_count = items[0].get_token_count()
    start = time.perf_counter()
    chunks, contexts = manager.generate_item_chunks(10, 0)
    rows.append({
        'source_tokens_per_item': token_count,
        'chunks': len(chunks),
        'median_items_per_batch': statistics.median(map(len, chunks)),
        'mean_items_per_batch': round(1000 / len(chunks), 3),
        'elapsed_ms': round((time.perf_counter() - start) * 1000, 3),
    })
print(json.dumps(rows, indent=2))
'@ | python -
```

本轮批次数为 100/200/250/334，中位条数为 10/5/4/3。

## 3. 上文回扫访问次数

固定 token=1 仅为隔离上文查找，使用当前生产分块方法。数据不含可接受的行尾标点，前缀会反复回扫。该结果只适用于启用参考上文的场景。

这里的生产入口指历史基线。当前翻译调度使用 `iter_item_chunks`；下面的 `generate_item_chunks` 保留旧算法，其平方级访问不能作为当前线上调度的测量结果。

```powershell
@'
import time
from unittest.mock import patch
from module.Cache.CacheManager import CacheManager
from module.Cache.CacheItem import CacheItem

for n in (1000, 2000, 4000):
    items = [CacheItem(src='line %d' % i, file_path='a.rpy') for i in range(n)]
    for item in items:
        item.get_token_count = lambda: 1
    manager = CacheManager(service=False)
    manager.items = items
    calls = [0]
    original = CacheItem.get_src
    def counted(item):
        calls[0] += 1
        return original(item)
    with patch.object(CacheItem, 'get_src', counted):
        start = time.perf_counter()
        manager.generate_item_chunks(10, 3)
        seconds = time.perf_counter() - start
    print(n, calls[0], round(seconds, 4))
'@ | python -
```

本轮调用次数：50,500 / 201,000 / 802,000。计数比秒数更稳定。

## 4. Hook 缓存阈值与预编译原型

直接调用当前 `render_replace_script`，只把 Ren'Py 块头转成 Python 测试块，在内存执行生成函数。并未加载用户脚本。`re._cache` 是本实验使用的 CPython 私有观察接口，不应成为产品依赖。

```powershell
@'
import json, re, time
from types import SimpleNamespace
from unittest.mock import patch
from module.Extract.ReplaceGenerator import (
    render_replace_script, _build_interpolated_replace_rule,
)

results = []
for dynamic, counts in [(False, [1000, 10000]), (True, [100, 500, 513, 1000, 3000])]:
    for n in counts:
        pairs = [
            (
                ('Field%06d: [value]' if dynamic else 'Field%06d: fixed value') % i,
                ('Value%06d: [value]' if dynamic else 'Value%06d: translated') % i,
            )
            for i in range(n)
        ]
        script = render_replace_script(pairs).replace(
            'translate chinese python:', 'if True:'
        )
        namespace = {'config': SimpleNamespace(replace_text=None)}
        exec(compile(script, '<generated-hook>', 'exec'), namespace)
        fn = namespace['config'].replace_text
        probe = 'A completely unrelated rendered text fragment.'
        re.purge()
        fn(probe)
        misses = [0]
        original_compile = re._compile
        def counted(pattern, flags=0):
            if (type(pattern), pattern, flags) not in re._cache:
                misses[0] += 1
            return original_compile(pattern, flags)
        with patch.object(re, '_compile', counted):
            fn(probe)
        start = time.perf_counter()
        for _ in range(10):
            assert fn(probe) == probe
        row = {
            'dynamic': dynamic,
            'rules': n,
            'warm_miss_ms': round((time.perf_counter() - start) * 1000 / 10, 4),
            'compile_cache_misses_per_call': misses[0],
        }
        if dynamic:
            compiled = []
            for source, target in pairs:
                pattern, replacement = _build_interpolated_replace_rule(source, target)
                compiled.append((re.compile(pattern), replacement, source.split('[')[0]))
            def prototype(text):
                for pattern, replacement, anchor in compiled:
                    if anchor in text:
                        text = pattern.sub(replacement, text)
                return text
            start = time.perf_counter()
            for _ in range(10):
                assert prototype(probe) == probe
            row['precompiled_anchor_prototype_ms'] = round(
                (time.perf_counter() - start) * 1000 / 10, 4
            )
            match = 'Field%06d: 27' % (n - 1)
            assert prototype(match) == fn(match) == 'Value%06d: 27' % (n - 1)
        results.append(row)
print(json.dumps(results, indent=2))
'@ | python -
```

本轮：500 条缓存未命中为 0；513 条为 513；3,000 条为 3,000。3,000 条的未命中均值由 147.4965 ms 降到原型的 0.1386 ms。这不是对复杂插值、多次命中或最终索引性能的全面验证。

## 5. 重复扫描与缓存原型的输出一致性

生产方法按候选调用两个辅助方法。原型只替换这两个方法的查询实现，仍由生产方法追加 TL；对每种规模断言结果完全一致。读取字节以返回文本重新编码为 UTF-8 计数，不代表物理磁盘流量。

```powershell
@'
import json, time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from module.Extract.UnifiedExtractor import UnifiedExtractor
from module.Renpy.renpy_tl_core import scan_quoted_literals

results = []
for n in (100, 300, 1000):
    with TemporaryDirectory(prefix='renpybox-scan-audit-') as temp:
        root = Path(temp)
        source = root / 'game' / 'scene.rpy'
        source.parent.mkdir()
        texts = ['Visible status item %06d' % i for i in range(n)]
        source.write_text(
            'screen inventory():\n' +
            ''.join('    text ' + json.dumps(text) + '\n' for text in texts),
            encoding='utf8',
        )
        outputs = []
        for optimized in (False, True):
            tl = root / 'game' / 'tl' / ('cached' if optimized else 'baseline')
            tl.mkdir(parents=True)
            target = tl / 'scene.rpy'
            target.write_text('', encoding='utf8')
            extractor = UnifiedExtractor()
            read_text = Path.read_text
            counters = {'source_reads': 0, 'tl_reads': 0, 'read_bytes': 0}
            def counted(path, *args, **kwargs):
                value = read_text(path, *args, **kwargs)
                if path == source or path == target:
                    counters['read_bytes'] += len(value.encode('utf8'))
                    counters['source_reads' if path == source else 'tl_reads'] += 1
                return value
            original_blocks = extractor._get_file_block_originals
            blocks_cache, locations = {}, {}
            def indexed_blocks(path):
                if path not in blocks_cache:
                    blocks_cache[path] = original_blocks(path)
                return blocks_cache[path]
            def indexed_lines(path, text):
                if path not in locations:
                    index = {}
                    for number, line in enumerate(
                        path.read_text(encoding='utf8').splitlines(), 1
                    ):
                        for literal in scan_quoted_literals(line):
                            index.setdefault(literal.value, number)
                    locations[path] = index
                return locations[path].get(text)
            if optimized:
                extractor._get_file_block_originals = indexed_blocks
                extractor._find_source_text_line = indexed_lines
            with patch.object(Path, 'read_text', counted):
                start = time.perf_counter()
                added = extractor._append_static_supplement_entries(
                    root, tl, 'chinese',
                    candidates={text: 'scene.rpy' for text in texts},
                    menu_candidates=set(),
                )
                elapsed = time.perf_counter() - start
            outputs.append(target.read_text(encoding='utf8'))
            results.append({
                'candidates': n, 'cached_read_prototype': optimized,
                'added': added, 'seconds': round(elapsed, 4), **counters,
            })
        assert outputs[0] == outputs[1]
print(json.dumps(results, indent=2))
'@ | python -
```

本轮 1,000 条：源文件读取 1,000 → 1，TL 读取 1,002 → 3，读取文本字节 116,340,388 → 38,020，耗时 5.8301 → 0.6665 秒。

## 6. 已有官方对白仍产生 replace-only

构造官方格式的 TL 夹具，不运行官方引擎；补抽、源码扫描、去重均执行当前生产代码。Python 版本识别被固定为 Python 3，避免要求临时目录存在游戏解释器。

```powershell
@'
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from module.Renpy import renpy_extract as rx

with TemporaryDirectory(prefix='renpybox-coverage-audit-') as temp:
    root = Path(temp)
    tl = root / 'game' / 'tl' / 'chinese'
    tl.mkdir(parents=True)
    source = root / 'game' / 'scene.rpy'
    target = tl / 'scene.rpy'
    official = (
        'translate chinese start_abc123:\n\n'
        '    # "Already extracted dialogue."\n'
        '    "Already extracted dialogue."\n'
    )
    for has_menu in (True, False):
        code = 'label start:\n    "Already extracted dialogue."\n'
        if has_menu:
            code += (
                '    menu:\n        "Already extracted dialogue.":\n'
                '            pass\n'
            )
        source.write_text(code + '    return\n', encoding='utf8')
        target.write_text(official, encoding='utf8')
        with patch.object(rx, 'is_python2_from_game_dir', return_value=False):
            rx.ExtractAllFilesInDir(str(tl), True, 4, False, True)
        result = target.read_text(encoding='utf8')
        print(json.dumps({
            'same_text_menu_exists': has_menu,
            'replace_only_markers': result.count('# renpybox: replace-only'),
            'repeated_old': result.count('old "Already extracted dialogue."'),
        }))
'@ | python -
```

本轮两个场景均新增 1 条。没有菜单的场景证明冗余；有菜单的场景说明不能把同文 strings 全删。

## 7. 一键 UI 同步扫描与 Qt 心跳

调用实际 `_check_old_translation`，替换显示控件为最小对象以隔离目录扫描。在同一 UI 回调中排一个零延时 QTimer，然后检查生产方法返回前 timer 是否执行。这里没有模拟慢磁盘或人为 sleep。

```powershell
@'
import json, os, time
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer
from frontend.RenpyToolbox.OneKeyTranslatePage import YiJianFanyiPage

app = QApplication.instance() or QApplication([])
class Widget:
    def setText(self, *args): pass
    def setVisible(self, *args): pass
    def setChecked(self, *args): pass

rows = []
for n in (1000, 5000):
    with TemporaryDirectory(prefix='renpybox-onekey-scan-') as temp:
        root = Path(temp)
        tl = root / 'game' / 'tl' / 'chinese'
        for index in range(n):
            directory = tl / ('chapter%03d' % (index // 100))
            directory.mkdir(parents=True, exist_ok=True)
            (directory / ('line%05d.rpy' % index)).touch()
        page = SimpleNamespace(
            tl_folder_edit=SimpleNamespace(text=lambda: 'chinese'),
            old_trans_title=Widget(), old_trans_desc=Widget(),
            old_translation_card=Widget(), incremental_rb=Widget(),
            full_extract_rb=Widget(), skip_extract_btn=Widget(),
        )
        state = {'heartbeat': False}
        def run():
            QTimer.singleShot(0, lambda: state.update(heartbeat=True))
            start = time.perf_counter()
            YiJianFanyiPage._check_old_translation(page, str(root))
            rows.append({
                'files': n,
                'callback_ms': round((time.perf_counter() - start) * 1000, 3),
                'heartbeat_before_return': state['heartbeat'],
                'detected_translation': page.has_old_translation,
            })
            QTimer.singleShot(0, app.quit)
        QTimer.singleShot(0, run)
        app.exec_()
print(json.dumps(rows, indent=2))
'@ | python -
```

本轮 1,000/5,000 文件为 23.648/128.581 ms，回调返回前 heartbeat 均为 false。证明该同步方法占用事件循环；没有证明真实游戏会因此永久卡死。

## 8. 仍需外部与复杂输入验收

- 用户问题游戏的同存档、同页面运行对照及调用栈采集。
- 真实翻译 API 的首 token、响应完成、重试、配额及有效吞吐测量。
- 完整覆盖率、真实 Ren'Py 分片加载和语言切换；合成夹具的失败恢复和部分复杂模板测试不能代替实际游戏。

以上缺少对应游戏和当次网络数据，不能用合成测试替代后直接写“用户卡死已解决”。

## 9. 当前工作区复测（2026-09-14）

环境仍为 Windows / Python 3.10.11，代码为 `0fabe18` 加本轮性能优化。以下运行均未调用 API。耗时为单机观测，规则数量、输出和读取次数比绝对毫秒数更适合回归判断。

### 9.1 当前惰性入口与旧方法

| 条目数 | 旧方法 get_src 次数 | 当前 iter_item_chunks 次数 | 旧方法耗时 | 当前入口耗时 |
| ---: | ---: | ---: | ---: | ---: |
| 1,000 | 50,500 | 2,000 | 64.211 ms | 2.190 ms |
| 2,000 | 201,000 | 4,000 | 265.651 ms | 6.637 ms |
| 4,000 | 802,000 | 8,000 | 1,026.145 ms | 11.386 ms |

输入为无标点的短标签，每项固定 1 token、每批 10 行、上文 3 条。两种方法均分别产生 100/200/400 批。当前生产调度走右侧入口；旧方法仍供兼容调用。

```powershell
@'
import time
from unittest.mock import patch
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
for n in (1000, 2000, 4000):
    for method in ('generate_item_chunks', 'iter_item_chunks'):
        manager = CacheManager(service=False)
        manager.items = [CacheItem(src='line %d' % i, file_path='a.rpy') for i in range(n)]
        for item in manager.items:
            item.get_token_count = lambda: 1
        calls = [0]
        original = CacheItem.get_src
        def counted(item):
            calls[0] += 1
            return original(item)
        with patch.object(CacheItem, 'get_src', counted):
            start = time.perf_counter()
            if method == 'iter_item_chunks':
                count = sum(1 for _ in manager.iter_item_chunks(10, 3))
            else:
                count = len(manager.generate_item_chunks(10, 3)[0])
            elapsed_ms = (time.perf_counter() - start) * 1000
        print(n, method, count, calls[0], round(elapsed_ms, 3))
'@ | python -
```

### 9.2 独立预算对装批的影响

使用生产 token 计数及 `iter_item_chunks`：1,000 个同文件单行项，每项 40 个 `word`，本机每项 40 token。这个夹具隔离分块，不执行去重预处理或翻译 API。

| 最大行数 | 源文 token 预算 | 批数 | 平均条/批 |
| ---: | ---: | ---: | ---: |
| 10 | 0，兼容旧推导得到 160 | 250 | 4 |
| 10 | 1,024 | 100 | 10 |
| 20 | 1,024 | 50 | 20 |
| 40 | 2,048 | 25 | 40 |

当前“均衡吞吐”按钮使用第三行。旧配置读取后预算为 0，保留原行为；全新默认源文预算为 1,024、行数仍为 10。选中均衡档后才把行数设为 20。输出预算自动维持后端默认值，成功项、占位符和响应协议检查保持有效。

250 → 50 是分块数量减少 80%，不是实际翻译提速五倍的证明。更长响应的延迟、格式/占位符失败和有效条/分钟仍需真实 API 对照；40 行仅为试验档，未设为默认。

```powershell
@'
from module.Cache.CacheItem import CacheItem
from module.Cache.CacheManager import CacheManager
for lines, budget in ((10, 0), (10, 1024), (20, 1024), (40, 2048)):
    manager = CacheManager(service=False)
    manager.items = [CacheItem(src=('word ' * 40).strip(), file_path='scene.rpy') for _ in range(1000)]
    chunks = list(manager.iter_item_chunks(lines, 0, source_token_limit=budget))
    print(lines, budget, len(chunks), 1000 / len(chunks), manager.items[0].get_token_count())
'@ | python -
```

### 9.3 当前 Hook 的变化输入未命中

规则为独立 `Field000000: [value]` 前缀；100 次调用每次换一个无关文本，避免只测结果缓存。另断言最后一条规则命中并保留插值值。计时不包含初始化。

| 动态规则数 | 变化输入未命中均值 | P95 | 调用期间 re.compile 次数 |
| ---: | ---: | ---: | ---: |
| 500 | 0.0029 ms | 0.0036 ms | 0 |
| 513 | 0.0028 ms | 0.0033 ms | 0 |
| 1,000 | 0.0028 ms | 0.0039 ms | 0 |
| 10,000 | 0.0050 ms | 0.0061 ms | 0 |

10,000 条的渲染、Python 编译和初始化合计本轮约 784 ms；这不是实际 Ren'Py 启动时间。无关前缀输入只能验证候选排除，不能代表共享锚点、长值或复杂多插值的最坏耗时。

```powershell
@'
import re, time
from types import SimpleNamespace
from unittest.mock import patch
from module.Extract.ReplaceGenerator import render_replace_script
for n in (500, 513, 1000, 10000):
    pairs = [('Field%06d: [value]' % i, 'Value%06d: [value]' % i) for i in range(n)]
    namespace = {'config': SimpleNamespace(replace_text=None)}
    exec(render_replace_script(pairs).replace('translate chinese python:', 'if True:'), namespace)
    hook = namespace['config'].replace_text
    timings = []
    with patch.object(re, 'compile', wraps=re.compile) as compilations:
        for i in range(100):
            probe = 'Unrelated rendered fragment %d.' % i
            start = time.perf_counter()
            assert hook(probe) == probe
            timings.append((time.perf_counter() - start) * 1000)
        assert hook('Field%06d: 27' % (n - 1)) == 'Value%06d: 27' % (n - 1)
    print(n, sum(timings) / len(timings), sorted(timings)[94], compilations.call_count)
'@ | python -
```

### 9.4 UI、预算和失败恢复回归

`test_onekey_file_scans.py` 使用受控后台等待验证：扫描未完成时 Qt timer 仍执行；计数保留全量/增量选择；清空路径、换语言或项目后不使用旧结果；应用枚举可取消和防重入。它不提供磁盘速度或真实 UI P95。

`test_replace_shard_write.py` 注入分片/入口/删除失败，验证旧 Hook 仍可执行，成功后只清理本工具的分片。预算回归覆盖旧配置、设置按钮、文件边界、完整提示的已知窗口检查及各后端输出参数。

```powershell
python -m pytest -q tests/frontend/test_onekey_file_scans.py tests/module/test_replace_shard_write.py tests/module/test_replace_runtime_performance.py tests/module/test_extraction_performance_regressions.py
python -m pytest -q tests/module/test_translation_batch_budgets.py tests/module/test_translation_budget_config.py tests/frontend/setting/test_basic_settings_budgets.py tests/module/test_token_estimator.py tests/module/engine/translator
```

完整验证结果记录在主文档第 9.4 节。未运行真实 API 和实际游戏。
