# 第三方元件說明 / Third-Party Notices

本專案（Video DownloadErm v2.0）以 **MIT License** 釋出，
版權宣告見根目錄 [`LICENSE`](LICENSE)。

> **本 repository 不散布任何第三方二進位檔或套件。**
> 下列元件皆由建置流程自動取得（`pip install -r requirements.txt`）
> 或於建置時另行下載（FFmpeg），因此本專案不負有 GPL / LGPL / Apache
> 等授權的散布義務。本檔案僅作為資訊揭露，方便使用者了解
> 執行本程式時實際會引入哪些元件、以及各自的授權條件。

---

## 元件一覽

| 元件 | 授權 | 取得方式 | 授權全文 |
|---|---|---|---|
| [FFmpeg](https://ffmpeg.org/)（gyan.dev build） | **GPL v3** | `build.bat` 自動下載 | [GPL-3.0](https://www.gnu.org/licenses/gpl-3.0.txt) |
| [edge-tts](https://github.com/rany2/edge-tts) | **LGPL v3**（單一檔案 MIT） | pip | [LGPL-3.0](https://www.gnu.org/licenses/lgpl-3.0.txt) |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Unlicense（公眾領域） | pip | [Unlicense](https://unlicense.org/) |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | CC0 1.0 | pip | [CC0](https://creativecommons.org/publicdomain/zero/1.0/legalcode) |
| [pywinstyles](https://github.com/Akascape/py-window-styles) | CC0 1.0 | pip | 同上 |
| [CTkTable](https://github.com/Akascape/CTkTable) | MIT | pip | [MIT](https://github.com/Akascape/CTkTable/blob/main/LICENSE) |
| [Pillow](https://python-pillow.org/) | MIT-CMU (HPND) | pip | [LICENSE](https://github.com/python-pillow/Pillow/blob/main/LICENSE) |
| [Requests](https://requests.readthedocs.io/) | Apache 2.0 | pip | [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0.txt) |
| [PyInstaller](https://pyinstaller.org/) | GPL v2+ with bootloader exception | pip（僅建置工具） | [LICENSE](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) |

---

## FFmpeg（GPL v3）

FFmpeg 用於影音串流合併、格式轉換與封面內嵌。

### 為什麼是 GPL v3

`build.bat` 取用的是 **gyan.dev** 發布的預編譯 build，其編譯選項包含：

```
--enable-gpl --enable-version3 --enable-libx264 --enable-libx265 ...
```

* `--enable-gpl` 使該建置受 **GNU General Public License** 約束
* `--enable-version3` 使其升級為 **GPL 第 3 版**

（該 build 靜態連結了 x264、x265、libxvid、libvidstab、frei0r 等本身即為 GPL
授權的編解碼器，這是它必須以 GPL 散布的原因。）

### 與本專案的關係

本專案**未以任何形式連結（link）FFmpeg 的程式庫**。
FFmpeg 僅透過 yt-dlp 的 `ffmpeg_location` 參數，以**獨立行程**被呼叫執行
（見 `Page1.py`、`Page2.py`、`Page3.py`）。

依自由軟體基金會對 GPL 適用範圍的一般見解，
以獨立行程互相呼叫的程式通常不構成單一衍生作品，
故本專案的 Python 原始碼維持 MIT 授權。

由於本 repository **不包含** FFmpeg 執行檔（見 `.gitignore`），
亦不隨附散布，因此不觸發 GPL v3 的散布義務。

### 若你要自行發行打包成品

一旦你把 `dist/` 下的成品（其中含 `ffmpeg.exe`）分享給他人，
即構成 GPL v3 二進位檔的散布，屆時須履行：

1. 隨附 GPL v3 全文
2. 提供對應原始碼，或附上三年有效的書面取得聲明
3. 標示該 build 的來源

FFmpeg 原始碼取得管道：

* 官方原始碼：<https://ffmpeg.org/download.html>
* 官方 Git：<https://git.ffmpeg.org/ffmpeg.git>
* 本專案所用 build 及其建置腳本：<https://www.gyan.dev/ffmpeg/builds/>

本專案未對 FFmpeg 原始碼做任何修改。

---

## edge-tts（LGPL v3）

文字轉語音功能（`Page4.py`）使用 edge-tts。

該套件以 **GNU Lesser General Public License v3** 授權，
其中 `src/edge_tts/srt_composer.py` 單一檔案另以 MIT 授權
（Copyright (c) 2014-2023 Christopher Down；Copyright (c) 2025- rany）。

由 pip 安裝，不隨本 repository 散布。

若日後製作包含 edge-tts 的發行版（例如 PyInstaller 打包成品），
請留意 LGPL v3 要求終端使用者需具備替換該程式庫的能力。

---

## 其他

* **yt-dlp** 以 Unlicense 釋出，已置於公眾領域，無附加義務。
* **CustomTkinter**、**pywinstyles** 以 CC0 1.0 釋出，無附加義務。
* **Requests** 為 Apache 2.0（Copyright 2019 Kenneth Reitz），散布時需保留歸屬聲明。
* **PyInstaller** 僅作為建置工具使用，其 bootloader 例外條款明確允許
  打包專有或非 GPL 程式。

---

## 使用者素材與服務條款

本專案僅為技術工具，不含亦不散布任何影音內容。
使用者透過本工具下載之媒體內容，其著作權歸原權利人所有，
使用者須自行確認其行為符合當地法令及來源平台之服務條款。

---

*最後更新：2026-07-28*
