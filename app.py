from flask import Flask, request, send_file, jsonify, send_from_directory
from flask_cors import CORS
import os
import uuid
import tempfile
import yt_dlp
import urllib.parse

app = Flask(__name__, static_folder=".")
CORS(app, expose_headers=["Content-Disposition"])

# 指定 Render 的正確專案路徑
BASE_DIR = "/opt/render/project/src"

# 讓前端首頁正常顯示
@app.route("/")
def home():
    return send_from_directory(BASE_DIR, "index.html")


# 暫存資料夾
TEMP_DIR = tempfile.gettempdir()
APP_TEMP_DIR = os.path.join(TEMP_DIR, 'yt_dlp_processor_temp')
if not os.path.exists(APP_TEMP_DIR):
    os.makedirs(APP_TEMP_DIR)


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

    unique_id = str(uuid.uuid4())
    base_output = os.path.join(APP_TEMP_DIR, f"{unique_id}_%(title)s.%(ext)s")

    cookies_path = os.path.join(BASE_DIR, "cookies/cookies.txt")

    ydl_opts = {
        "outtmpl": base_output,
        "quiet": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": os.path.join(BASE_DIR, "bin"),
        "cookiefile": cookies_path
    }

    if target_format == "mp4":
        ydl_opts["format"] = "bestvideo+bestaudio/best"
    else:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source_url, download=True)

        title = sanitize_filename(info.get("title", "video"))
        ext = "mp3" if target_format == "mp3" else "mp4"

        final_filepath = None
        for fname in os.listdir(APP_TEMP_DIR):
            if fname.startswith(unique_id) and fname.endswith(f".{ext}"):
                final_filepath = os.path.join(APP_TEMP_DIR, fname)

        if not final_filepath:
            raise Exception("下載後找不到檔案")

        download_name = f"{title}.{ext}"
        response = send_file(
            final_filepath,
            as_attachment=True,
            download_name=download_name,
            mimetype="video/mp4" if ext == "mp4" else "audio/mp3"
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
        return jsonify({"error": str(e)}), 500
