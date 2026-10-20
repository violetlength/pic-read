# 图片文字阅读器

把随手拍的**文字图片**变成一份清晰、可搜索的 PDF：上传图片 → 转换 → 直接阅读 / 下载 PDF。页面保留原图内容（排版、插图、字体都不动），只做摆正、去阴影、增白、锐化，效果与扫描类 App（扫描王 / CamScanner）一致，并叠加不可见文字层——看起来是扫描件。

## 它是什么

一个跑在**你自己电脑上**的网页应用，不开外网、不传云端：

- **后端**：Python 服务（FastAPI + Tesseract OCR + PyMuPDF），负责摆正、增强、识别、出 PDF —— 这些都必须在本机跑。
- **前端**：普通 H5 页面（`index.html` / `style.css` / `app.js`，无框架），用电脑浏览器打开 <http://127.0.0.1:8765> 使用。
- **只在电脑上用**：服务跑在本机、页面在桌面浏览器里操作；关掉服务页面就用不了，也不考虑手机 / 平板、APK、外网部署。

处理过程和产物**全部留在本机**（见「输出文件与数据位置」）。

## 快速开始

```bash
# 1) 装好 Python 3.11+ 和 Tesseract-OCR 5（含 chi_sim 简体中文包）
# 2) 安装 Python 依赖（在项目根目录执行）
pip install -r requirements.txt
# 3) 双击 start.bat —— 服务启动后会自动打开浏览器
```

浏览器里看到「图片文字阅读器」标题、右上角徽标变绿显示 **识别引擎就绪 · chi_sim**，就可以开始用了。关闭服务双击 `stop.bat`。

> `start.bat` 会先做启动前检查（Python 版本、依赖、Tesseract、端口），**不满足条件时窗口会停住并给出具体原因和修复命令**，不会一闪而过；有问题也可以单独运行 `start.bat --check` 只做检查。

## 怎么用

界面只有三步，页顶那行「① 上传图片 → ② 调整顺序、方向、开始转换 → ③ 阅读 / 下载」就是操作顺序。

### 1. 上传图片

- 把图片**拖进虚线框**，或点「选择图片」多选。
- 支持 `JPG / PNG / WEBP / BMP / TIFF`，一次最多 60 张；相机 / 手机翻拍的文字照片、扫描件、截图都行。
- 横拍、竖拍混在一起没关系，会自动摆正。
- 已有内容时重新选择会**覆盖**当前这一批（页面上有提示）。

### 2. 检查 · 摆正 · 排序 → 开始转换

- **点图片任意位置** → 打开大图预览：`↺ 向左转` / `↻ 向右转` 每次 90°，`‹` `›` 或 `←` `→` 换上一张 / 下一张，`Esc` 或点空白处关闭。
- **手动旋转会保存到服务端**，转换时就按你定的方向出页（这些页会跳过自动方向判断）。
- **按住图片右上角的 `⠿` 手柄**拖动可调整顺序（点图片本身只会预览，不会误触发排序）；顺序即转换后的 PDF 页序，左上角 `P1/P2…` 会同步刷新。
- 确认无误后点**开始转换**，会显示进度条和日志。转换方式已固定为最佳设置，不需要选择。
- 旋转或调序后，之前的转换结果作废，**重新点一次「开始转换」**即可（之前归档的文档仍在「阅读历史」里）。

### 3. 阅读 · 下载

- 转换完直接进入**阅读器**：上一页 / 下一页按钮、页码输入框跳转、可切「适宽 / 适合页」；键盘 `←` `→` `空格` `PageUp` `PageDown` `Home` `End` 翻页。每份文档读到第几页会自动记住（存在浏览器里）。
- **下载 PDF**：当前窗口就是阅读器，所以不再另设「打开 PDF」按钮。文件名按时间命名，例如 `扫描件_20261019_1318.pdf`，PDF 内部标题为 `扫描件 2026-10-19 13:18`。
- 一次生成多份时会多出**下载全部 ZIP**。
- **再转一批**回到第 1 步重新开始。

### 阅读历史

顶部**阅读历史**按钮打开本机保存过的文档（转换完成即自动入库）：

- **阅读**：直接回到阅读器继续看（位置沿用上次）。
- **下载**：把 PDF 存到本地。
- **删除 / 清空全部**：只保留你满意的版本。

默认可存 20 份，超出后自动淘汰最旧的（可用环境变量 `LIBRARY_MAX_DOCS` 调整）。

### 键盘快捷键

| 位置 | 按键 | 作用 |
| --- | --- | --- |
| 第 2 步大图预览 | `←` `→` / `↑` `↓` / `空格` | 上一张 / 下一张 |
| 第 2 步大图预览 | `Esc` | 关闭预览 |
| 第 3 步阅读器 | `→` `PageDown` `空格` | 下一页 |
| 第 3 步阅读器 | `←` `PageUp` | 上一页 |
| 第 3 步阅读器 | `Home` / `End` | 第一页 / 最后一页 |
| 阅读历史弹窗 | `Esc` | 关闭 |

## 运行环境

- Python 3.11+
- Tesseract-OCR 5，需含 `chi_sim` 简体中文语言包
  - 默认路径：`C:\Program Files\Tesseract-OCR\tesseract.exe`
  - 可用环境变量覆盖：`TESSERACT_CMD`、`TESSDATA_DIR`、`OCR_LANG`
- 依赖安装：`pip install -r requirements.txt`
- 浏览器：桌面版 Chrome / Edge 等主流浏览器（界面按键鼠与桌面宽度适配）
- 前端是原生 H5，无需 Node / 构建步骤（背景里有可选的 `node --check` 语法检查）

## 启动与停止

`start.bat` 双击即可。它在启动前会逐项检查，任何一项不满足都会**停住窗口**（不会闪退）并告诉你原因：

1. **Python**：找到真实的 Python 3.11+（自动跳过 Microsoft Store 的 `python.exe` 占位符，找不到 `python` 时回退到 `py` 启动器），过旧/跑不起来都会提示。
2. **依赖**：实际 `import` 一遍 fastapi / uvicorn / Pillow / OpenCV / reportlab / pytesseract / pymupdf 等，缺什么就打印缺的模块名，并给出本机对应的安装命令。
3. **Tesseract**：按 `TESSERACT_CMD` → `C:\Program Files\Tesseract-OCR\` → `PATH` 顺序查找；找不到只**警告**（服务仍可启动、可看阅读历史，但转换没有文字层），不会阻断。
4. **端口 8765**：空闲则启动；已是本程序在跑则直接打开浏览器；被**其它程序**占用则明确报错并建议换端口（不会误连、不会误杀）。
5. **启动结果**：等端口就绪即报成功；若进程秒退或 30 秒没起来，会直接把 `logs\server.log` 的最后 20 行贴出来（通常就是真正的报错，如 `ModuleNotFoundError`）。

| 脚本 / 参数 | 说明 |
| --- | --- |
| `start.bat` | 检查环境 → 启动服务 → 自动打开浏览器；结束后窗口停住 |
| `start.bat --check` | 只检查环境（Python / 依赖 / Tesseract / 端口），不启动 |
| `start.bat --no-open` · `--quiet` | 启动但不打开浏览器、不暂停（便于脚本调用） |
| `start.bat --help` | 查看参数说明 |
| `stop.bat` | 停止本程序的服务；**端口被其它程序占用时不做任何操作**（会列出占用进程） |
| `stop.bat --force` | 强制结束占用 8765 的程序（有风险，确认后用） |
| `stop.bat --quiet` | 不暂停，用返回码表示结果（0 成功 / 1 失败） |

日志：`logs\server.log`（服务输出与报错，每次启动覆盖）、`logs\server.stdout`（标准输出）。

两个脚本默认 `HOST=127.0.0.1`、`PORT=8765`（只监听本机，仅供本机浏览器访问），要改端口请同时调整脚本内的 `PORT` 与启动命令。

命令行方式：

```bash
cd G:\LanguageStudy\app
python -m newspaper_reader --open            # 默认 http://127.0.0.1:8765
python -m newspaper_reader --port 9000       # 换端口
```

启动后服务在后台运行，浏览器里就能正常用；用完可让服务继续挂着（下次打开浏览器直接刷新即可），或运行 `stop.bat` 关掉。

> 维护提示：`start.bat` / `stop.bat` 用 **GBK（ANSI）+ CRLF** 保存（中文提示在 cmd 里才不乱码）。编辑这两个文件时请保持该编码与行尾，不要另存为 UTF-8。

## 输出文件与数据位置

全部在 `%TEMP%\newspaper_reader\`（可用环境变量 `NEWSPAPER_RUNTIME_DIR` 改到别处）：

| 目录 | 内容 |
| --- | --- |
| `uploads\{job}\` | 上传的原始图片 |
| `output\{job}\` | 本次转换生成的 PDF（下载接口从这里取） |
| `preview\` | 第 2 步大图预览的缓存（按旋转角度分文件） |
| `library\{doc_id}\` | 阅读历史：`meta.json` + PDF + 按需渲染的页图缓存 |

想彻底清空：在「阅读历史」里点**清空全部**，或直接删掉 `%TEMP%\newspaper_reader\` 目录（建议先停服务）。任务数据（上传图片、临时 PDF）保留 6 小时后自动过期清理。

## 常见问题

- **双击 start.bat 后窗口一闪就没了**：现在不会这样了——脚本在每一步失败时都会 `pause` 停住并打印原因。如果仍然闪退，通常是 `start.bat` 被改过（编码不是 GBK/ANSI，或行尾不是 CRLF），恢复原文件即可；也可以手动在 cmd 里运行 `start.bat --check` 看输出。
- **提示"端口 8765 已被其它程序占用"**：不是本服务占的，脚本不会去动它。关掉占用的程序（脚本没有显示进程名时可用 `Get-NetTCPConnection -LocalPort 8765` 查），或改用 `python -m newspaper_reader --port 9000`。
- **提示"服务已在运行"**：直接打开 <http://127.0.0.1:8765> 即可；确实要重启就先运行 `stop.bat`。
- **提示"Python 依赖不完整"**：按屏幕上给出的那条 `pip install -r requirements.txt` 命令执行（注意用同一个 Python；脚本会打印它的完整路径）。
- **启动失败 / 服务秒退**：脚本会把 `logs\server.log` 最后 20 行贴出来，基本就是根因（常见：依赖装到了另一个 Python 上、端口被占、Tesseract 路径不对）。
- **徽标红色「识别引擎未就绪」**：Tesseract 没装好或路径不对。确认 `C:\Program Files\Tesseract-OCR\tesseract.exe` 存在且 `tessdata\chi_sim.traineddata` 在，或用 `TESSERACT_CMD` / `TESSDATA_DIR` 指到正确位置，然后重启服务。
- **中文识别不出来 / 乱码**：多半是图片太糊、太小或严重倾斜。建议重拍（正对、光线足、占满画面），或在第 2 步手动旋转摆正后重新转换。
- **页面看起来像图片，复制出来的文字不对**：文字层由 OCR 生成，识别不准时文字层会跟着不准；不影响阅读观感。
- **识别出的文字错位 / 内容失真**：这是代码里保留的**实验性「智能重排」**通道（按 OCR 坐标重绘版面）才会出现，界面已不提供，正常使用不会触发。
- **转换中卡住不动了**：如果这时重启过服务或任务过期（超过 6 小时），界面会自动解锁并提示重新上传，不会一直卡着。
- **想改清晰度 / 增强方式**：改 `newspaper_reader/config.py` 里的 `DEFAULT_SCAN_STYLE`、`DEFAULT_CLARITY` 后**重启服务**（界面上不提供这些选项）。
- **改动没生效 / 页面样式不对**：前端文件每次请求都读盘，浏览器 `Ctrl+F5` 强刷即可；改的是 `.py` 才需要先 `stop.bat` 再 `start.bat` 重启服务。
- **图片顺序不对**：在第 2 步拖 `⠿` 手柄重排，然后重新转换；转换完的 PDF 顺序就已固定，要改只能重新上传。

## 转换参数

| 参数 | 说明 |
| --- | --- |
| 转换方式 | 固定为**扫描件美化**，界面上不提供选择。透视摆正 → 去阴影 / 增白 / 锐化（彩色增强）→ 全部页面合并为一个 PDF，页面保留原图外观 + 可搜索文字层，效果类似扫描类 App |
| 默认值位置 | `newspaper_reader/config.py`：`DEFAULT_OUTPUT_MODE="scan"`、`DEFAULT_SCAN_STYLE="color"`、`DEFAULT_CLARITY="high"`（仅调试时修改） |
| （开发用）`POST /api/convert` 可选参数 | `mode`（`scan` / 实验性 `rebuild`）、`scan_style`（`color` / `auto` / `gray` / `bw`）、`clarity`（`high` / `std`）、`bg_opacity`（智能重排底图透明度）——界面不再传这些参数，交由服务端默认值决定 |

## 目录结构

```
newspaper_reader/
├── __main__.py          # 启动入口（--port / --open）
├── app.py               # FastAPI 后端（上传/转换/进度/下载/阅读历史）
├── config.py            # 路径与参数（含阅读历史上限、默认转换方式）
├── core/
│   ├── image_proc.py    # 纸张摆正、裁边、纠偏
│   ├── ocr.py           # Tesseract 中文识别（词级坐标）+ 90°/270° 方向判定
│   ├── enhance.py       # 原图增强：去阴影、增白、对比度、锐化、黑白二值
│   ├── layout.py        # 分栏、标题/竖排判定、插图区域检测
│   ├── cover.py         # 版面封面信息解析与分组
│   ├── library.py       # 阅读历史：入库/列表/删除 + 页图按需渲染与缓存
│   ├── fonts.py         # 中文字体注册与字宽测量
│   └── render_pdf.py    # 矢量版式 PDF + 扫描合并 PDF（含隐形文字层）
├── web/static/          # 前端页面（index.html / style.css / app.js）
└── test/                # 样例生成、流水线验证、HTTP/浏览器端到端测试
```

## API 一览

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| POST | `/api/upload` | 多图上传，返回 `job_id` 与页列表 |
| POST | `/api/convert/{job}` | 开始转换（界面不传参数，用服务端默认：扫描件美化 / 彩色增强 / 高清） |
| GET | `/api/job/{job}` | 轮询进度、日志、结果（含 `doc_id`） |
| GET | `/api/job/{job}/pageimg/{page}?w=1600` | 第 2 步大图预览（按当前旋转角度生成，磁盘缓存） |
| POST | `/api/job/{job}/page/{page}/rotate` | 设定该页手动旋转角（`angle`: 0/90/180/270），返回新缩略图 |
| POST | `/api/job/{job}/order` | 保存页序（`ids`: 按新顺序排列的页 id） |
| GET | `/api/download/{job}/{name}` | 下载本次生成的 PDF |
| GET | `/api/zip/{job}` | 下载全部 PDF 压缩包 |
| GET | `/api/library` | 阅读历史列表 |
| GET | `/api/library/{id}/page/{n}?w=1600` | 阅读器页图（按需渲染，磁盘缓存） |
| GET | `/api/library/{id}/thumb.jpg` | 历史列表缩略图 |
| GET | `/api/library/{id}/pdf` | 阅读历史中的 PDF |
| DELETE | `/api/library/{id}` · `/api/library` | 删除单份 / 清空阅读历史 |

## 技术要点

1. **摆正**：Canny 轮廓检测纸张四边形 → 透视变换；Otsu + 最小外接矩形做角度纠偏。
2. **方向**：Hough 线段判断"横放/竖放"，横放页面再用 OCR 得分区分 90° 与 270°（两者线方向相同，只能靠文字朝向分辨）；竖版页面永不被转成横版。**第 2 步里手动旋转过的页面会跳过自动判定**，按用户设定方向出页。
3. **原图增强**：形态学闭运算估计光照场 → 增白去阴影（彩色/纹理区域加保护，不洗掉插图）→ 白点拉伸 + 轻微对比 → 亮度通道轻降噪 → **按分辨率自适应的双重反锐化掩蔽**（细边 + 中频）；低于约 300DPI 的页面先 LANCZOS 升采样再锐化；`黑白二值`的自适应阈值块尺寸随分辨率缩放。
4. **识别**：Tesseract `--psm 6 --oem 1` + `chi_sim+eng`，输出词级 `conf` 与包围盒，越界词被裁剪剔除。
5. **版式分析**：词按基线聚成行 → x 轴投影切分栏带 → 按栏归组；高度/宽度比判定竖排；方差+饱和度检测插图区域。
6. **渲染**：字体号按行高估算，超宽时**横向压缩**而非缩小字号，保持与原图同等字高与版式；扫描模式整页嵌图 + `3 Tr` 隐形文字层（文字渲染模式 3）实现"看着是图、搜得到字"，嵌入 JPEG 使用 **4:4:4 无色度抽样**（4:2:0 会把彩色文字边缘糊掉，PSNR 约 35dB；4:4:4 约 44–47dB）。
7. **分组**：空间顺序拼接 OCR 文本（含词级行聚类兜底），正则提取 `第NNN期` / `YYYY年M月D日` / `本期N版`，封面页触发新分组；普通文字图片识别不到这些信息时自动归为**一份文档**，界面不出现期号字样。
8. **阅读历史**：转换完成的 PDF 复制进 `%TEMP%\newspaper_reader\library\{doc_id}\`（含 `meta.json`），页图用 PyMuPDF 按需渲染成 JPEG（质量 92、无色度抽样）并缓存；超过 `LIBRARY_MAX_DOCS`（默认 20）自动淘汰最旧的文档。

## 测试

```bash
python newspaper_reader/test/make_samples.py    # 生成 7 页样例
python newspaper_reader/test/test_pipeline.py   # 版式重建：OCR→版式→分组 PDF
python newspaper_reader/test/test_scan.py       # 原图增强→合并 PDF→PyMuPDF 校验文字层
python newspaper_reader/test/e2e_scan.py        # HTTP 端到端（原图增强 + 智能排版 + 阅读历史）
python newspaper_reader/test/e2e_rebuild.py     # 同一任务反复转换回归
python newspaper_reader/test/e2e_edit.py        # 第 2 步编辑：大图预览 / 旋转 / 调序 → 转出顺序校验
python newspaper_reader/test/e2e_ui.py          # 浏览器端到端（三步流程 + 阅读器 + 预览旋转拖拽 + 历史，需 playwright install chromium）
python newspaper_reader/test/smoke_scan.py      # 转换接口冒烟
```

端到端脚本需要服务已在 8765 端口运行（`start.bat` 或 `python -m newspaper_reader`）。

## 许可

MIT License，见 [LICENSE](LICENSE)。
