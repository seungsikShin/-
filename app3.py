
import streamlit as st
import os
import smtplib
import sqlite3
import hashlib
import logging
import mimetypes
import re
import ssl
import datetime
import zipfile
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from docx import Document
from dotenv import load_dotenv

# --- 설정 및 상수 ---
BASE_FOLDER = "uploaded_files"
DB_PATH = "audit_system.db"
ZIP_FOLDER = os.path.join(BASE_FOLDER, "zips")
REQUIRED_FILES = [
    "계약서 파일", "계약 체결 관련 내부 품의서", "일상감사요청서",
    "입찰 평가표", "예산 內사용 여부", "업체 제안서",
    "계약 상대방 사업자등록증 또는 등기부등본",
    "소프트웨어 기술자 경력증명서 (해당할 경우)",
    "기타 관련 문서 (협약서, 과업지시서, 재무제표 등)"
]

# 환경 변수 로드
load_dotenv()
OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
OPENAI_ORG_ID  = st.secrets["OPENAI_ORG_ID"]
EMAIL_ADDRESS  = st.secrets["EMAIL_ADDRESS"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    filename="audit_system.log"
)
logger = logging.getLogger("audit_system")

# --- 데이터베이스 초기화 및 함수 ---

@st.experimental_singleton
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_date TEXT,
            submission_id TEXT UNIQUE,
            department TEXT,
            manager TEXT,
            phone TEXT,
            contract_name TEXT,
            contract_date TEXT,
            contract_amount TEXT,
            status TEXT,
            email_sent INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT,
            file_name TEXT,
            file_path TEXT,
            file_type TEXT,
            file_size INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS missing_file_reasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT,
            file_name TEXT,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def save_submission(info: dict):
    conn = init_db()
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO submissions
        (submission_date, submission_id, department, manager, phone,
         contract_name, contract_date, contract_amount, status, email_sent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        info["date"], info["id"], info["department"], info["manager"], info["phone"],
        info["contract_name"], info["contract_date"], info["contract_amount"],
        "접수중", 0
    ))
    conn.commit()

def save_file_record(sub_id, name, path, size):
    conn = init_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO uploaded_files
        (submission_id, file_name, file_path, file_type, file_size)
        VALUES (?, ?, ?, ?, ?)
    """, (sub_id, name, path, os.path.splitext(name)[1], size))
    conn.commit()

def save_missing_reason(sub_id, name, reason):
    conn = init_db()
    c = conn.cursor()
    c.execute("""
        INSERT INTO missing_file_reasons
        (submission_id, file_name, reason) VALUES (?, ?, ?)
    """, (sub_id, name, reason))
    conn.commit()

def update_submission_status(sub_id, status, email_sent=1):
    conn = init_db()
    c = conn.cursor()
    c.execute("""
        UPDATE submissions
        SET status = ?, email_sent = ?
        WHERE submission_id = ?
    """, (status, email_sent, sub_id))
    conn.commit()

def get_submission_info(sub_id):
    conn = init_db()
    c = conn.cursor()
    c.execute("""
        SELECT department, manager, phone, contract_name, contract_date, contract_amount
        FROM submissions WHERE submission_id = ?
    """, (sub_id,))
    row = c.fetchone()
    if row:
        return {
            "department": row[0],
            "manager": row[1],
            "phone": row[2],
            "contract_name": row[3],
            "contract_date": row[4],
            "contract_amount": row[5]
        }
    return {}

def get_clean_answer_from_gpts(question: str):
    # 기존 구현 함수 그대로 사용
    # ...
    return "[예시 응답]", True  # 테스트용


# --- GPT 보고서 및 이메일 --- 

def generate_report_with_gpt(data: dict) -> str:
    prompt = f"""
당신은 일상감사 실무자의 업무를 보조하는 AI 감사 도우미입니다.
- 접수 ID: {data['id']}
- 접수 부서: {data['department']}
- 담당자: {data['manager']} ({data['phone']})
- 계약명: {data['contract_name']}
- 계약 체결일: {data['contract_date']}
- 계약금액: {data['contract_amount']}
- 제출된 자료: {', '.join(data.get('uploaded_files', [])) or '없음'}
- 누락된 자료 및 사유:
{"".join([f"- {f}:{r}\n" for f, r in data.get("missing", [])])}
위 정보를 바탕으로 일상감사 보고서 초안을 작성해 주세요.
"""
    answer, success = get_clean_answer_from_gpts(prompt)
    if not success:
        raise RuntimeError("GPT 보고서 생성 실패")
    doc = Document()
    doc.add_heading("일상감사 보고서 초안", level=0)
    for line in answer.splitlines():
        doc.add_paragraph(line)
    rpt_dir = os.path.join(BASE_FOLDER, "draft_reports")
    os.makedirs(rpt_dir, exist_ok=True)
    path = os.path.join(rpt_dir, f"report_{data['id']}.docx")
    doc.save(path)
    return path

def send_email(subject, body, to_addr, attachments=None):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    for fpath in attachments or []:
        with open(fpath, "rb") as f:
            part = MIMEApplication(f.read(), Name=os.path.basename(fpath))
        part["Content-Disposition"] = f'attachment; filename="{os.path.basename(fpath)}"'
        msg.attach(part)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as server:
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        logger.error(f"Email error: {e}")
        return False

# --- 파일 처리 헬퍼 ---

def validate_and_save_file(uploaded, sub_id, folder):
    if not uploaded:
        return None
    safe_name = re.sub(r"[^\w\s.-]", "", uploaded.name).replace(" ", "_")
    dest = os.path.join(folder, safe_name)
    with open(dest, "wb") as f:
        f.write(uploaded.getbuffer())
    save_file_record(sub_id, uploaded.name, dest, uploaded.size)
    return dest

# --- Streamlit UI 로직 ---

def main():
    st.set_page_config(page_title="일상감사 접수 시스템", layout="wide")
    today = datetime.datetime.now().strftime("%Y%m%d")
    # 폴더 생성
    daily_folder = os.path.join(BASE_FOLDER, today)
    os.makedirs(daily_folder, exist_ok=True)

    # submission_id 초기화
    if "submission_id" not in st.session_state:
        st.session_state["submission_id"] = f"AUDIT-{today}-{hashlib.md5(today.encode()).hexdigest()[:6]}"

    # 사이드바 메뉴
    menu = st.sidebar.radio("메뉴 선택", ["파일 업로드", "접수 완료"], index=0, key="menu")

    if menu == "파일 업로드":
        st.header("📤 일상감사 파일 업로드")
        # 접수 정보 입력
        dept = st.text_input("접수부서", key="dept")
        mgr  = st.text_input("담당자", key="mgr")
        phone= st.text_input("전화번호", key="phone")
        cn   = st.text_input("계약명", key="cn")
        cd   = st.text_input("계약 체결일", key="cd")
        ca   = st.text_input("계약금액", key="ca")
        if st.button("접수 정보 저장"):
            info = dict(
                date=today, id=st.session_state["submission_id"],
                department=dept, manager=mgr, phone=phone,
                contract_name=cn, contract_date=cd, contract_amount=ca
            )
            save_submission(info)
            st.success("✅ 접수 정보가 저장되었습니다.")

        st.markdown("---")
        # 파일 업로드 및 사유 입력
        conn = init_db()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM uploaded_files WHERE submission_id=?", (st.session_state["submission_id"],))
        up_cnt = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM missing_file_reasons WHERE submission_id=?", (st.session_state["submission_id"],))
        miss_cnt = c.fetchone()[0]
        complete_cnt = up_cnt + miss_cnt

        for f in REQUIRED_FILES:
            uploaded = st.file_uploader(f, key=f)
            if uploaded:
                path = validate_and_save_file(uploaded, st.session_state["submission_id"], daily_folder)
                if path:
                    st.success(f"✅ {f} 업로드 완료")
            else:
                reason = st.text_input(f"{f} 미제출 사유", key=f+"_reason")
                if reason:
                    save_missing_reason(st.session_state["submission_id"], f, reason)
                    st.info(f"📝 {f} 사유 저장됨")

        st.progress(complete_cnt / len(REQUIRED_FILES))
        st.info(f"진행 상황: {complete_cnt}/{len(REQUIRED_FILES)} 완료")

        if complete_cnt >= len(REQUIRED_FILES) and st.button("다음 단계: 접수 완료"):
            st.session_state["menu"] = "접수 완료"
            st.experimental_rerun()

    else:
        st.header("✅ 일상감사 접수 완료")
        sub_id = st.session_state["submission_id"]
        info = get_submission_info(sub_id)

        # 업로드 및 누락 목록 조회
        conn = init_db()
        c = conn.cursor()
        c.execute("SELECT file_name, file_path FROM uploaded_files WHERE submission_id=?", (sub_id,))
        uploaded_db = c.fetchall()
        c.execute("SELECT file_name, reason FROM missing_file_reasons WHERE submission_id=?", (sub_id,))
        missing_db = c.fetchall()

        st.markdown("#### 업로드된 파일")
        for fn, _ in uploaded_db:
            st.success(f"✅ {fn}")

        if missing_db:
            st.markdown("#### 누락된 파일 및 사유")
            for fn, rs in missing_db:
                st.info(f"📝 {fn}: {rs}")

        # 이메일 발송
        recipient = st.text_input("수신자 이메일", value=EMAIL_ADDRESS)
        subject = st.text_input("이메일 제목", value=f"일상감사 접수: {sub_id}")
        addition = st.text_area("추가 메시지", "")

        if st.button("접수 완료 및 이메일 발송"):
            # ZIP 생성
            attachments = []
            if uploaded_db:
                os.makedirs(ZIP_FOLDER, exist_ok=True)
                zip_path = os.path.join(ZIP_FOLDER, f"{sub_id}.zip")
                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for _, fp in uploaded_db:
                        zipf.write(fp, os.path.basename(fp))
                attachments.append(zip_path)
            # GPT 보고서 생성
            data = {
                "id": sub_id,
                **info,
                "uploaded_files": [fn for fn, _ in uploaded_db],
                "missing": missing_db
            }
            try:
                report_path = generate_report_with_gpt(data)
                attachments.append(report_path)
            except Exception as e:
                st.error("GPT 보고서 생성에 실패했습니다.")
                logger.error(e)

            # 본문 작성
            body = f"일상감사 접수 ID: {sub_id}\n접수일: {datetime.datetime.now().strftime('%Y-%m-%d')}\n\n"
            if addition:
                body += f"{addition}\n\n"
            body += "업로드된 파일:\n" + "\n".join(f"- {fn}" for fn, _ in uploaded_db) + "\n\n"
            if missing_db:
                body += "누락 파일 및 사유:\n" + "\n".join(f"- {fn} ({rs})" for fn, rs in missing_db) + "\n"

            # 이메일 전송
            if send_email(subject, body, recipient, attachments):
                update_submission_status(sub_id, "접수완료", 1)
                st.success("📧 이메일이 성공적으로 발송되었습니다!")
            else:
                st.error("❌ 이메일 발송에 실패했습니다.")

if __name__ == "__main__":
    main()
