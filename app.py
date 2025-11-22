# app.py - Render 最終版，可正確輸出 MP4/MP3 + 首頁 UI + 影片標題檔名

from flask import Flask, request, send_file, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import tempfile
import yt_dlp
import urllib.parse

app = Flask(__name__)
CORS(app, expose_headers=["Content-Disposition"])

# 🔥 Render 首頁：回傳 index.html
@app.route('/')
def home():
    return send_from_directory('.', 'index.html')


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
    target_format = data.get('format')

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
        "ffmpeg_location": "./bin",
        "cookiefile": "./cookies/cookies.txt"   # ← 加這行！
    }

    # ---------- MP4 ----------
    if target_format == "mp4":
        ydl_opts["format"] = (
            "bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]/"
            "best[ext=mp4][vcodec^=avc1]"
        )

    # ---------- MP3 ----------
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

        title = sanitize_filename(info.get("title", "video"))
        ext = "mp3" if target_format == "mp3" else "mp4"

        # 找到輸出檔
        for fname in os.listdir(APP_TEMP_DIR):
            if fname.startswith(unique_id) and fname.endswith(f".{ext}"):
                final_filepath = os.path.join(APP_TEMP_DIR, fname)
                break

        if not final_filepath:
            raise Exception("找不到 yt-dlp 輸出的檔案！")

        print(f"最終檔案: {final_filepath}")

        download_name = f"{title}.{ext}"

        mime_type = "video/mp4" if ext == "mp4" else "audio/mp3"

        response = send_file(
            final_filepath,
            as_attachment=True,
            download_name=download_name,
            mimetype=mime_type
        )

        quoted = urllib.parse.quote(download_name)
        response.headers["Content-Disposition"] = (
            f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"
        )

        # 自動清理
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
    app.run(host="0.0.0.0", port=5000)
