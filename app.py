# app.py - 最終版，支援 mp4/mp3 正常輸出 + 影片標題作為下載檔名

from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import uuid
import tempfile
import yt_dlp
import urllib.parse

app = Flask(__name__)

# 🔥 讓前端可讀取 Content-Disposition（否則檔名會變 download.mp4）
CORS(app, expose_headers=["Content-Disposition"])

# ----------- 系統暫存資料夾 -----------
TEMP_DIR = tempfile.gettempdir()
APP_TEMP_DIR = os.path.join(TEMP_DIR, 'yt_dlp_processor_temp')

if not os.path.exists(APP_TEMP_DIR):
    os.makedirs(APP_TEMP_DIR)
# --------------------------------------


# 移除檔名非法字元
def sanitize_filename(filename):
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    return filename


@app.route('/api/process', methods=['POST'])
def process_media():
    data = request.get_json()
    source_url = data.get('url')
    target_format = data.get('format')   # mp4 或 mp3

    if not source_url or target_format not in ['mp4', 'mp3']:
        return jsonify({'error': 'Invalid URL or format parameter.'}), 400

    print(f"\n--- 處理請求 ---")
    print(f"來源 URL: {source_url}")
    print(f"目標格式: {target_format.upper()}")

    unique_id = str(uuid.uuid4())
    base_output = os.path.join(APP_TEMP_DIR, f"{unique_id}_%(title)s.%(ext)s")

    # ---------- yt-dlp 基本設定 ----------
    ydl_opts = {
        "outtmpl": base_output,
        "quiet": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": "./bin",     # 指定你的 ffmpeg 位置
    }

    # ---------- MP4 下載設定 ----------
    if target_format == "mp4":
       ydl_opts["format"] = (
        "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
        "best[ext=mp4][vcodec^=avc1]"
    )
    # ---------- MP3 下載設定 ----------
    if target_format == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })

    final_filepath = None

    try:
        # 執行 yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source_url, download=True)

        # 取得影片標題
        title = sanitize_filename(info.get("title", "video"))
        ext = "mp3" if target_format == "mp3" else "mp4"

        # 在暫存資料夾中尋找 yt-dlp 生成的檔案
        for fname in os.listdir(APP_TEMP_DIR):
            if fname.startswith(unique_id) and fname.endswith(f".{ext}"):
                final_filepath = os.path.join(APP_TEMP_DIR, fname)
                break

        if not final_filepath or not os.path.exists(final_filepath):
            raise Exception("yt-dlp 下載後找不到輸出檔案")

        print(f"最終檔案: {final_filepath}")

        # 下載時顯示的檔名 = 影片標題.mp4 / .mp3
        download_name = f"{title}.{ext}"

        mime_type = f"video/{ext}" if ext == "mp4" else f"audio/{ext}"

        response = send_file(
            final_filepath,
            as_attachment=True,
            download_name=download_name,
            mimetype=mime_type
        )

        # 修正中文檔名
        quoted = urllib.parse.quote(download_name)
        response.headers["Content-Disposition"] = (
            f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"
        )

        # 自動清理所有相關檔案
        @response.call_on_close
        def cleanup():
            for f in os.listdir(APP_TEMP_DIR):
                if f.startswith(unique_id):
                    try:
                        os.remove(os.path.join(APP_TEMP_DIR, f))
                        print(f"已清理: {f}")
                    except:
                        pass

        return response

    except Exception as e:
        print("錯誤：", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
