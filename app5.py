import streamlit as st
# ← import 바로 다음 줄에만 이것! 다른 st.* 호출 NO
st.set_page_config(
    page_title="일상감사 접수 시스템",
    page_icon="📋",
    layout="wide",
)
from dotenv import load_dotenv  
load_dotenv()
with open("system_prompt.txt", "r", encoding="utf-8") as f:
    SYSTEM_PROMPT = f.read().strip()
# 이제부터 다른 import
import os
import gc  # gc 모듈 추가
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import datetime, hashlib
import requests
import json
import sqlite3
import logging
import mimetypes
import re
import ssl
import shutil
from typing import List, Dict, Optional, Tuple, Any
from docx import Document
import zipfile

# 2) 여기서부터 Streamlit 호출 시작
today = datetime.datetime.now().strftime("%Y%m%d")
# 세션 쿠키 관리 추가
import uuid
if "uploader_reset_token" not in st.session_state:
    st.session_state["uploader_reset_token"] = str(uuid.uuid4())
# 앱 시작 시 새로운 세션 ID 생성
if "cookie_session_id" not in st.session_state:
    st.session_state["cookie_session_id"] = str(uuid.uuid4())
    
# submission_id 생성 시 쿠키 세션 ID 포함
if "submission_id" not in st.session_state:
    session_id = st.session_state["cookie_session_id"]
    st.session_state["submission_id"] = f"AUDIT-{today}-{session_id[:6]}"
submission_id = st.session_state["submission_id"]

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='audit_system.log'
)
logger = logging.getLogger('audit_system')

# 파일을 저장할 폴더 경로
import tempfile
base_folder = os.path.join(tempfile.gettempdir(), "uploaded_files")
if not os.path.exists(base_folder):
    os.makedirs(base_folder)

# 업로드할 날짜 정보
upload_date = datetime.datetime.now().strftime("%Y%m%d")
today_folder = os.path.join(base_folder, upload_date)
if not os.path.exists(today_folder):
    os.makedirs(today_folder)

session_folder = os.path.join(today_folder, st.session_state["submission_id"])
if not os.path.exists(session_folder):
    os.makedirs(session_folder)

# 세션 타임아웃 설정 (20분)
session_timeout = datetime.timedelta(minutes=20)

# 타임아웃 검사 및 세션 연장 로직
current_time = datetime.datetime.now()

if "last_session_time" not in st.session_state:
    # 최초 실행 시 기록
    st.session_state["last_session_time"] = current_time
    # 새 세션 시작 - 파일 업로더 상태 초기화
    for key in list(st.session_state.keys()):
        # uploader_reset_token은 남기고, 그 외 uploader_* 만 삭제
        if key.startswith("uploader_") and key != "uploader_reset_token":
            del st.session_state[key]
        # reason_ 접두사는 전부 삭제
        if key.startswith("reason_"):
            del st.session_state[key]
else:
    elapsed = current_time - st.session_state["last_session_time"]
    if elapsed > session_timeout:
        # 타임아웃 초과 시에만 세션 초기화
        keys_to_keep = ["cookie_session_id", "uploader_reset_token", "last_session_time"]
        for key in list(st.session_state.keys()):
            if key not in keys_to_keep:
                del st.session_state[key]
        # 새로운 submission_id 및 시간 갱신
        session_id = st.session_state["cookie_session_id"]
        st.session_state["submission_id"] = f"AUDIT-{today}-{session_id[:6]}"
        st.session_state["last_session_time"] = current_time
        # 임시 파일 폴더 정리
        if os.path.exists(session_folder):
            try:
                shutil.rmtree(session_folder)
                logger.info(f"세션 타임아웃으로 임시 파일 정리: {session_folder}")
            except Exception as e:
                logger.error(f"임시 파일 정리 오류: {e}")
        st.rerun()
# 정상 흐름 시 마지막 상호작용 시간 갱신
st.session_state["last_session_time"] = current_time

# ✅ GPT 감사보고서 docx 생성 함수
def generate_audit_report_with_gpt(submission_id, department, manager, phone, contract_name,
                                   contract_date, contract_amount, uploaded_files, missing_files_with_reasons) -> Optional[str]:
    try:
        # 제출 자료와 누락 자료를 읽기 쉬운 형식으로 변환
        uploaded_list = "\n".join([f"- {file}" for file in uploaded_files]) if uploaded_files else "없음"
        
        missing_list = ""
        if missing_files_with_reasons:
            missing_list = "\n".join([f"- {name}: {reason}" for name, reason in missing_files_with_reasons])
        else:
            missing_list = "없음"
        
        # 명확하고 상세한 지시사항 포함
        user_message = f"""
다음 정보를 기반으로, 상세하고 전문적인 일상감사 보고서를 작성해주세요:

## 계약 기본 정보
- 접수 ID: {submission_id}
- 접수 부서: {department}
- 담당자: {manager} (연락처: {phone})
- 계약명: {contract_name}
- 계약 체결일: {contract_date}
- 계약금액: {contract_amount}

## 제출된 자료
{uploaded_list}

## 누락된 자료 및 사유
{missing_list}

## 보고서 작성 지침
1. 표준 감사보고서 형식을 따르되, 각 항목은 최소 3-5문장의 상세한 분석을 포함할 것
2. 각 검토 항목은 "현황 → 규정 → 문제점 → 개선방안" 구조로 서술할 것
3. 구체적인 규정과 조항을 명확히 인용하고 그 내용을 설명할 것
4. 모든 발견사항에 그 중요도와 잠재적 영향을 평가할 것
5. 【4:1†source】와 같은 인용 표시는 포함하지 말 것
6. 예시나 가정이 아닌 제공된 정보에 기반하여 분석할 것
7. 전문적인 감사 용어와 문어체를 사용할 것
8. 각 섹션별로 충분한 상세 분석을 제공할 것
9. 볼드 처리된 키워드와 콜론(예: **계약명:**, **현황:**)을 사용하지 말고, 대신 일반 텍스트로 서술할 것

감사 전문가가 작성한 것과 같은 수준의 상세하고 전문적인 보고서를 작성해주세요.
"""
        
        # GPT 응답 가져오기
        answer, success = get_clean_answer_from_gpts(user_message)
        if not success:
            return None

        # 인용 마크 및 볼드 콜론 패턴 제거
        answer = re.sub(r'\【\d+\:\d+\†source\】', '', answer)
        answer = re.sub(r'\*\*(.*?)\:\*\*', r'\1', answer)  # **키워드:** 형태 제거
        
        document = Document()
        document.add_heading('일상감사 보고서 초안', level=0)
        
        # 보고서 내용을 적절한 형식으로 변환
        for line in answer.strip().split("\n"):
            if line.strip().startswith("# "):
                document.add_heading(line.replace("# ", "").strip(), level=1)
            elif line.strip().startswith("## "):
                document.add_heading(line.replace("## ", "").strip(), level=2)
            elif line.strip().startswith("### "):
                document.add_heading(line.replace("### ", "").strip(), level=3)
            elif line.strip().startswith("- ") or line.strip().startswith("* "):
                # 불릿 포인트 처리
                p = document.add_paragraph()
                p.style = 'List Bullet'
                p.add_run(line.strip()[2:])
            else:
                if line.strip():  # 빈 줄이 아닌 경우만 추가
                    document.add_paragraph(line.strip())

        report_folder = os.path.join(base_folder, "draft_reports")
        os.makedirs(report_folder, exist_ok=True)
        report_path = os.path.join(report_folder, f"감사보고서초안_{submission_id}.docx")
        document.save(report_path)
        return report_path

    except Exception as e:
        logger.error(f"GPT 보고서 생성 오류: {str(e)}")
        return None




# OpenAI API 정보 (하드코딩)
openai_api_key = st.secrets["OPENAI_API_KEY"]
openai_org_id  = st.secrets["OPENAI_ORG_ID"]

# 이메일 정보 (예시, 실제로 입력해 주세요)
from_email     = st.secrets["EMAIL_ADDRESS"]
from_password  = st.secrets["EMAIL_PASSWORD"]
to_email       = "1504282@okfngroup.com"         # 수신자 이메일 주소


# 데이터베이스 초기화
def init_db():
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        
        # 접수 내역 테이블 생성 - 필요한 필드 추가
        c.execute('''
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
        ''')
        
        # 파일 업로드 내역 테이블 생성
        c.execute('''
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT,
            file_name TEXT,
            file_path TEXT,
            file_type TEXT,
            file_size INTEGER,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (submission_id) REFERENCES submissions (submission_id)
        )
        ''')
        
        # 누락 파일 사유 테이블 생성
        c.execute('''
        CREATE TABLE IF NOT EXISTS missing_file_reasons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT,
            file_name TEXT,
            reason TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (submission_id) REFERENCES submissions (submission_id)
        )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("데이터베이스 초기화 완료")
        return True
    except Exception as e:
        logger.error(f"데이터베이스 초기화 오류: {str(e)}")
        return False
    
# 필수 업로드 파일 목록 (누락된 파일 체크용)
required_files = [
    "계약서 파일",
    "계약 체결 관련 내부 품의서",
    "일상감사요청서",
    "입찰 평가표",
    "예산 內사용 여부",
    "업체 제안서",
    "계약 상대방 사업자등록증 또는 등기부등본",
    "소프트웨어 기술자 경력증명서 (해당할 경우)",
    "기타 관련 문서 (협약서, 과업지시서, 재무제표 등)"
]

# 파일 검증 함수 - 모든 파일 허용
def validate_file(file) -> Tuple[bool, str]:
    """
    업로드된 파일의 유효성을 검사합니다.
    모든 파일을 허용하도록 수정됨.
    
    Args:
        file: 업로드된 파일 객체
        
    Returns:
        (유효성 여부, 오류 메시지)
    """
    try:
        # 파일이 존재하는지만 확인
        if file is not None:
            return True, "파일이 유효합니다."
        return False, "파일이 없습니다."
    except Exception as e:
        logger.error(f"파일 검증 오류: {str(e)}")
        return False, f"파일 검증 중 오류가 발생했습니다: {str(e)}"

# 파일 저장 함수
def save_uploaded_file(uploaded_file, folder_path) -> Optional[str]:
    try:
        if uploaded_file is not None:
            # 파일명 보안 처리 (특수문자 제거)
            safe_filename = re.sub(r"[^\w\s.-]", "", uploaded_file.name)
            safe_filename = safe_filename.replace(" ", "_")
            
            # 세션 폴더에 저장하도록 변경
            file_path = os.path.join(session_folder, safe_filename)
            counter = 1
            while os.path.exists(file_path):
                name, ext = os.path.splitext(safe_filename)
                file_path = os.path.join(session_folder, f"{name}_{counter}{ext}")
                counter += 1
            
            # 청크 단위로 파일 저장하여 메모리 효율성 개선
            CHUNK_SIZE = 1024 * 1024  # 1MB 단위로 처리
            with open(file_path, "wb") as f:
                buffer = uploaded_file.read(CHUNK_SIZE)
                while len(buffer) > 0:
                    f.write(buffer)
                    buffer = uploaded_file.read(CHUNK_SIZE)
            
            logger.info(f"파일 저장 성공: {file_path}")
            return file_path
        return None
    except Exception as e:
        logger.error(f"파일 저장 오류: {str(e)}")
        st.error(f"파일 저장 중 오류가 발생했습니다: {str(e)}")
        return None

# 데이터베이스에 파일 정보 저장
def save_file_to_db(submission_id, file_name, file_path, file_type, file_size) -> bool:
    """
    업로드된 파일 정보를 데이터베이스에 저장합니다.
    
    Returns:
        성공 여부
    """
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute('''
        INSERT INTO uploaded_files (submission_id, file_name, file_path, file_type, file_size)
        VALUES (?, ?, ?, ?, ?)
        ''', (submission_id, file_name, file_path, file_type, file_size))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB 파일 저장 오류: {str(e)}")
        return False

# 데이터베이스에 누락 파일 사유 저장
def save_missing_reason_to_db(submission_id, file_name, reason) -> bool:
    """
    누락된 파일 사유를 중복 없이 DB에 저장합니다.
    """
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        # 이미 같은 레코드가 있으면 삽입 안 함
        c.execute(
            "SELECT 1 FROM missing_file_reasons WHERE submission_id = ? AND file_name = ?",
            (submission_id, file_name)
        )
        if c.fetchone():
            conn.close()
            return True

        # 신규 레코드만 삽입
        c.execute('''
            INSERT INTO missing_file_reasons (submission_id, file_name, reason)
            VALUES (?, ?, ?)
        ''', (submission_id, file_name, reason))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB 사유 저장 오류: {str(e)}")
        return False

# 데이터베이스에 접수 내역 저장 (접수 정보 포함)
def save_submission_with_info(submission_id, department, manager, phone, contract_name, contract_date, contract_amount, status="접수중", email_sent=0) -> bool:
    """
    접수 내역과 추가 정보를 데이터베이스에 저장합니다.
    
    Returns:
        성공 여부
    """
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute('''
        INSERT OR REPLACE INTO submissions
        (submission_date, submission_id, department, manager, phone, contract_name, contract_date, contract_amount, status, email_sent)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (upload_date, submission_id, department, manager, phone, contract_name, contract_date, contract_amount, status, email_sent))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB 접수 내역 저장 오류: {str(e)}")
        return False

# 데이터베이스에서 접수 내역 업데이트
def update_submission_status(submission_id, status, email_sent=1) -> bool:
    """
    접수 내역의 상태를 업데이트합니다.
    
    Returns:
        성공 여부
    """
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute('''
        UPDATE submissions
        SET status = ?, email_sent = ?
        WHERE submission_id = ?
        ''', (status, email_sent, submission_id))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB 접수 상태 업데이트 오류: {str(e)}")
        return False

# OpenAI API를 사용하여 질문에 답변하는 함수
def get_clean_answer_from_gpts(question: str) -> Tuple[str, bool]:
    """
    Assistant GPTs API v2 기반 GPT에게 질문을 보내고,
    최종 응답 텍스트만 추출해서 반환합니다.
    """
    try:
        import time

        assistant_id = "asst_oTip4nhZNJHinYxehJ7itwG9"

        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "OpenAI-Organization": openai_org_id,
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2"
        }
        # 1. 새 스레드 생성
        thread_url = "https://api.openai.com/v1/threads"
        thread_response = requests.post(thread_url, headers=headers)
        if thread_response.status_code != 200:
            return f"[스레드 생성 실패] {thread_response.text}", False
        
        thread_id = thread_response.json()["id"]
        
        # 1. 메시지를 해당 thread에 추가
        message_url = f"https://api.openai.com/v1/threads/{thread_id}/messages"
        add_msg = {
            "role": "user",
            "content": question
        }
        msg_response = requests.post(message_url, headers=headers, json=add_msg)
        if msg_response.status_code != 200:
            return f"[메시지 추가 실패] {msg_response.text}", False

        # 2. GPT 실행 요청 (Run 생성)
        run_url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        run_response = requests.post(run_url, headers=headers, json={"assistant_id": assistant_id})
        if run_response.status_code != 200:
            return f"[실행 실패] {run_response.text}", False

        run_id = run_response.json()["id"]

        # 3. 실행 상태 확인 (폴링)
        while True:
            check = requests.get(f"{run_url}/{run_id}", headers=headers).json()
            if check["status"] == "completed":
                break
            elif check["status"] == "failed":
                return "[실행 중 실패] GPT 실행 실패", False
            time.sleep(1.5)

        # 4. 메시지 목록 조회 후 마지막 assistant 메시지의 텍스트 추출
        msgs = requests.get(message_url, headers=headers).json()["data"]
        for msg in reversed(msgs):
            if msg.get("role") == "assistant":
                for content in msg.get("content", []):
                    if content.get("type") == "text":
                        return content["text"]["value"].strip(), True

        return "[응답 없음] assistant 메시지를 찾을 수 없습니다.", False

    except Exception as e:
        return f"[예외 발생] {str(e)}", False
        
# 이메일 발송 함수 (보안 강화)
def send_email(subject, body, to_email, attachments=None) -> Tuple[bool, str]:
    """
    이메일을 발송합니다. SSL/TLS 보안 연결을 사용합니다.
    
    Args:
        subject: 이메일 제목
        body: 이메일 본문
        to_email: 수신자 이메일
        attachments: 첨부 파일 경로 목록
        
    Returns:
        (성공 여부, 메시지)
    """
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 465  # SSL 포트 사용
        
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        
        # 본문 추가
        msg.attach(MIMEText(body, "plain", "utf-8"))
        
        # 첨부 파일 추가
        if attachments:
            for file_path in attachments:
                if os.path.exists(file_path):
                    # 파일 타입 감지
                    content_type, encoding = mimetypes.guess_type(file_path)
                    if content_type is None:
                        content_type = 'application/octet-stream'
                    main_type, sub_type = content_type.split('/', 1)
                    
                    with open(file_path, "rb") as file:
                        part = MIMEApplication(file.read(), Name=os.path.basename(file_path))
                    part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                    msg.attach(part)
        
        # SSL 보안 연결로 SMTP 서버 연결 및 이메일 발송
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(from_email, from_password)
            server.sendmail(from_email, to_email, msg.as_string())
        
        logger.info(f"이메일 발송 성공: {subject}")
        return True, "이메일이 성공적으로 발송되었습니다."
    except smtplib.SMTPAuthenticationError:
        error_msg = "이메일 인증 오류: 이메일 계정과 비밀번호를 확인해주세요."
        logger.error(error_msg)
        return False, error_msg
    except smtplib.SMTPException as e:
        error_msg = f"SMTP 오류: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"이메일 발송 오류: {str(e)}"
        logger.error(error_msg)
        return False, error_msg

# 데이터베이스 초기화
init_db()

# 상수 정의
ASSISTANT_ID = "asst_FS7Vu9qyONYlq8O8Zab471Ek"  # 일상감사 시스템용 Assistant ID

# OpenAI Assistant API 연동 함수
def get_assistant_response(question: str) -> str:
    """
    OpenAI Assistants API를 사용하여 질문에 대한 응답을 생성합니다.
    """
    try:
        import time
        import requests
        
        # API 키 가져오기 (Streamlit Secrets에서)
        openai_api_key = st.secrets["OPENAI_API_KEY"]
        
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2"
        }
        
        # 1. 스레드 관리 (새 스레드 생성 또는 기존 스레드 사용)
        if "thread_id" not in st.session_state or st.session_state.thread_id is None:
            thread_url = "https://api.openai.com/v1/threads"
            thread_response = requests.post(thread_url, headers=headers)
            if thread_response.status_code != 200:
                return f"시스템 연결에 실패했습니다. 잠시 후 다시 시도해주세요."
            thread_id = thread_response.json()["id"]
            st.session_state.thread_id = thread_id
        else:
            thread_id = st.session_state.thread_id
        
        # 2. 메시지를 스레드에 추가
        message_url = f"https://api.openai.com/v1/threads/{thread_id}/messages"
        add_msg = {"role": "user", "content": question}
        msg_response = requests.post(message_url, headers=headers, json=add_msg)
        if msg_response.status_code != 200:
            return "메시지 전송에 실패했습니다. 다시 시도해주세요."
        
        # 3. 스레드 실행 - 여기서 일상감사 Assistant ID 사용
        run_url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        run_response = requests.post(
            run_url, 
            headers=headers, 
            json={"assistant_id": ASSISTANT_ID}  # 상수 사용
        )
        if run_response.status_code != 200:
            return "처리 요청에 실패했습니다."
        
        run_id = run_response.json()["id"]
        
        # 4. 실행 완료 대기 (폴링)
        while True:
            check = requests.get(f"{run_url}/{run_id}", headers=headers).json()
            if check["status"] == "completed":
                break
            elif check["status"] in ["failed", "cancelled", "expired"]:
                return f"응답 생성에 실패했습니다. 다시 시도해주세요."
            time.sleep(1)
        
        # 5. 메시지 목록 조회하여 응답 추출
        msgs = requests.get(message_url, headers=headers).json()["data"]
        for msg in msgs:
            if msg.get("role") == "assistant":
                for content in msg.get("content", []):
                    if content.get("type") == "text":
                        return content["text"]["value"].strip()
        
        return "응답을 가져올 수 없습니다."
    
    except Exception as e:
        # 오류 로깅
        print(f"Assistant 응답 오류: {str(e)}")
        return f"오류가 발생했습니다. 잠시 후 다시 시도해주세요."

# 메뉴 정의 - 기존 코드에 추가
menu_options = ["질의응답", "파일 업로드", "접수 완료"]

default_menu = st.query_params.get("menu", "질의응답")
if isinstance(default_menu, list):
    default_menu = default_menu[0]
if default_menu not in menu_options:
    default_menu = "질의응답"

# 사이드바에 메뉴 표시
menu = st.sidebar.selectbox("메뉴", menu_options, index=menu_options.index(default_menu))

# 질의응답 페이지 구현
if menu == "질의응답":
    st.title("💬 일상감사 질의응답")
    
    # 상단 설명 - 간결하게 유지
    st.markdown("""
    일상감사 접수에 관한 질문을 입력하시면 AI가 답변해 드립니다.
    """)
    
    # 채팅 컨테이너 스타일 정의 (높이 고정, 스크롤 가능)
    st.markdown("""
    <style>
    .chat-container {
        border: 1px solid #ddd;
        border-radius: 8px;
        padding: 15px;
        margin-bottom: 15px;
        height: 400px;
        overflow-y: auto;
        background-color: #f9f9f9;
    }
    .user-message {
        background-color: #e1f5fe;
        border-radius: 15px 15px 0 15px;
        padding: 10px 15px;
        margin: 5px 0;
        max-width: 80%;
        margin-left: auto;
        text-align: right;
    }
    .assistant-message {
        background-color: #f0f0f0;
        border-radius: 15px 15px 15px 0;
        padding: 10px 15px;
        margin: 5px 0;
        max-width: 80%;
        text-align: left;
    }
    .message-time {
        font-size: 0.7em;
        color: #666;
        margin-top: 5px;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 세션 상태 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant", 
            "content": "안녕하세요! 일상감사 접수에 관해 궁금한 점을 물어봐주세요.",
            "time": datetime.datetime.now().strftime("%H:%M")
        })
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
    
    # 채팅 컨테이너 생성
    chat_container = st.container()
    with chat_container:
        # 커스텀 HTML 채팅 인터페이스
        messages_html = ""
        for message in st.session_state.messages:
            role = message["role"]
            content = message["content"]
            time = message.get("time", "")
            
            if role == "user":
                messages_html += f"""
                <div style="display: flex; justify-content: flex-end;">
                    <div class="user-message">
                        {content}
                        <div class="message-time">{time}</div>
                    </div>
                </div>
                """
            else:
                messages_html += f"""
                <div style="display: flex; justify-content: flex-start;">
                    <div class="assistant-message">
                        {content}
                        <div class="message-time">{time}</div>
                    </div>
                </div>
                """
        
        # HTML 채팅 컨테이너에 메시지 표시
        st.markdown(f'<div class="chat-container">{messages_html}</div>', unsafe_allow_html=True)
    
    # 사용자 입력 처리
    if prompt := st.chat_input("질문을 입력하세요..."):
        current_time = datetime.datetime.now().strftime("%H:%M")
        
        # 사용자 메시지 저장
        st.session_state.messages.append({
            "role": "user", 
            "content": prompt,
            "time": current_time
        })
        
        # AI 응답 생성
        with st.spinner("응답 생성 중..."):
            # 응답 생성 함수 호출 - 별도의 ID 매개변수 없이 호출
            response = get_assistant_response(prompt)
            
            # 응답 저장
            st.session_state.messages.append({
                "role": "assistant", 
                "content": response,
                "time": datetime.datetime.now().strftime("%H:%M")
            })
        
        # 새로운 메시지 추가 후 페이지 리프레시
        st.rerun()
    
    # 자바스크립트로 자동 스크롤 추가
    st.markdown("""
    <script>
    function scrollToBottom() {
        const chatContainer = document.querySelector('.chat-container');
        if (chatContainer) {
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    }
    // 페이지 로드 후 자동 실행
    window.addEventListener('load', scrollToBottom);
    </script>
    """, unsafe_allow_html=True)
    
    # 하단 버튼 - 더 눈에 띄게 스타일링
    st.markdown("---")
    col1, col2 = st.columns([1, 2])
    with col1:
        st.markdown("""
        <div style="margin-top: 15px;">
            <p>다음 단계로 진행하시겠습니까?</p>
        </div>
        """, unsafe_allow_html=True)
    with col2:
        if st.button("파일 업로드 페이지로 이동", key="start_upload", 
                   use_container_width=True, type="primary"):
            # 마지막 질문/답변 저장
            if len(st.session_state.messages) >= 2:
                st.session_state["last_question"] = st.session_state.messages[-2]["content"]
                st.session_state["last_answer"] = st.session_state.messages[-1]["content"]
            st.query_params["menu"] = "파일 업로드"
            st.rerun()

elif menu == "파일 업로드":
    # 기존 파일 업로드 코드...
    pass

elif menu == "접수 완료":
    # 기존 접수 완료 코드...
    pass

# 페이지 하단 정보
st.sidebar.markdown("---")
st.sidebar.info("""
© 2025 일상감사 접수 시스템
문의:  
    OKH. 감사팀
    📞 02-2009-6512/ 신승식
""")
