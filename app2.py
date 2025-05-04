import streamlit as st
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import datetime
import requests
import json
from dotenv import load_dotenv
import sqlite3
import hashlib
import logging
import mimetypes
import re
import ssl
from typing import List, Dict, Optional, Tuple, Any

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='audit_system.log'
)
logger = logging.getLogger('audit_system')

# 환경 변수 로드 (.env 파일에서 민감한 정보 불러오기)
load_dotenv()

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
        
        # 질의응답 내역 테이블 생성
        c.execute('''
        CREATE TABLE IF NOT EXISTS qa_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id TEXT,
            question TEXT,
            answer TEXT,
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

# 파일을 저장할 폴더 경로
base_folder = "uploaded_files"
if not os.path.exists(base_folder):
    os.makedirs(base_folder)

# 업로드할 날짜 정보
upload_date = datetime.datetime.now().strftime("%Y%m%d")
today_folder = os.path.join(base_folder, upload_date)
if not os.path.exists(today_folder):
    os.makedirs(today_folder)

# 고유한 제출 ID 생성 (초기값)
submission_id = f"AUDIT-{upload_date}-{hashlib.md5(str(datetime.datetime.now()).encode()).hexdigest()[:6]}"

# 필수 업로드 파일 목록 (누락된 파일 체크용)
required_files = [
    "계약서 파일",
    "계약 체결 관련 내부 품의서",
    "일상감사요청서",
    "입찰 평가표",
    "예산 內사용 여부",
    "제안요청서",
    "계약 상대방 사업자등록증 또는 등기부등본",
    "소프트웨어 기술자 경력증명서 (해당할 경우)",
    "기타 관련 문서 (협약서, 과업지시서 등)"
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
    """
    업로드된 파일을 저장합니다.
    
    Args:
        uploaded_file: 업로드된 파일 객체
        folder_path: 저장할 폴더 경로
        
    Returns:
        저장된 파일 경로 또는 None (오류 발생 시)
    """
    try:
        if uploaded_file is not None:
            # 파일명 보안 처리 (특수문자 제거)
            safe_filename = re.sub(r'[^\w\s.-]', '', uploaded_file.name)
            safe_filename = safe_filename.replace(' ', '_')
            
            # 중복 파일명 처리
            file_path = os.path.join(folder_path, safe_filename)
            counter = 1
            while os.path.exists(file_path):
                name, ext = os.path.splitext(safe_filename)
                file_path = os.path.join(folder_path, f"{name}_{counter}{ext}")
                counter += 1
                
            # 파일 저장
            with open(file_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
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
    누락된 파일의 사유를 데이터베이스에 저장합니다.
    
    Returns:
        성공 여부
    """
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
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

# 데이터베이스에 질의응답 내역 저장
def save_qa_to_db(submission_id, question, answer) -> bool:
    """
    질의응답 내역을 데이터베이스에 저장합니다.
    
    Returns:
        성공 여부
    """
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute('''
        INSERT INTO qa_records (submission_id, question, answer)
        VALUES (?, ?, ?)
        ''', (submission_id, question, answer))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"DB 질의응답 저장 오류: {str(e)}")
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
def get_answer_from_custom_gpts(question: str) -> Tuple[str, bool]:
    """
    OpenAI GPTs (Assistants API)로 질문에 답변합니다.
    """
    try:
        import time  # 시간 대기용

        # OpenAI GPTs 관련 정보
        assistant_id = "asst_oTip4nhZNJHinYxehJ7itwG9"
        thread_id = "thread_fELywv3yHxSmzKhd31WumcgT"

        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "OpenAI-Organization": openai_org_id,
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2"
        }

        # 1. 메시지를 해당 thread에 추가
        message_endpoint = f"https://api.openai.com/v1/threads/{thread_id}/messages"
        message_payload = {
            "role": "user",
            "content": question
        }
        message_response = requests.post(message_endpoint, headers=headers, json=message_payload)
        if message_response.status_code != 200:
            return f"[1단계 실패] 메시지 추가 오류: {message_response.text}", False

        # 2. Run 실행
        run_endpoint = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        run_payload = {
            "assistant_id": assistant_id
        }
        run_response = requests.post(run_endpoint, headers=headers, json=run_payload)
        if run_response.status_code != 200:
            return f"[2단계 실패] 실행 오류: {run_response.text}", False

        run_id = run_response.json()["id"]

        # 3. Run 상태 확인 (폴링)
        run_status = "queued"
        while run_status in ["queued", "in_progress"]:
            status_check = requests.get(f"{run_endpoint}/{run_id}", headers=headers)
            if status_check.status_code != 200:
                return f"[3단계 실패] 상태 확인 오류: {status_check.text}", False
            run_status = status_check.json().get("status", "")
            if run_status == "completed":
                break
            elif run_status == "failed":
                return "[3단계 실패] GPT 실행 실패", False
            time.sleep(1.5)

        # 4. 답변 가져오기
        response = requests.get(message_endpoint, headers=headers)
        if response.status_code != 200:
            return "[4단계 실패] 메시지 조회 오류", False

        messages = response.json().get("data", [])
        for msg in reversed(messages):
            if msg["role"] == "assistant":
                return msg["content"], True

        return "[4단계 실패] 어시스턴트 응답 없음", False

    except Exception as e:
        logger.error(f"커스텀 GPT 호출 오류: {str(e)}")
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

# Streamlit UI 구성 - 사용자 경험 개선
st.set_page_config(
    page_title="일상감사 접수 시스템",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 사이드바 메뉴 - 순서 변경
st.sidebar.title("📋 일상감사 접수 시스템")
st.sidebar.info(f"접수 ID: {submission_id}")
st.sidebar.markdown("---")
menu = st.sidebar.radio(
    "메뉴 선택",
    ["질의응답", "파일 업로드", "접수 완료"]  # 질의응답을 첫 번째로 이동
)

# 업로드된 파일 및 사유를 관리할 딕셔너리
uploaded_files = {}
missing_files = []
reasons = {}

# 파일 업로드 페이지 - menu 변수가 정의된 후에 사용
if menu == "파일 업로드":
    st.title("📤 일상감사 파일 업로드")
    
    # 접수 정보 입력 섹션 추가
    st.markdown("### 접수 정보")
    
    # 두 개의 열로 나누어 정보 입력 필드 배치
    col1, col2 = st.columns(2)
    
    with col1:
        department = st.text_input("접수부서", key="department")
        manager = st.text_input("담당자", key="manager")
        phone = st.text_input("전화번호", key="phone")
    
    with col2:
        contract_name = st.text_input("계약명", key="contract_name")
        contract_date = st.text_input("계약 체결일(예상)", key="contract_date")
        
        # 계약금액 입력 (텍스트 입력으로 변경)
        contract_amount_str = st.text_input("계약금액", value="0", key="contract_amount")
        
        # 쉼표 제거 후 숫자로 변환 시도
        try:
            contract_amount = int(contract_amount_str.replace(',', ''))
            # 다시 형식화하여 저장
            contract_amount_formatted = f"{contract_amount:,}"
        except ValueError:
            if contract_amount_str:
                st.error("계약금액은 숫자만 입력해주세요.")
            contract_amount_formatted = contract_amount_str
    
    # 접수 ID 생성 - 부서명 포함
    if department:
        # 부서명의 첫 글자만 추출하여 ID에 포함
        dept_code = department[:3]
        submission_id = f"AUDIT-{upload_date}-{dept_code}"
    
    # 접수 ID 표시
    st.info(f"접수 ID: {submission_id}")
    st.markdown("---")
    
    # 접수 정보 저장
    if all([department, manager, phone, contract_name, contract_date, contract_amount_str]):
        # 데이터베이스에 접수 정보 저장 함수 호출
        save_submission_with_info(submission_id, department, manager, phone, contract_name, contract_date, contract_amount_formatted)
    
    st.markdown("필요한 파일을 업로드하거나, 해당 파일이 없는 경우 사유를 입력해주세요.")
    
    # 진행 상황 표시
    progress_container = st.container()
    progress_bar = st.progress(0)
    total_files = len(required_files)
    uploaded_count = 0
    
    # 각 파일에 대한 업로드 칸을 생성하고 체크 표시 및 사유 입력 받기
    for idx, file in enumerate(required_files):
        st.markdown(f"### {idx+1}. {file}")
        col1, col2 = st.columns([3, 1])
        
        with col1:
            uploaded_files[file] = st.file_uploader(
                f"📄 {file} 업로드", 
                type=None,  # None으로 설정하여 모든 파일 타입 허용
                key=f"uploader_{file}"
            )
        
        with col2:
            if uploaded_files[file]:
                # 파일 검증
                is_valid, message = validate_file(uploaded_files[file])
                
                if is_valid:
                    # 파일 저장
                    file_path = save_uploaded_file(uploaded_files[file], today_folder)
                    if file_path:
                        # 데이터베이스에 파일 정보 저장
                        file_type = os.path.splitext(uploaded_files[file].name)[1]
                        save_file_to_db(
                            submission_id, 
                            uploaded_files[file].name, 
                            file_path, 
                            file_type, 
                            uploaded_files[file].size
                        )
                        st.success(f"✅ 업로드 완료")
                        uploaded_count += 1
                else:
                    st.error(message)
                    uploaded_files[file] = None
            else:
                missing_files.append(file)
                reasons[file] = st.text_input(
                    f"{file} 업로드하지 않은 이유", 
                    key=f"reason_{file}",
                    help="파일을 업로드하지 않는 경우 반드시 사유를 입력해주세요."
                )
                if reasons[file]:
                    # 데이터베이스에 누락 사유 저장
                    save_missing_reason_to_db(submission_id, file, reasons[file])
                    st.info("사유가 저장되었습니다.")
                    uploaded_count += 1
        
        st.markdown("---")
        
        # 진행 상황 업데이트
        progress_bar.progress(uploaded_count / total_files)
    
    progress_container.info(f"진행 상황: {uploaded_count}/{total_files} 완료")
    
    # 다음 단계로 버튼
    if st.button('다음 단계: 접수 완료', key='next_to_complete'):
        st.session_state['menu'] = '접수 완료'
        st.rerun()


# 질의응답 페이지
elif menu == "질의응답":
    st.title("💬 일상감사 질의응답 시스템 GPT")
    st.markdown("일상감사 접수전, 질문이 있으시면 아래에 입력해주세요.")
    
    # 이전 질의응답 기록 표시
    conn = sqlite3.connect('audit_system.db')
    c = conn.cursor()
    c.execute("SELECT question, answer FROM qa_records WHERE submission_id = ? ORDER BY created_at DESC", (submission_id,))
    qa_records = c.fetchall()
    conn.close()
    
    if qa_records:
        st.markdown("### 이전 질의응답 기록")
        for q, a in qa_records:
            with st.expander(f"Q: {q[:50]}..."):
                st.markdown(f"**질문:** {q}")
                st.markdown(f"**답변:** {a}")
    
    # 사용자 질문 입력 받기
    user_question = st.text_area("질문을 입력하세요:", height=100)
                                
    def extract_clean_text_from_gpts_response(response_text: str) -> str:
        return re.sub(r"【.*?†.*?】", "", response_text).strip()
    # 답변 받기 버튼
    if st.button("답변 받기"):
        if user_question:
            with st.spinner("답변을 생성 중입니다..."):
                answer, success = get_answer_from_custom_gpts(user_question)
        
                if success:
                    st.markdown("### 답변")
                    clean_answer = extract_clean_text_from_gpts_response(answer)  # 출처 제거
                    st.write(clean_answer)

                    # 데이터베이스에는 원문 answer를 저장 (필요시 clean_answer로 바꿔도 됨)
                    save_qa_to_db(submission_id, user_question, answer)
                else:
                    st.error(f"답변 생성 중 오류가 발생했습니다: {answer}")
        else:
            st.warning("질문을 입력해 주세요.")
    
    # 다음 단계로 버튼
    col1, col2 = st.columns(2)
    with col1:
        if st.button('다음 단계: 파일 업로드', key='next_to_upload'):
            st.session_state['menu'] = '파일 업로드'
            st.rerun()



# 접수 완료 페이지
elif menu == "접수 완료":
    st.title("✅ 일상감사 접수 완료")
    
    # 접수 내용 요약
    st.markdown("### 접수 내용 요약")
    
    # 업로드된 파일 목록
    uploaded_file_list = []
    conn = sqlite3.connect('audit_system.db')
    c = conn.cursor()
    c.execute("SELECT file_name, file_path FROM uploaded_files WHERE submission_id = ?", (submission_id,))
    uploaded_db_files = c.fetchall()
    
    if uploaded_db_files:
        st.markdown("#### 업로드된 파일")
        for file_name, file_path in uploaded_db_files:
            st.success(f"✅ {file_name}")
            uploaded_file_list.append(file_path)
    
    # 누락된 파일 및 사유
    c.execute("SELECT file_name, reason FROM missing_file_reasons WHERE submission_id = ?", (submission_id,))
    missing_db_files = c.fetchall()
    
    if missing_db_files:
        st.markdown("#### 누락된 파일 및 사유")
        for file_name, reason in missing_db_files:
            st.info(f"📝 {file_name}: {reason}")
    
    # 질의응답 내용
    c.execute("SELECT question, answer FROM qa_records WHERE submission_id = ?", (submission_id,))
    qa_db_records = c.fetchall()
    conn.close()
    
    if qa_db_records:
        st.markdown("#### 질의응답 내용")
        for question, answer in qa_db_records:
            with st.expander(f"Q: {question[:50]}..."):
                st.markdown(f"**질문:** {question}")
                st.markdown(f"**답변:** {answer}")
    
    # 누락된 파일 확인
    current_missing_files = []
    for file in required_files:
        file_uploaded = any(file == f_name for f_name, _ in uploaded_db_files)
        file_reason_given = any(file == f_name for f_name, _ in missing_db_files)
        
        if not file_uploaded and not file_reason_given:
            current_missing_files.append(file)
    
    # 이메일 발송 섹션
    st.markdown("### 이메일 발송")
    
    # 수신자 이메일 주소 입력 (기본값 사용 가능)
    recipient_email = st.text_input("수신자 이메일 주소", value=to_email)
    
    # 이메일 제목 및 추가 메시지
    email_subject = st.text_input("이메일 제목", value=f"일상감사 접수: {submission_id}")
    additional_message = st.text_area("추가 메시지", value="")
    
    # 접수 완료 버튼
# 접수 완료 버튼
if st.button('접수 완료 및 이메일 발송'):
    # 누락된 파일이 있고 사유도 입력되지 않은 경우, 이메일 발송하지 않고 경고 메시지 출력
    if current_missing_files:
        st.warning(f"누락된 파일: {', '.join(current_missing_files)}. 업로드 또는 사유를 입력해 주세요.")
    else:
        # 질의응답 내역을 파일로 저장
        qa_file_path = None
        if qa_db_records:
            qa_text = f"# 일상감사 질의응답 내역 (접수 ID: {submission_id})\n\n"
            for question, answer in qa_db_records:
                qa_text += f"## 질문:\n{question}\n\n"
                qa_text += f"## 답변:\n{answer}\n\n---\n\n"
            
            # 질의응답 파일 저장
            qa_folder = os.path.join(base_folder, "qa_records")
            if not os.path.exists(qa_folder):
                os.makedirs(qa_folder)
            
            qa_file_path = os.path.join(qa_folder, f"질의응답_{submission_id}.txt")
            with open(qa_file_path, "w", encoding="utf-8") as f:
                f.write(qa_text)
            
            # 질의응답 내역 다운로드 버튼 제공
            st.download_button(
                label="질의응답 내역 다운로드",
                data=qa_text,
                file_name=f"질의응답_{submission_id}.txt",
                mime="text/plain"
            )
        
        # 업로드된 파일들을 ZIP으로 압축
        zip_file_path = None
        if uploaded_file_list:
            zip_folder = os.path.join(base_folder, "zips")
            if not os.path.exists(zip_folder):
                os.makedirs(zip_folder)
            
            zip_file_path = os.path.join(zip_folder, f"일상감사_파일_{submission_id}.zip")
            
            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in uploaded_file_list:
                    if os.path.exists(file_path):
                        zipf.write(file_path, os.path.basename(file_path))
            
            # ZIP 파일 다운로드 버튼 제공
            with open(zip_file_path, "rb") as f:
                zip_data = f.read()
                st.download_button(
                    label="모든 파일 다운로드 (ZIP)",
                    data=zip_data,
                    file_name=f"일상감사_파일_{submission_id}.zip",
                    mime="application/zip"
                )
        
        # 이메일 첨부 파일 목록 준비
        email_attachments = []
        
        # ZIP 파일이 있으면 첨부
        if zip_file_path and os.path.exists(zip_file_path):
            email_attachments.append(zip_file_path)
        else:
            # ZIP 파일이 없으면 개별 파일 첨부
            email_attachments.extend(uploaded_file_list)
        
        # 질의응답 파일 첨부
        if qa_file_path and os.path.exists(qa_file_path):
            email_attachments.append(qa_file_path)
        
        # 이메일 본문 작성
        body = f"일상감사 접수 ID: {submission_id}\n"
        body += f"접수일자: {upload_date}\n\n"
        
        if additional_message:
            body += f"추가 메시지:\n{additional_message}\n\n"
        
        # 업로드된 파일 목록 추가
        body += "업로드된 파일 목록:\n"
        for file_name, _ in uploaded_db_files:
            body += f"- {file_name}\n"
        
        # 누락된 파일 및 사유 추가
        if missing_db_files:
            body += "\n누락된 파일 및 사유:\n"
            for file_name, reason in missing_db_files:
                body += f"- {file_name} (사유: {reason})\n"
        
        # 첨부 파일 안내 추가
        if zip_file_path:
            body += "\n* 업로드된 파일들이 ZIP 파일로 압축되어 첨부되어 있습니다.\n"
        if qa_file_path:
            body += "* 질의응답 내역이 첨부 파일로 포함되어 있습니다.\n"
        
        # 이메일 발송
        with st.spinner("이메일을 발송 중입니다..."):
            success, message = send_email(email_subject, body, recipient_email, email_attachments)
            
            if success:
                # 데이터베이스에 접수 상태 업데이트
                update_submission_status(submission_id, "접수완료", 1)
                st.success("일상감사 접수가 완료되었으며, 이메일 알림이 발송되었습니다!")
                
                # 접수 완료 확인서 표시
                st.markdown("### 접수 완료 확인서")
                st.markdown(f"""
                **접수 ID**: {submission_id}  
                **접수일자**: {upload_date}  
                **처리상태**: 접수완료  
                **이메일 발송**: 완료 ({recipient_email})
                """)
                
                # 다운로드 버튼 제공
                receipt_text = f"""
                일상감사 접수 확인서
                
                접수 ID: {submission_id}
                접수일자: {upload_date}
                처리상태: 접수완료
                이메일 발송: 완료 ({recipient_email})
                
                업로드된 파일 목록:
                """
                for file_name, _ in uploaded_db_files:
                    receipt_text += f"- {file_name}\n"
                
                if missing_db_files:
                    receipt_text += "\n누락된 파일 및 사유:\n"
                    for file_name, reason in missing_db_files:
                        receipt_text += f"- {file_name} (사유: {reason})\n"
                
                st.download_button(
                    label="접수 확인서 다운로드",
                    data=receipt_text,
                    file_name=f"접수확인서_{submission_id}.txt",
                    mime="text/plain"
                )
            else:
                st.error(f"이메일 발송 중 오류가 발생했습니다: {message}")

    # 이전 단계로 버튼
    if st.button('이전 단계: 질의응답', key='back_to_qa'):
        st.session_state['menu'] = '질의응답'
        st.rerun()

# 페이지 하단 정보
st.sidebar.markdown("---")
st.sidebar.info("""
© 2025 일상감사 접수 시스템
문의:  
    OKH. 감사팀
    📞 02-2009-6512/ 신승식
""")
