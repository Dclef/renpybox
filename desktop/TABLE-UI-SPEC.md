# RenpyBox Table UI 设计规范与组件文档

本规范详细记录了 RenpyBox 在从原生 PyQt + QFluentWidgets（`TableWidget`）迁移至现代化桌面端（Electron + React + TypeScript）过程中，关于数据表格（Table UI）的视觉设计语言、交互体系、架构演进与开发复用指南。

---

## 一、背景与设计理念

### 1.1 核心诉求
在 Ren'Py 游戏本地化与 AI 翻译工作流中，表格是承载数据密度最高、使用最频繁的组件：
- **实时翻译流水**：实时展示当前高并发翻译的文本对、耗时、时间戳，需要极高的秩序感与动态反馈。
- **平行校对台**：双语长文本对照、行状态辨识、在线快速编辑打磨，需要舒适的呼吸感行高和清晰的交互热区。
- **项目术语表**：专有名词提取与候选审核，需要紧凑高效的编辑排版。

### 1.2 设计哲学：“神似原生，质感超越”
- **神似原生（DNA Alignment）**：严格继承 Windows 11 / WinUI 3 与 QFluentWidgets 的设计精髓，包括安静克制的中性背景、圆角卡片、精确到 3.5px 的左侧 Accent Pill 状态条、以及语义一致的状态指示体系。
- **超越原生（Modern Elevation）**：借助现代 Web 与 CSS 标准能力，剔除旧原生表格呆板、厚重、纯色斑马纹断层等历史问题，引入毛玻璃吸顶表头（Acrylic Header）、双层微光投影（Ambient Shadow）、悬停微交互、等宽排版（Tabular Nums）与平滑动效。

---

## 二、视觉设计系统规范

### 2.1 表面层级与微光阴影（Surfaces & Elevation）

| 元素 | 浅色主题（LIGHT） | 深色主题（DARK） | 视觉效果 |
|---|---|---|---|
| **外层容器** | `#FFFFFF`（`--rb-surface`） | `#192128`（`--rb-surface`） | 12px 圆角，外带 `0 0 0 1px` 微弱描边与多级柔和弥散阴影 |
| **吸顶表头** | `color-mix(var(--rb-surface-subtle) 95%, var(--rb-surface))` | `color-mix(var(--rb-surface-subtle) 95%, var(--rb-surface))` | 12px 亚克力磨砂毛玻璃（`backdrop-filter: blur(12px)`），用户滚动时内容优雅穿行于下方 |
| **行悬停态** | `#EAF0F2`（`--rb-surface-hover`） | `#232E37`（`--rb-surface-hover`） | `cubic-bezier(0, 0, 0, 1)` 140ms 平滑高亮过渡 |
| **行选中态** | `#E4F2ED`（`--rb-accent-surface`） | `#193A34`（`--rb-accent-surface`） | 浅主题底色，左侧点亮 3.5px 宽、上下内缩 6px 的胶囊状 Accent 指示条 |

### 2.2 状态胶囊系统（Status Badges）
在校对台等数据视图中，摒弃生硬的文字状态，采用 WinUI 3 风格的带微光小圆点的胶囊指示牌：

```
+---------------------------------------+
|  ● 已翻译 (TRANSLATED)                |  -> 浅绿底 + 翠绿文字 + 5px 状态圆点
|  ● 已润色 (POLISHED)                  |  -> 柔和淡青底 + 信息蓝文字
|  ● 已有译文 (TRANSLATED_IN_PAST)      |  -> 淡紫底 + 主题紫蓝文字
|  ● 待翻译 (UNTRANSLATED)              |  -> 暖橙底 + 警告橙文字
+---------------------------------------+
```

### 2.3 文本与数字排版体系
1. **等宽数字（Tabular Figures）**：所有时间戳、行号、数字列显式开启 `font-variant-numeric: tabular-nums`，消除不同字符宽度造成的纵向抖动。
2. **代码级行号徽标**：采用 `Cascadia Code` / Consolas 字体，外加单像素边框与微背景色，形成标准规整的微标。
3. **双语内容阅读呼吸感**：
   - 原文区域：采用类似代码块与引言块的 Slate 容器，左侧带有 2.5px 装饰线，区分度高且不抢视觉焦点。
   - 译文区域：作为用户关注重心，采用纯净背景，悬停时触发微卡片边框高亮与阴影上浮。

---

## 三、组件架构与复用

### 3.1 核心 React 组件列表

组件封装位于 [desktop/renderer/src/ui.tsx](desktop/renderer/src/ui.tsx)：

- **`<Table>`**：表格根容器，支持配置外框卡片、紧凑/宽松模式、可选轻量斑马纹。
- **`<TableHead>`**：表头容器，自动注入吸顶与毛玻璃滤镜。
- **`<TableBody>`**：表格数据体。
- **`<TableRow>`**：数据行，支持 `selected` 属性、点击选择回调、悬停过渡。
- **`<TableHeaderCell>`**：表头单元格，支持 `align`（左/中/右）、`width`、以及 `tag` / `tagAccent` 语言或类型微标签。
- **`<TableCell>`**：数据单元格，支持 `time`（时间列）、`num`（数字对齐）、`mono`（等宽代码）、`muted`（弱化文本）、`nowrap` 等快捷语义属性。

### 3.2 使用示例

```tsx
import {
  Table,
  TableHead,
  TableBody,
  TableRow,
  TableHeaderCell,
  TableCell,
} from '../ui';

export function ExampleTable() {
  const [selectedId, setSelectedId] = useState<number | null>(1);

  return (
    <Table container>
      <TableHead>
        <TableRow>
          <TableHeaderCell width={120}>时间</TableHeaderCell>
          <TableHeaderCell tag="EN">原文</TableHeaderCell>
          <TableHeaderCell tag="ZH" tagAccent>译文</TableHeaderCell>
          <TableHeaderCell align="right" width={80}>字数</TableHeaderCell>
        </TableRow>
      </TableHead>
      <TableBody>
        <TableRow
          selected={selectedId === 1}
          onClick={() => setSelectedId(1)}
        >
          <TableCell time>14:28:05</TableCell>
          <TableCell>Hello, how are you today?</TableCell>
          <TableCell>你好，今天过得怎么样？</TableCell>
          <TableCell num>26</TableCell>
        </TableRow>
      </TableBody>
    </Table>
  );
}
```

---

## 四、主要落地场景

### 4.1 实时翻译流水卡片（[desktop/renderer/src/pages/TranslationPage.tsx](desktop/renderer/src/pages/TranslationPage.tsx)）
- **动态呼吸感**：在翻译任务运行中，最新吐出的一条流水（`index === 0`）带有 `data-latest="true"` 属性，左侧自动激发主题色微光指示条。
- **表头双语标签**：原文与译文表头内置 `table-header-tag` 胶囊，直观展示源语言与目标语言方向。
- **独立时间微标**：采用 `feed-time-wrap`，时间规整等宽排列。

### 4.2 平行校对台（[desktop/renderer/src/pages/ProofreadingPage.tsx](desktop/renderer/src/pages/ProofreadingPage.tsx)）
- **快捷复制交互（Hover-to-Copy）**：
  - 鼠标悬停在原文或译文区域时，右上角浮现微缩复制按钮。
  - 点击后即时切换为对勾图标（`IconCheck`），1.5 秒后平滑复原，为对照查阅词典提供极致便利。
- **行内打磨激活态**：
  - 译文单元格悬停时，右上角滑入带有铅笔图标的「编辑」胶囊徽标。
  - 点击后弹出居中打磨编辑器，保持上下文聚焦。
- **多行选择与批量替换**：
  - 支持全选与复选框勾选，行选中时激活 WinUI 3 经典的左侧 Accent Pill 条，与批量替换弹窗无缝联动。

---

## 五、对比分析：原生 PyQt 表格 vs 现代 Web 表格

| 特性 | 旧原生 PyQt (QTableWidget) | 现代 Web (React + CSS Tokens) |
|---|---|---|
| **表头固定与毛玻璃** | 仅支持固定行，背景生硬纯色 | 原生 CSS `sticky` + `backdrop-filter: blur(12px)`，透亮通透 |
| **行选中状态** | 整行变为强刺眼单色高亮，易遮盖文字细节 | 左侧 3.5px Accent Pill 胶囊指示条 + 清淡柔和主题浅底，文字清晰可读 |
| **状态指示** | 图标和普通文字混合，间距不稳定 | 统一的带微光圆点状态胶囊（Badges），对齐如一 |
| **快捷微操作** | 需右键弹出多级上下文菜单 | 鼠标悬停即时滑出复制/编辑动作，操作路径缩短 60% |
| **响应式排版** | 窄窗口下水平滚动条硬切，挤压严重 | 响应式媒体查询（680px 以下自动折叠为双行卡片流式结构） |
| **主题切换过渡** | 切换瞬间突兀闪烁 | 颜色变量与过渡曲线（`cubic-bezier`）实现无感丝滑过渡 |

---

## 六、维护与扩展准则

1. **色彩引用原则**：严格从 CSS 变量读取（如 `var(--rb-surface)`、`var(--rb-accent)`、`var(--rb-divider)`），严禁在表格内硬编码十六进制颜色值，确保自动适配深浅双色模式。
2. **行高与换行控制**：
   - 纯数据类表格（如日志、时间序列）推荐使用 `.table-compact`；
   - 双语对白类表格必须允许自然折行（`word-break: break-word`）并配合 1.6~1.7 的呼吸行高，不可随意设置固定像素行高。
3. **无障碍访问（A11y）**：选中行必须同步维护 `aria-selected` 属性，复选框与操作按钮必须配置精准的 `aria-label`。
