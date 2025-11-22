from flask import Flask, request, send_file, jsonify
from flask_cors import CORS
import os
import uuid
import tempfile
import yt_dlp
import urllib.parse

app = Flask(__name__)
CORS(app, expose_headers=["Content-Disposition"])

# === 指向你的 cookies.txt（在 GitHub 專案內的 /cookies/cookies.txt）===
COOKIES_PATH = os.path.join(os.path.dirname(__file__), "cookies", "cookies.txt")

# === 暫存資料夾 ===
TEMP_DIR = tempfile.gettempdir()
APP_TEMP_DIR = os.path.join(TEMP_DIR, "yt_dlp_processor_temp")

if not os.path.exists(APP_TEMP_DIR):
    os.makedirs(APP_TEMP_DIR)

def sanitize_filename(filename):
    illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    return filename


@app.route("/")
def home():
    return "Backend is running."


@app.route("/api/process", methods=["POST"])
def process_media():
    data = request.get_json()
    source_url = data.get("url")
    target_format = data.get("format")

    if not source_url or target_format not in ["mp4", "mp3"]:
        return jsonify({"error": "Invalid parameters"}), 400

    unique_id = str(uuid.uuid4())
    output_template = os.path.join(APP_TEMP_DIR, f"{unique_id}_%(title)s.%(ext)s")

    # yt-dlp options
    ydl_opts = {
        "outtmpl": output_template,
        "quiet": True,
        "noplaylist": True,
        "cookies": COOKIES_PATH,          # <── 核心：加入 cookies！
        "merge_output_format": "mp4",
    }

    # mp4 設定（最安全）
    if target_format == "mp4":
        ydl_opts["format"] = "bv*+ba/best"

    # mp3 設定
    if target_format == "mp3":
        ydl_opts.update({
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        })

    final_filepath = None

    try:
        # 執行 yt-dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source_url, download=True)

        title = sanitize_filename(info.get("title", "video"))
        ext = "mp3" if target_format == "mp3" else "mp4"

        # 找到產出檔案
        for file in os.listdir(APP_TEMP_DIR):
            if file.startswith(unique_id) and file.endswith(ext):
                final_filepath = os.path.join(APP_TEMP_DIR, file)
                break

        if not final_filepath:
            raise Exception("找不到輸出檔案")

        download_name = f"{title}.{ext}"
        response = send_file(
            final_filepath,
            as_attachment=True,
            download_name=download_name
        )

        quoted = urllib.parse.quote(download_name)
        response.headers["Content-Disposition"] = (
            f"attachment; filename=\"{quoted}\"; filename*=UTF-8''{quoted}"
        )

        # 清理
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
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
