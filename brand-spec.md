# Brand Spec · 快手作品保存台

> 这是一个非官方的本地工具页面，使用快手的公开 favicon 标识“解析对象”，不复制快手的完整品牌系统，也不暗示官方身份。

## Assets

| 文件 | 来源 | 用途 |
|---|---|---|
| `assets/kuaishou-favicon.ico` | 快手官网公开 favicon `s1-11674.kwimgs.com/udata/pkg/fe/favicon.70ff1fcc.ico` | 浏览器图标 |
| `assets/kuaishou-icon.png` | 上述 favicon 转 PNG（48 → 256） | 导航标识、海报中心、空状态 |

- 标识尺寸：导航 38 × 38（圆角 10）；海报 64 × 64（圆角 16）。
- 不重绘、不使用 CSS 色块替代标识。
- 海报中的视频画面是解析结果的封面，属于内容预览，不是产品图。

## Palette

| Token | Hex | 用途 |
|---|---|---|
| `--paper` | `#F2EDE4` | 页面底色（暖纸） |
| `--paper-soft` | `#F8F3EA` | 输入区、音频条底色 |
| `--card` | `#FFFCF6` | 卡片 |
| `--ink` | `#181410` | 主文字 |
| `--ink-2` | `#3B342B` | 次级文字 |
| `--muted` | `#847A6B` | 标签、说明 |
| `--line` | `#DCD3C5` | 分隔线 |
| `--orange` | `#FF4D00` | 品牌强调、主按钮 |
| `--orange-deep` | `#D33E00` | hover |
| `--orange-soft` | `#FFE7DA` | 图标底色 |
| `--night` | `#14110D` | 深色说明区 |

颜色数量：4 个主色族（纸、墨、橙、深色），不引入其它色相。

## Typography

- 标题：`Noto Serif SC` / `Songti SC` / `SimSun`，500–600 字重，负字距（-0.03 ~ -0.045em）。
- 正文：`PingFang SC` / `HarmonyOS Sans SC` / `Microsoft YaHei`。
- 标签、数字、代码：`DM Mono` / `Cascadia Code` / Consolas，9–11px，字距 0.08–0.18em。
- 标题与正文比例约 4:1（桌面 h1 94px / 正文 16.5px）。

## Layout

- 12 栏语义网格，最大宽度 1240px，桌面间距 40px。
- 首屏：左侧 1.15fr 操作区 + 右侧 368px 静态海报；≤940px 隐藏海报。
- 解析结果：330px 竖屏预览 + 自适应信息列；≤940px 单列。
- 卡片圆角：22–30px；按钮 999px；输入区 22px。
- 阴影只用于“纸片浮起”，避免多层发光。

## Motion

- 主曲线：`cubic-bezier(.2,.8,.2,1)`；时长 220–500ms。
- 悬停：按钮上移 1px、箭头右移 3px；历史卡上移 3px。
- 结果出现：透明度 + 18px 位移；海报指针视差 ±7°。
- 尊重 `prefers-reduced-motion`，关闭动画与平滑滚动。

## Voice

- 直接、具体、技术性：说“本地引擎”“CDN 直连”“原声 M4A”，不用夸张营销词。
- 不使用 emoji 作为图标；所有图标为线性 SVG。
- 英文只做结构标签（RESULT / LOCAL HISTORY / PREVIEW FRAME），不喧宾夺主。
