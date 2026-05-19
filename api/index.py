from flask import Flask, render_template, request, jsonify, redirect, url_for
import gspread
from google.oauth2.service_account import Credentials
import os, json
from datetime import datetime
from flask_mail import Mail, Message

app = Flask(
    __name__,
    template_folder="../templates",
    static_folder="../static"
)

# 메일 설정 (Gmail 사용)
app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME")   # 본인 Gmail
app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD")   # 앱 비밀번호
app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_USERNAME")
mail = Mail(app)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_sheet():
    creds_dict = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(os.environ.get("SPREADSHEET_ID")).sheet1
    return sheet

def init_sheet(sheet):
    """시트 헤더가 없으면 자동 생성"""
    if sheet.row_count == 0 or sheet.cell(1, 1).value != "ID":
        sheet.insert_row(
            ["ID", "제목", "작성자", "내용", "파일명", "파일URL", "날짜"],
            index=1
        )

# ───────────────────────────
# 페이지 라우트
# ───────────────────────────

@app.route("/")
def index():
    try:
        sheet = get_sheet()
        rows = sheet.get_all_records()
        posts = list(reversed(rows))  # 최신순
    except:
        posts = []
    return render_template("index.html", posts=posts)

@app.route("/write")
def write():
    return render_template("write.html")

@app.route("/post/<int:post_id>")
def post(post_id):
    try:
        sheet = get_sheet()
        rows = sheet.get_all_records()
        found = next((r for r in rows if int(r["ID"]) == post_id), None)
    except:
        found = None
    if not found:
        return "게시물을 찾을 수 없습니다.", 404
    return render_template("post.html", post=found)

@app.route("/contact")
def contact():
    return render_template("contact.html")

# ───────────────────────────
# API 라우트
# ───────────────────────────

@app.route("/api/post", methods=["POST"])
def create_post():
    try:
        title   = request.form.get("title", "").strip()
        author  = request.form.get("author", "익명").strip()
        content = request.form.get("content", "").strip()
        file    = request.files.get("file")

        if not title or not content:
            return jsonify({"success": False, "error": "제목과 내용을 입력해주세요."})

        file_name = ""
        file_url  = ""

        # 구글 드라이브 파일 업로드
        if file and file.filename:
            import io
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseUpload

            creds_dict = json.loads(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"))
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            drive_service = build("drive", "v3", credentials=creds)

            folder_id = os.environ.get("DRIVE_FOLDER_ID")  # 업로드할 드라이브 폴더 ID

            file_metadata = {
                "name": file.filename,
                "parents": [folder_id] if folder_id else []
            }
            media = MediaIoBaseUpload(
                io.BytesIO(file.read()),
                mimetype=file.content_type
            )
            uploaded = drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink"
            ).execute()

            # 파일 공개 설정 (링크 있으면 누구나 열람)
            drive_service.permissions().create(
                fileId=uploaded["id"],
                body={"type": "anyone", "role": "writer"}
            ).execute()

            file_name = file.filename
            file_url  = uploaded.get("webViewLink", "")

        # 시트에 저장
        sheet = get_sheet()
        init_sheet(sheet)
        rows = sheet.get_all_records()
        new_id = max([int(r["ID"]) for r in rows], default=0) + 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        sheet.append_row([new_id, title, author, content, file_name, file_url, timestamp])

        return jsonify({"success": True, "id": new_id})

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/mail", methods=["POST"])
def send_mail():
    try:
        data    = request.get_json()
        sender_name  = data.get("name", "익명")
        sender_email = data.get("email", "")
        subject = data.get("subject", "문의")
        body    = data.get("body", "")

        admin_email = os.environ.get("ADMIN_EMAIL")  # 받을 이메일

        msg = Message(
            subject=f"[블로그 문의] {subject}",
            recipients=[admin_email],
            body=f"보낸 사람: {sender_name} ({sender_email})\n\n{body}"
        )
        mail.send(msg)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
