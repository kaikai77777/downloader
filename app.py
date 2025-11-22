from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import uuid
import tempfile
import yt_dlp
import urllib.parse

app = Flask(__name__)
CORS(app, expose_headers=["Content-Disposition"])  # 讓前端能讀取檔名

def home():
    return send_from_directory(".", "index.html")
# 暫存資料夾
TEMP_DIR = tempfile.gettempdir()
APP_TEMP_DIR = os.path.join(TEMP_DIR, "yt_dlp_processor_temp")
if not os.path.exists(APP_TEMP_DIR):
    os.makedirs(APP_TEMP_DIR)

# 你的 cookies.txt
COOKIES_PATH = "./cookies/cookies.txt"


def sanitize_filename(name):
    bad = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for c in bad:
        name = name.replace(c, "_")
    return name


@app.route("/api/process", methods=["POST"])
def process_media():
    data = request.get_json()
    source_url = data.get("url")
    target_format = data.get("format")

    if not source_url or target_format not in ["mp4", "mp3"]:
        return jsonify({"error": "Invalid URL or format"}), 400

    unique_id = str(uuid.uuid4())
    output_template = os.path.join(APP_TEMP_DIR, f"{unique_id}_%(title)s.%(ext)s")

    # 基本設定
    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "noplaylist": True,
        "cookiefile": COOKIES_PATH,      # 🔥 使用 cookies.txt
        "merge_output_format": "mp4",
        "ffmpeg_location": "./bin",       # Render 不會用到，但本地會
    }

    # --- MP4 設定（最相容） ---
    if target_format == "mp4":
        ydl_opts["format"] = "bestvideo+bestaudio/best"

    # --- MP3 設定 ---
    if target_format == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        })

    try:
        # 執行 yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source_url, download=True)

        title = sanitize_filename(info.get("title", "video"))
        ext = "mp3" if target_format == "mp3" else "mp4"

        final_path = None

        # 找到輸出檔案
        for f in os.listdir(APP_TEMP_DIR):
            if f.startswith(unique_id) and f.endswith(f".{ext}"):
                final_path = os.path.join(APP_TEMP_DIR, f)
                break

        if not final_path:
            raise Exception("Cannot locate downloaded file")

        download_name = f"{title}.{ext}"
        mime = "video/mp4" if ext == "mp4" else "audio/mp3"

        response = send_file(
            final_path,
            as_attachment=True,
            download_name=download_name,
            mimetype=mime
        )

        quoted = urllib.parse.quote(download_name)
        response.headers["Content-Disposition"] = (
            f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"
        )

        @response.call_on_close
        def cleanup():
            for f in os.listdir(APP_TEMP_DIR):
                if f.startswith(unique_id):
                    try:
                        os.remove(os.path.join(APP_TEMP_DIR, f))
                    except:
                        pass

        return response

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
