"""
ffmpeg_strategy.py

決定 mp4 下載時的 format 選擇與 ffmpeg 後製參數。

------------------------------------------------------------------
背景一：為什麼不能無條件 -c:a aac
------------------------------------------------------------------
YouTube 高畫質採 DASH 分離串流，影音需以 ffmpeg 合併。
原作者對 Merger 無條件加上 -c:a aac，安全但慢——整條音軌要完整
解碼再編碼一次，耗時與片長成正比，表現為進度條停在 99% 很久。

------------------------------------------------------------------
背景二：為什麼不能靠「事先探測」決定要不要 copy
------------------------------------------------------------------
先前版本會另外呼叫一次 extract_info 探測「這支影片有沒有 m4a 音軌」，
有就用 -c:a copy。這個設計有兩個致命問題：

  1. 探測結果與 format chain 的實際選擇是兩套獨立邏輯，會互相矛盾。
     例如使用者選 4320p 而影片沒有該畫質時，chain 會一路 fallback 到
     `bestvideo+bestaudio`，其中 bestaudio 是 Opus；但探測只看到
     「這支影片有 m4a」就回報可以 copy，於是 Opus 被原封不動封進 mp4，
     產生「有影像但沒有聲音」的檔案。

  2. 每支影片多打一次 extract_info。下載播放清單時請求數直接加倍，
     容易觸發 YouTube 的
     "Sign in to confirm you're not a bot" 風控。

------------------------------------------------------------------
本模組的作法：讓格式選擇本身保證音訊必為 AAC
------------------------------------------------------------------
不做任何探測。快速路徑的 format chain 中，每一個候選方案的音訊
都限定為 m4a/AAC，因此 Merger 的預設 -c copy 永遠安全：

    bestvideo[height<=H][vcodec^=avc1]+bestaudio[ext=m4a]
    /bestvideo[height<=H]+bestaudio[ext=m4a]
    /bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]
    /bestvideo+bestaudio[ext=m4a]

只有在上述全部落空時（YouTube 幾乎每支影片都有 itag 140 m4a，
實務上極罕見），才改用寬鬆 chain 搭配 -c:a aac 重跑一次。
由呼叫端以 try/except 銜接，快速路徑成功時完全不多花成本。

刻意不在快速路徑加上 best[ext=mp4] 之類的保底方案：
progressive mp4 只有 360p，靜默降級比明確失敗後重試更難察覺。
"""

from logging_config import setup_logger

logger = setup_logger(__name__)

# YouTube 的 H.264(avc1) 最高只提供到 1080p，超過此高度只有 VP9 / AV1。
# 因此高於 1080p 時不強制 avc1，否則會被迫降級畫質。
_H264_MAX_HEIGHT = 1080

# 相容路徑使用的 ffmpeg 參數：強制把音訊轉成 AAC。
_AAC_REENCODE_ARGS = ['-c:a', 'aac', '-b:a', '192k']

# 判定「格式不可用」的 yt-dlp 錯誤訊息特徵
_FORMAT_UNAVAILABLE_MARKERS = (
    'requested format is not available',
    'requested format not available',
)


def build_mp4_format(height, prefer_h264=True):
    """
    快速路徑的 format 選擇字串。每個候選的音訊都限定 m4a/AAC。

    height 使用 <= 比對而非精確比對：使用者選了影片沒有的畫質時
    （例如選 4320p 但影片最高只有 1080p），會降級到次高可用畫質，
    而不是整條跳過、落到不受控的 fallback。

    注意：yt-dlp 的 '/' 是「整組 format 的替代方案」分隔符，
    不能把含 '/' 的子選擇器直接串進 'bestvideo+<sel>'，
    否則 'A+B/C' 會被解讀成「A+B」或「C(純音訊)」，
    導致 fallback 時只下載到音訊而沒有影像。

    另注意：yt-dlp 預設的 vcodec 偏好順序為
        av01 > vp9.2 > vp9 > h265 > h264
    所以 bestvideo 通常會挑到 AV1 或 VP9。這兩種編碼在 Windows
    需另外安裝 Store 的解碼延伸模組，否則檔案總管無法產生預覽縮圖，
    部分播放器與剪輯軟體也無法開啟。prefer_h264=True 會優先選 avc1。
    """
    h = _normalize_height(height)
    chain = []

    if h:
        if prefer_h264 and h <= _H264_MAX_HEIGHT:
            chain.append(f'bestvideo[height<={h}][vcodec^=avc1]+bestaudio[ext=m4a]')
        chain.append(f'bestvideo[height<={h}]+bestaudio[ext=m4a]')

    if prefer_h264:
        chain.append('bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]')
    chain.append('bestvideo+bestaudio[ext=m4a]')

    # 刻意「不」加上 best[ext=mp4] 之類的保底：progressive mp4 只有 360p，
    # 影片若真的沒有任何 m4a 音軌，寧可讓 yt-dlp 回報格式不可用、
    # 由呼叫端改走相容路徑（全畫質 + AAC 重編碼），
    # 也不要靜默把使用者的 1080p 降級成 360p。
    return _dedupe('/'.join(chain))


def build_mp4_format_compat(height):
    """
    相容路徑的 format 選擇字串。不限定音訊編碼，
    必須搭配 compat_postprocessor_args() 重新編碼成 AAC。
    """
    h = _normalize_height(height)
    chain = []
    if h:
        chain.append(f'bestvideo[height<={h}]+bestaudio')
    chain.append('bestvideo+bestaudio')
    chain.append('best')
    return _dedupe('/'.join(chain))


def compat_postprocessor_args():
    """
    相容路徑的 ffmpeg 參數。

    以 dict 形式限定只作用在 Merger。若傳 list，yt-dlp 會套用到
    每一個 postprocessor，導致 EmbedThumbnail 階段又重編碼一次音訊。
    """
    return {'merger': list(_AAC_REENCODE_ARGS)}


def is_format_unavailable_error(exc):
    """判斷例外是否為「所選格式不存在」，以決定要不要走相容路徑重試。"""
    msg = str(exc).lower()
    return any(m in msg for m in _FORMAT_UNAVAILABLE_MARKERS)


def is_bot_check_error(exc):
    """判斷例外是否為 YouTube 的機器人驗證攔截。"""
    msg = str(exc).lower()
    return ('confirm you' in msg and 'bot' in msg) or 'sign in to confirm' in msg


def build_thumbnail_opts(embed=True):
    """
    回傳內嵌封面所需的 ydl_opts 片段。

    在 mp4 寫入 cover art 後，即使影片本身是 Windows 無法解碼的編碼，
    檔案總管仍能顯示封面圖。
    """
    if not embed:
        return {}
    return {
        'writethumbnail': True,
        'postprocessors': [{
            'key': 'EmbedThumbnail',
            'already_have_thumbnail': False,
        }],
    }


def build_throttle_opts():
    """
    降低觸發 YouTube 風控的機率。

    播放清單以多執行緒下載時，短時間內會湧入大量 metadata 請求，
    容易被判定為機器人。這裡在每次請求之間插入間隔。
    """
    return {
        'sleep_interval_requests': 1,   # 每次 API 請求間隔（秒）
        'retries': 5,
        'extractor_retries': 3,
    }


# ----------------------------------------------------------------------
# 內部工具
# ----------------------------------------------------------------------
def _normalize_height(height):
    try:
        h = int(height)
        return h if h > 0 else None
    except (TypeError, ValueError):
        logger.warning("Invalid height %r; format chain will omit height filter", height)
        return None


def _dedupe(chain_str):
    """去除重複的候選但保持原順序。"""
    seen = set()
    out = []
    for alt in chain_str.split('/'):
        alt = alt.strip()
        if alt and alt not in seen:
            seen.add(alt)
            out.append(alt)
    return '/'.join(out)


def make_postprocessor_hook(progress_callback=None, status_callback=None):
    """
    產生 yt-dlp 的 postprocessor hook。

    下載串流結束後仍有合併/轉檔階段，原版無任何回報，
    使用者會誤以為程式卡在 99%。此 hook 讓 UI 能顯示目前後製狀態。
    """
    def hook(d):
        pp = d.get('postprocessor', '')
        status = d.get('status', '')
        logger.debug("Postprocessor %s: %s", pp, status)
        if status_callback:
            try:
                status_callback(pp, status)
            except Exception:
                pass
        if progress_callback and status == 'finished':
            try:
                progress_callback(0.995)
            except Exception:
                pass
    return hook
