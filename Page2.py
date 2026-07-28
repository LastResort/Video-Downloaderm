import os
import re
import time
import functools
import subprocess
import threading
from logging_config import setup_logger, log_and_show_error
from ffmpeg_strategy import (build_mp4_format, build_mp4_format_compat,
                             compat_postprocessor_args, build_thumbnail_opts,
                             build_throttle_opts, make_postprocessor_hook,
                             is_format_unavailable_error, is_bot_check_error)
import yt_dlp
import uuid

# ------------------------------
# 初始化 Logger
# ------------------------------
logger = setup_logger(__name__)

# extract_flat 模式下，yt-dlp 對無法存取的項目會給定這些固定標題。
# 這些項目沒有實際內容，必須在解析階段就濾掉。
# 本模組的下載函式會被 ThreadPoolExecutor 併發呼叫，
# 錯誤狀態必須逐執行緒隔離，否則某支影片被 bot 驗證擋下時，
# 會誤導其他 worker 放棄重試。
_thread_state = threading.local()


def _mark_bot_blocked(flag):
    _thread_state.bot_blocked = bool(flag)


def _was_bot_blocked():
    return getattr(_thread_state, 'bot_blocked', False)


_UNAVAILABLE_TITLES = frozenset({
    '[Private video]',
    '[Deleted video]',
    '[Unavailable video]',
    '[Age restricted]',
})

def timeit(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        elapsed = end_time - start_time
        logger.info(f"{func.__name__} executed in {elapsed:.4f} seconds")
        return result
    return wrapper

def _sanitize_filename(filename):
    """
    將檔案名稱中 Windows 不允許的字元替換為底線，
    並移除控制字元或非可見字元。
    """
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'[\x00-\x1f\x80-\x9f]', '', filename)
    return filename

def _generate_new_filename(download_path, filename):
    """
    檢查 download_path 中是否已存在相同檔名，若存在則在檔名後方加上 (1), (2) 等標記。
    """
    filename = _sanitize_filename(filename)
    base, ext = os.path.splitext(filename)
    new_filename = filename
    counter = 1
    while os.path.exists(os.path.join(download_path, new_filename)):
        new_filename = f"{base} ({counter}){ext}"
        counter += 1
    return new_filename

@timeit
def parse_playlist(url, resolution, file_format="mp4", cookiefile=''):
    """
    解析播放清單 URL，若不是播放清單則印出錯誤並回傳空列表；
    否則回傳列表，每筆為影片資料字典，包含 "title", "resolution", "format", "url"。
    """
    if "list=" not in url:
        return []
    
    playlist = []
    
    try:
        logger.info("Parsing playlist from URL: %s", url)
        ydl_opts = {
            'quiet': True,
            # 'in_playlist' 只抓清單層級的淺資訊(id/title)，不逐支影片再解析一次。
            # parse_playlist 只用得到 id 與 title，改用 flat 可把解析時間從
            # 數十秒~數分鐘降到數秒；代價是少數清單的 title 可能取不到（顯示 Unknown），
            # 且無法在此階段得知影片是否可下載（改由下載階段的 retry 機制處理）。
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'noplaylist': False,    # 強制解析播放清單
            'ignoreerrors': True,   # 跳過私人/已刪除的影片，繼續解析其餘項目
        }
        # 若有指定cookies檔案，則加入 cookies 選項
        if cookiefile != '':
        # 使用 cookies 來處理年齡限制或地區限制的影片
        # cookiesfrombrowser無法使用, ERROR: _parse_browser_specification() takes from 1 to 4 positional arguments but 6 were given
        # cookies會過期
            ydl_opts['cookiefile'] = cookiefile # 只有這能用，需先匯出cookies.txt

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # 啟用 ignoreerrors 後，整個清單都取不到時 extract_info 會回 None
        if not info or "entries" not in info:
            log_and_show_error("No playlist entries found!")
            return []

        skipped = 0
        for entry in info['entries']:
            # ignoreerrors 會把解析失敗的項目（私人、已刪除、地區限制）留成 None，
            # 直接取用會拋 'NoneType' object is not subscriptable，這裡要跳過。
            if not entry:
                skipped += 1
                continue
            video_id = entry.get('id')
            if not video_id:
                skipped += 1
                continue

            title = entry.get("title") or "Unknown"
            # flat 模式下不可用的項目仍會出現在清單中，
            # yt-dlp 以固定標題標記，這裡一併濾除避免下載階段整批失敗。
            if title in _UNAVAILABLE_TITLES:
                logger.info("Skip unavailable entry %s (%s)", video_id, title)
                skipped += 1
                continue

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            playlist.append({
                "title": title,
                "resolution": resolution,
                "format": file_format,
                "url": video_url
            })

        if skipped:
            logger.warning(
                "Skipped %d unavailable item(s) in playlist (private/deleted/region-locked)",
                skipped)
        if not playlist:
            log_and_show_error("No playlist entries found!")
            return []
        logger.info("Parsed %d video(s) from playlist, %d skipped", len(playlist), skipped)
        return playlist
    except Exception as e:
        log_and_show_error(f"Error parsing playlist: {e}")
        return []

@timeit
def download_video_audio_playlist_with_retry(url, resolution, download_path, file_format, cookiefile='', max_retries=3):
    _mark_bot_blocked(False)
    for attempt in range(max_retries):
        logger.info(f"Attempt {attempt + 1} to download: {url}")
        result = download_video_audio_playlist(url, resolution, download_path, file_format, cookiefile)
        if result is not None and os.path.exists(result) and os.path.getsize(result) > 0:
            return result
        # 被 YouTube 機器人驗證擋下時，重試只會加重風控，直接放棄這一支
        if _was_bot_blocked():
            logger.error("Blocked by YouTube bot check, skip retrying: %s", url)
            return None
        logger.info("Retrying in 2 seconds...")
        time.sleep(2)  # 等待2秒再重試
    log_and_show_error(f"多次嘗試仍失敗: {url}")
    return None

def download_video_audio_playlist(url, resolution, download_path, file_format, cookiefile=''):
    temp_id = uuid.uuid4().hex
    final_filepath = None
    ffmpeg_path = os.path.join(os.path.dirname(__file__), 'ffmpeg', 'bin', 'ffmpeg.exe')
    ydl_opts = {}
    if file_format == 'mp4':
        try:
            # 解析如 "1080p", "720p" 這種格式，只保留數字部分作為 height
            height_str = resolution.lower().replace('p', '').strip()
            height = int(height_str)
        except Exception as e:
            log_and_show_error("解析解析度失敗，請檢查格式是否正確(例如 '1080p')")
            raise ValueError("解析解析度失敗，請檢查格式是否正確(例如 '1080p')") from e
        
        temp_template = os.path.join(download_path, f"temp_download_{temp_id}.%(ext)s")
        # 快速路徑：不做任何額外探測（探測會讓每支影片的請求數加倍，
        # 是先前觸發 YouTube 機器人驗證的主因）。format chain 的每個候選
        # 都限定 m4a/AAC 音訊，Merger 的預設 -c copy 因此永遠安全。
        ydl_opts = {
            'format': build_mp4_format(height),
            'outtmpl': temp_template,
            'noplaylist': True,
            'merge_output_format': 'mp4',
            'ffmpeg_location': ffmpeg_path,
        }
        # 內嵌 YouTube 封面為 mp4 cover art，
        # 讓檔案總管即使無法解碼影片本身也能顯示縮圖。
        ydl_opts.update(build_thumbnail_opts())
        ydl_opts.update(build_throttle_opts())
    elif file_format == 'mp3':
        temp_template = os.path.join(download_path, f"temp_download_{temp_id}.%(ext)s")
        # 嘗試解析用戶選擇的位元率
        selected_bitrate = None
        try:
            selected_bitrate = int(resolution.replace("kbps", "").strip())
        except Exception:
            pass
        if selected_bitrate is not None:
            format_str = f"bestaudio[abr={selected_bitrate}]/bestaudio/best"
            preferred_quality = str(selected_bitrate)
        else:
            format_str = "bestaudio/best"
            preferred_quality = str(selected_bitrate)
        ydl_opts = {
            'format': format_str,
            'outtmpl': temp_template,
            'noplaylist': True,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': preferred_quality,
            }],
            'ffmpeg_location': ffmpeg_path,
        }
        ydl_opts.update(build_throttle_opts())

    try:
        # 若有指定cookies檔案，則加入 cookies 選項
        if cookiefile != '':
        # 使用 cookies 來處理年齡限制或地區限制的影片
        # cookiesfrombrowser無法使用, ERROR: _parse_browser_specification() takes from 1 to 4 positional arguments but 6 were given
        # cookies會過期
            ydl_opts['cookiefile'] = cookiefile # 只有這能用，需先匯出cookies.txt

        ydl_opts['postprocessor_hooks'] = [make_postprocessor_hook()]

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except Exception as e:
            # 快速路徑要求音訊必為 m4a。極少數影片沒有任何 m4a 音軌，
            # 此時改用寬鬆 chain 並把音訊重新編碼成 AAC 再跑一次。
            if file_format != 'mp4' or not is_format_unavailable_error(e):
                raise
            logger.warning("No m4a audio available; retrying with AAC re-encode: %s", url)
            ydl_opts['format'] = build_mp4_format_compat(height)
            ydl_opts['postprocessor_args'] = compat_postprocessor_args()
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

        if file_format == 'mp4':
            output_ext = 'mp4'
        else:
            output_ext = 'mp3'
        # 取得 yt_dlp 回傳的影片標題
        raw_title = info['title']
        # 利用自訂函式先清理標題，再產生唯一檔案名稱
        safe_title = _sanitize_filename(raw_title)
        filename = safe_title + f".{output_ext}"
        unique_filename = _generate_new_filename(download_path, filename)
        final_filepath = os.path.join(download_path, unique_filename)
        # 取得暫存檔案的完整路徑
        temp_filepath = os.path.join(download_path, f"temp_download_{temp_id}.{output_ext}")
        # 重新命名暫存檔案
        os.rename(temp_filepath, final_filepath)
        
        return final_filepath
    except Exception as e:
        logger.error(f"Error downloading {url}: {e}")
        # 供 with_retry 判斷是否值得重試（bot 驗證重試只會加重風控）
        _mark_bot_blocked(is_bot_check_error(e))
        # log_and_show_error(f"Error downloading {url} : {e}") # 不需要顯示視窗
        return None
