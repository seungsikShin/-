import streamlit as st
# ← import 바로 다음 줄에만 이것! 다른 st.* 호출 NO
st.set_page_config(
    page_title="일상감사 접수 시스템",
    page_icon="📋",
    layout="wide",
)
from dotenv import load_dotenv  
load_dotenv()
# system_prompt.txt 안전하게 읽기
try:
    with open("system_prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read().strip()
except FileNotFoundError:
    SYSTEM_PROMPT = ""
    logging.warning("system_prompt.txt 파일을 찾을 수 없습니다.")
# 이제부터 다른 import
import os
import gc  # gc 모듈 추가
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import hashlib  # datetime 제거
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
from datetime import datetime, timedelta  # ✅ timedelta 추가

# OCR 관련 라이브러리들 - 에러 방지
try:
    from pypdf import PdfReader  # 또는 PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    st.warning("PDF 처리 기능이 제한됩니다.")

try:
    from pptx import Presentation
    PPTX_AVAILABLE = True
except ImportError:
    PPTX_AVAILABLE = False
    st.warning("PowerPoint 처리 기능이 제한됩니다.")

try:
    import openpyxl
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    st.warning("Excel 처리 기능이 제한됩니다.")

import subprocess

# --- 페이지 상태 관리 변수 추가 (맨 위에)
if "page" not in st.session_state:
    st.session_state["page"] = "질의응답"

# 2) 여기서부터 Streamlit 호출 시작
today = datetime.now().strftime("%Y%m%d")
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

# 프로덕션 환경에서는 WARNING 이상만 기록
if os.getenv("ENVIRONMENT") == "production":
    logging.basicConfig(level=logging.WARNING)
else:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# 파일을 저장할 폴더 경로
import tempfile
base_folder = os.path.join(tempfile.gettempdir(), "uploaded_files")
if not os.path.exists(base_folder):
    os.makedirs(base_folder)

# 업로드할 날짜 정보
upload_date = datetime.now().strftime("%Y%m%d")
today_folder = os.path.join(base_folder, upload_date)
if not os.path.exists(today_folder):
    os.makedirs(today_folder)

session_folder = os.path.join(today_folder, st.session_state["submission_id"])
if not os.path.exists(session_folder):
    os.makedirs(session_folder)

# 세션 타임아웃 설정 (20분)
session_timeout = timedelta(minutes=20)

# 타임아웃 검사 및 세션 연장 로직
current_time = datetime.now()

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

# --- (2) 파일 내용 추출 함수들 ---
def extract_text_from_docx(file_path):
    try:
        doc = Document(file_path)
        full_text = []
        
        # 문단 텍스트 추출
        for paragraph in doc.paragraphs:
            if paragraph.text.strip():
                full_text.append(paragraph.text.strip())
        
        # 표 내용 추출
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    if cell.text.strip():
                        row_text.append(cell.text.strip())
                if row_text:
                    full_text.append(" | ".join(row_text))
        
        return '\n'.join(full_text)
    except Exception as e:
        logger.error(f"Word 파일 읽기 오류: {str(e)}")
        return f"Word 파일 읽기 실패: {str(e)}"

def extract_text_from_pdf(file_path):
    """PDF에서 텍스트 추출 (OCR 없이)"""
    if not PDF_AVAILABLE:
        return "PDF 처리 라이브러리가 설치되지 않았습니다."
    
    try:
        reader = PdfReader(file_path)
        text = ""
        for page_num, page in enumerate(reader.pages, 1):
            page_text = page.extract_text()
            if page_text and page_text.strip():
                text += f"[페이지 {page_num}]\n{page_text}\n\n"
        
        if len(text.strip()) < 50:
            return "[PDF 텍스트 추출 제한] 스캔된 이미지 PDF이거나 텍스트가 없습니다. 텍스트가 포함된 PDF를 업로드해주세요."
        
        return text.strip()
    except Exception as e:
        logger.error(f"PDF 텍스트 추출 오류: {str(e)}")
        return f"PDF 텍스트 추출 실패: {str(e)}"

def extract_text_from_powerpoint(file_path):
    """PowerPoint에서 텍스트 추출"""
    if not PPTX_AVAILABLE:
        return "PowerPoint 처리 라이브러리가 설치되지 않았습니다."
    
    try:
        prs = Presentation(file_path)
        text = ""
        
        for slide_num, slide in enumerate(prs.slides, 1):
            text += f"\n=== 슬라이드 {slide_num} ===\n"
            
            # 슬라이드의 모든 텍스트 추출
            for shape in slide.shapes:
                if hasattr(shape, "text") and shape.text.strip():
                    text += shape.text.strip() + "\n"
                
                # 표 내용 추출
                if hasattr(shape, "has_table") and shape.has_table:
                    table = shape.table
                    for row in table.rows:
                        row_text = []
                        for cell in row.cells:
                            if cell.text.strip():
                                row_text.append(cell.text.strip())
                        if row_text:
                            text += " | ".join(row_text) + "\n"
        
        return text.strip()
    except Exception as e:
        logger.error(f"PowerPoint 텍스트 추출 오류: {str(e)}")
        return f"PowerPoint 텍스트 추출 실패: {str(e)}"

def extract_text_from_excel(file_path):
    """Excel에서 텍스트 추출"""
    if not EXCEL_AVAILABLE:
        return "Excel 처리 라이브러리가 설치되지 않았습니다."
    
    try:
        workbook = openpyxl.load_workbook(file_path, data_only=True)
        text = ""
        
        for sheet_name in workbook.sheetnames:
            sheet = workbook[sheet_name]
            text += f"\n=== {sheet_name} 시트 ===\n"
            
            for row in sheet.iter_rows(values_only=True):
                row_text = []
                for cell in row:
                    if cell is not None and str(cell).strip():
                        row_text.append(str(cell).strip())
                if row_text:
                    text += " | ".join(row_text) + "\n"
        
        return text.strip()
    except Exception as e:
        logger.error(f"Excel 텍스트 추출 오류: {str(e)}")
        return f"Excel 텍스트 추출 실패: {str(e)}"

def extract_file_content(file_path):
    """파일 확장자에 따라 적절한 방법으로 내용 추출 (OCR 제외)"""
    if not os.path.exists(file_path):
        return "파일이 존재하지 않습니다."
    
    file_ext = os.path.splitext(file_path)[1].lower()
    
    try:
        if file_ext == '.docx':
            return extract_text_from_docx(file_path)
        
        elif file_ext == '.pdf':
            return extract_text_from_pdf(file_path)
        
        elif file_ext in ['.pptx', '.ppt']:
            return extract_text_from_powerpoint(file_path)
        
        elif file_ext in ['.xlsx', '.xls']:
            return extract_text_from_excel(file_path)
        
        elif file_ext == '.txt':
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        
        else:
            return f"지원하지 않는 파일 형식: {file_ext}\n지원 형식: PDF, Word(.docx), PowerPoint(.pptx), Excel(.xlsx), 텍스트(.txt)"
    
    except Exception as e:
        logger.error(f"파일 처리 오류: {file_path}, {str(e)}")
        return f"파일 읽기 실패: {str(e)}"

# --- (3) 개선된 GPT 보고서 생성 함수 ---
def improved_generate_audit_report_with_gpt(submission_id, department, manager, phone,
                                          contract_name, contract_date, contract_amount,
                                          uploaded_files, missing_files_with_reasons) -> Optional[str]:
    """개선된 감사보고서 생성 함수"""
    try:
        logger.info(f"📋 보고서 생성 시작 - ID: {submission_id}")
        
        # 1. 입력 데이터 검증
        if not submission_id:
            logger.error("❌ submission_id가 없습니다.")
            st.error("접수 ID가 없습니다.")
            return None
        
        # 2. 파일 내용 추출
        st.info("📄 업로드된 파일 내용을 분석하는 중...")
        file_contents, success_count = extract_and_validate_file_contents(submission_id)
        
        if success_count == 0:
            logger.warning("⚠️ 처리 가능한 파일이 없습니다.")
            st.warning("처리 가능한 파일이 없습니다. 텍스트 기반 문서를 업로드해주세요.")
        else:
            st.success(f"✅ {success_count}개 파일 내용 추출 완료")
        
        # 3. GPT 프롬프트 생성
        logger.info("📝 GPT 프롬프트 생성 중...")
        user_message = create_gpt_prompt(
            submission_id, department, manager, phone,
            contract_name, contract_date, contract_amount,
            file_contents
        )
        
        logger.info(f"📊 프롬프트 길이: {len(user_message)}자")
        
        # 4. GPT API 호출
        st.info("🤖 AI가 보고서를 생성하는 중...")
        answer, success = improved_get_clean_answer_from_gpts(user_message)
        
        if not success:
            logger.error(f"❌ GPT API 호출 실패: {answer}")
            st.error(f"보고서 생성 실패: {answer}")
            return None
        
        logger.info(f"✅ GPT 응답 받음: {len(answer)}자")
        st.success("🎉 AI 보고서 생성 완료!")
        
        # 5. Word 문서 생성
        logger.info("📄 Word 문서 생성 중...")
        document = Document()
        document.add_heading('일상감사 보고서 초안', level=0)
        
        # 접수 정보 표 추가
        document.add_heading('접수 정보', level=1)
        info_table = document.add_table(rows=7, cols=2)
        info_table.style = 'Table Grid'
        
        info_data = [
            ['접수번호', submission_id],
            ['계약명', contract_name or '정보 없음'],
            ['주관부서', department or '정보 없음'],
            ['담당자', f"{manager or '정보 없음'} ({phone or '정보 없음'})"],
            ['계약금액', contract_amount or '정보 없음'],
            ['계약일', contract_date or '정보 없음'],
            ['보고서 생성일', datetime.now().strftime('%Y-%m-%d %H:%M')]
        ]
        
        for i, (label, value) in enumerate(info_data):
            info_table.cell(i, 0).text = label
            info_table.cell(i, 1).text = str(value)
        
        document.add_page_break()
        
        # AI 생성 내용 추가 (구조화)
        lines = answer.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            if line.startswith('##') or line.startswith('# '):
                # 대제목
                heading_text = line.replace('#', '').strip()
                document.add_heading(heading_text, level=1)
            elif line.startswith('###'):
                # 소제목
                heading_text = line.replace('###', '').strip()
                document.add_heading(heading_text, level=2)
            elif line.startswith('- ') or line.startswith('• '):
                # 리스트 항목
                p = document.add_paragraph(style='List Bullet')
                p.add_run(line[2:].strip())
            elif line.startswith('**') and line.endswith('**'):
                # 강조 텍스트
                p = document.add_paragraph()
                p.add_run(line[2:-2]).bold = True
            else:
                # 일반 텍스트
                document.add_paragraph(line)
        
        # 6. 파일 저장
        reports_folder = os.path.join(base_folder, "draft_reports")
        os.makedirs(reports_folder, exist_ok=True)
        file_path = os.path.join(reports_folder, f"일상감사보고서_{submission_id}.docx")
        
        document.save(file_path)
        logger.info(f"✅ 보고서 저장 완료: {file_path}")
        
        if os.path.exists(file_path):
            st.success(f"📄 보고서 파일 생성 완료: {os.path.basename(file_path)}")
            return file_path
        else:
            logger.error("❌ 파일 저장 실패")
            st.error("파일 저장에 실패했습니다.")
            return None
        
    except Exception as e:
        error_msg = f"보고서 생성 중 오류 발생: {str(e)}"
        logger.error(f"❌ {error_msg}")
        logger.error(f"상세 오류: {traceback.format_exc()}")
        st.error(error_msg)
        return None

# OpenAI API 정보 (하드코딩)
openai_api_key = st.secrets["OPENAI_API_KEY"]
openai_org_id  = st.secrets["OPENAI_ORG_ID"]

# 이메일 정보 (예시, 실제로 입력해 주세요)
from_email     = st.secrets["EMAIL_ADDRESS"]
from_password  = st.secrets["EMAIL_PASSWORD"]
to_email       = "1504282@okfngroup.com"         # 수신자 이메일 주소

# 파일/사유 삭제 및 삭제 다이얼로그 함수들 (DB 초기화 바로 위에 위치)
def delete_uploaded_file(file_id, file_path):
    """업로드된 파일을 서버와 DB에서 삭제합니다."""
    try:
        # 1. 실제 파일 삭제
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.info(f"파일 삭제 완료: {file_path}")
        # 2. DB에서 삭제
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute("DELETE FROM uploaded_files WHERE id = ?", (file_id,))
        conn.commit()
        conn.close()
        logger.info(f"DB 레코드 삭제 완료: file_id={file_id}")
        return True
    except Exception as e:
        error_msg = f"파일 삭제 중 오류 발생: {str(e)}"
        st.error(error_msg)
        logger.error(error_msg)
        return False

def delete_missing_reason(submission_id, file_name):
    """누락 파일 사유를 DB에서 삭제합니다."""
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute("DELETE FROM missing_file_reasons WHERE submission_id = ? AND file_name = ?", 
                  (submission_id, file_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"사유 삭제 오류: {str(e)}")
        return False

def show_delete_confirmation(file_name, file_id, file_path):
    """삭제 확인 다이얼로그"""
    if f"confirm_delete_{file_id}" not in st.session_state:
        st.session_state[f"confirm_delete_{file_id}"] = False
    if st.session_state[f"confirm_delete_{file_id}"]:
        st.warning(f"'{file_name}' 파일을 정말 삭제하시겠습니까?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("삭제 확인", key=f"confirm_yes_{file_id}", type="primary"):
                if delete_uploaded_file(file_id, file_path):
                    st.success("파일이 삭제되었습니다.")
                    st.session_state[f"confirm_delete_{file_id}"] = False
                    st.rerun()
                else:
                    st.error("파일 삭제에 실패했습니다.")
        with col2:
            if st.button("취소", key=f"confirm_no_{file_id}"):
                st.session_state[f"confirm_delete_{file_id}"] = False
                st.rerun()
    else:
        if st.button("🗑️", key=f"delete_{file_id}", help="파일 삭제"):
            st.session_state[f"confirm_delete_{file_id}"] = True
            st.rerun()

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
    Assistant API v2를 통한 GPT 호출 (시스템 메시지 제거)
    """
    try:
        assistant_id = "asst_oTip4nhZNJHinYxehJ7itwG9"
        thread_url = "https://api.openai.com/v1/threads"
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "OpenAI-Organization": openai_org_id,
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2"
        }

        # 1) 새 스레드 생성
        thread_resp = requests.post(thread_url, headers=headers)
        if thread_resp.status_code != 200:
            logger.error(f"스레드 생성 실패: {thread_resp.text}")
            return f"[스레드 생성 실패] {thread_resp.text}", False
        
        thread_id = thread_resp.json()["id"]
        msg_url = f"{thread_url}/{thread_id}/messages"
        run_url = f"{thread_url}/{thread_id}/runs"

        # 2) ❌ 시스템 메시지 제거 (Assistant에 이미 설정됨)
        # sys_msg = {"role":"system", "content": SYSTEM_PROMPT}
        # resp = requests.post(msg_url, headers=headers, json=sys_msg)

        # 3) user 메시지만 전송
        user_msg = {"role": "user", "content": question}
        resp = requests.post(msg_url, headers=headers, json=user_msg)
        if resp.status_code != 200:
            logger.error(f"사용자 메시지 전송 실패: {resp.text}")
            return f"[사용자 메시지 전송 실패] {resp.text}", False

        # 4) ✅ 수정된 run 요청
        run_payload = {
            "assistant_id": assistant_id,
            "max_tokens": 3000,  # 보고서 생성을 위해 증가
            "temperature": 0.3   # 일관성을 위해 낮춤
        }
        
        run_resp = requests.post(run_url, headers=headers, json=run_payload)
        if run_resp.status_code != 200:
            logger.error(f"실행 요청 실패: {run_resp.text}")
            return f"[실행 요청 실패] {run_resp.text}", False
        
        run_id = run_resp.json()["id"]

        # 5) 완료 대기 (타임아웃 추가)
        import time
        max_wait_time = 90  # 90초로 증가
        wait_time = 0
        
        while wait_time < max_wait_time:
            status_resp = requests.get(f"{run_url}/{run_id}", headers=headers)
            if status_resp.status_code != 200:
                return f"[상태 확인 실패] {status_resp.text}", False
                
            status = status_resp.json()["status"]
            logger.info(f"Assistant 실행 상태: {status}")
            
            if status == "completed": 
                break
            elif status in ["failed", "cancelled", "expired"]:
                error_msg = status_resp.json().get("last_error", {})
                logger.error(f"Assistant 실행 실패: {status}, 오류: {error_msg}")
                return f"[실행 실패] 상태: {status}, 오류: {error_msg}", False
            
            time.sleep(2)
            wait_time += 2

        if wait_time >= max_wait_time:
            logger.error("Assistant 응답 타임아웃")
            return "[타임아웃] 응답 생성이 너무 오래 걸립니다.", False

        # 6) 최종 assistant 응답 추출
        msgs_resp = requests.get(msg_url, headers=headers)
        if msgs_resp.status_code != 200:
            return f"[메시지 조회 실패] {msgs_resp.text}", False
            
        msgs = msgs_resp.json()["data"]
        for msg in reversed(msgs):
            if msg.get("role") == "assistant":
                for c in msg.get("content", []):
                    if c.get("type") == "text":
                        response_text = c["text"]["value"].strip()
                        
                        # 응답 품질 검증
                        if len(response_text) < 100:
                            logger.warning(f"Assistant 응답이 너무 짧음: {len(response_text)}자")
                            return "응답이 너무 짧습니다", False
                        
                        logger.info(f"Assistant 응답 숵신 완료: {len(response_text)}자")
                        return response_text, True

        logger.error("Assistant 응답을 찾을 수 없음")
        return "[응답 없음] assistant 메시지를 찾을 수 없습니다.", False

    except Exception as e:
        logger.error(f"get_clean_answer_from_gpts 예외: {str(e)}")
        return f"[예외 발생] {str(e)}", False

# OpenAI Assistant API 연동 함수
def get_assistant_response(question: str) -> str:
    """
    OpenAI Assistants API를 사용하여 질문에 대한 응답을 생성합니다.
    """
    try:
        import time
        import re  # 정규표현식 모듈 추가
        
        # 일상감사 질의응답용 Assistant ID
        assistant_id = "asst_FS7Vu9qyONYlq8O8Zab471Ek"
        
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "OpenAI-Organization": openai_org_id,
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2"
        }
        
        # 대화 맥락 유지: thread_id 세션에 저장
        if "thread_id" not in st.session_state or st.session_state.thread_id is None:
            # 새 스레드 생성
            thread_url = "https://api.openai.com/v1/threads"
            thread_response = requests.post(thread_url, headers=headers)
            if thread_response.status_code != 200:
                return f"시스템 연결에 실패했습니다. 잠시 후 다시 시도해주세요."
            thread_id = thread_response.json()["id"]
            st.session_state.thread_id = thread_id
        else:
            thread_id = st.session_state.thread_id
        
        # 메시지 추가
        message_url = f"https://api.openai.com/v1/threads/{thread_id}/messages"
        add_msg = {
            "role": "user",
            "content": question
        }
        msg_response = requests.post(message_url, headers=headers, json=add_msg)
        if msg_response.status_code != 200:
            return "메시지 전송에 실패했습니다. 다시 시도해주세요."
        
        # 스레드 실행
        run_url = f"https://api.openai.com/v1/threads/{thread_id}/runs"
        run_response = requests.post(
            run_url, 
            headers=headers, 
            json={"assistant_id": assistant_id}
        )
        if run_response.status_code != 200:
            return "처리 요청에 실패했습니다."
        
        run_id = run_response.json()["id"]
        
        # 실행 완료 확인 (폴링)
        while True:
            check = requests.get(f"{run_url}/{run_id}", headers=headers).json()
            if check["status"] == "completed":
                break
            elif check["status"] in ["failed", "cancelled", "expired"]:
                return "응답 생성에 실패했습니다. 다시 시도해주세요."
            time.sleep(1)
        
        # 메시지 목록 조회하여 응답 추출
        msgs = requests.get(message_url, headers=headers).json()["data"]
        for msg in msgs:
            if msg.get("role") == "assistant":
                for content in msg.get("content", []):
                    if content.get("type") == "text":
                        response_text = content["text"]["value"].strip()
                        # 인용 표시 제거 - 여러 형식의 인용 마크 처리
                        cleaned_response = re.sub(r'\【.*?\】', '', response_text)
                        return cleaned_response
        
        return "응답을 가져올 수 없습니다."
    
    except Exception as e:
        logger.error(f"Assistant 응답 오류: {str(e)}")
        return f"오류가 발생했습니다. 잠시 후 다시 시도해주세요."

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

def send_email_with_attachments(to_email, subject, body, attachment_paths):
    """
    첨부 파일이 있는 이메일을 발송합니다.
    """
    try:
        smtp_server = "smtp.gmail.com"
        smtp_port = 465
        msg = MIMEMultipart()
        msg["From"] = from_email
        msg["To"] = to_email
        msg["Subject"] = subject
        # 본문 추가
        msg.attach(MIMEText(body, "plain", "utf-8"))
        # 첨부 파일 추가
        for file_path in attachment_paths:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    part = MIMEApplication(f.read(), Name=os.path.basename(file_path))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(file_path)}"'
                msg.attach(part)
        # 이메일 발송
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(smtp_server, smtp_port, context=context) as server:
            server.login(from_email, from_password)
            server.sendmail(from_email, to_email, msg.as_string())
        logger.info(f"이메일 발송 성공: {subject}")
        return True
    except Exception as e:
        logger.error(f"이메일 발송 오류: {str(e)}")
        return False

# 데이터베이스 초기화
init_db()

# 메뉴 정의
menu_options = ["질의응답", "파일 업로드", "접수 완료"]

# 쿼리 파라미터 대신 세션 상태 사용
menu = st.session_state["page"]

# 사이드바 메뉴
st.sidebar.title("📋 일상감사 접수 시스템")
st.sidebar.info(f"접수 ID: {submission_id}")
st.sidebar.markdown("---")

# 사이드바 메뉴 라디오 버튼 (원래 위치로 이동)
selected_menu = st.sidebar.radio(
    "메뉴 선택",
    menu_options,
    index=menu_options.index(menu),
    key="menu_radio"
)
if selected_menu != st.session_state["page"]:
    st.session_state["page"] = selected_menu
    st.rerun()

with st.sidebar.expander("초기화 옵션", expanded=True):
    if st.button("전체 시스템 초기화", key="btn_reset_all", use_container_width=True, type="primary"):
        try:
            # 1. 새 접수 시작 기능
            st.session_state["uploader_reset_token"] = str(uuid.uuid4())
            st.session_state["timestamp"] = datetime.now().strftime("%Y%m%d%H%M%S")
            
            # 2. 파일 업로더 캐시 초기화 기능
            st.cache_data.clear()
            
            # 3. DB 및 파일 완전 초기화 기능
            if os.path.exists('audit_system.db'):
                os.remove('audit_system.db')
            if os.path.exists(base_folder):
                shutil.rmtree(base_folder)
                
            # 세션 상태 초기화 (쿠키 ID와 업로더 토큰만 유지)
            keys_to_keep = ["cookie_session_id", "uploader_reset_token"]
            for key in list(st.session_state.keys()):
                if key not in keys_to_keep:
                    del st.session_state[key]
            
            # 새로운 submission_id 생성
            session_id = st.session_state["cookie_session_id"]
            st.session_state["submission_id"] = f"AUDIT-{today}-{session_id[:6]}"
            st.session_state["last_session_time"] = datetime.now()
            
            # 파일 업로더 관련 세션 초기화
            for key in list(st.session_state.keys()):
                if key.startswith("uploader_") and key != "uploader_reset_token":
                    del st.session_state[key]
            
            st.success("시스템이 완전히 초기화되었습니다. 새 접수가 시작됩니다.")
            st.rerun()
        except Exception as e:
            st.error(f"초기화 중 오류가 발생했습니다: {e}")

# 질의응답 페이지 - 첫 번째 페이지로 추가
if st.session_state["page"] == "질의응답":
    st.title("💬 일상감사 질의응답")
    
    st.markdown("""
    ### 일상감사 접수에 관한 질문이 있으신가요?
    아래 채팅창에 질문을 입력해주세요. AI 비서가 답변해 드립니다.
    """)
    
    # 세션 상태 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = []
        st.session_state.messages.append({
            "role": "assistant", 
            "content": "안녕하세요! 일상감사 접수에 관해 궁금한 점을 물어봐주세요.",
            "time": datetime.now().strftime("%H:%M")
        })
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = None
    
    # 이전 메시지 표시
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.write(message["content"])
    
    # 사용자 입력 처리
    if prompt := st.chat_input("질문을 입력하세요"):
        current_time = datetime.now().strftime("%H:%M")
        
        # 사용자 메시지 표시 및 저장
        st.session_state.messages.append({
            "role": "user", 
            "content": prompt,
            "time": current_time
        })
        with st.chat_message("user"):
            st.write(prompt)

        # AI 응답 생성 중 표시
        with st.chat_message("assistant"):
            with st.spinner("응답 생성 중..."):
                response = get_assistant_response(prompt)
                st.write(response)
        
        # AI 응답 저장
        st.session_state.messages.append({
            "role": "assistant", 
            "content": response,
            "time": datetime.now().strftime("%H:%M")
        })
    
    st.markdown("---")
    if st.button("다음 단계: 파일 업로드", key="next_to_upload", use_container_width=True, type="primary"):
        if len(st.session_state.messages) >= 2:
            st.session_state["last_question"] = st.session_state.messages[-2]["content"]
            st.session_state["last_answer"] = st.session_state.messages[-1]["content"]
        st.session_state["page"] = "파일 업로드"
        st.rerun()

# 파일 업로드 페이지 - elif로 변경
elif st.session_state["page"] == "파일 업로드":
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
        safe_dept = re.sub(r'[^\w]', '', department)[:6]
        st.session_state["submission_id"] = f"AUDIT-{upload_date}-{safe_dept}"
    
    # 접수 ID 표시
    sid = st.session_state.get("submission_id", submission_id)
    st.info(f"접수 ID: {sid}")
    st.markdown("---")
    
    # 접수 정보 저장
    if all([department, manager, phone, contract_name, contract_date, contract_amount_str]):
    # 데이터 저장
        save_submission_with_info(
            submission_id,
            department,
            manager,
            phone,
            contract_name,
            contract_date,
            contract_amount_formatted
        )
      
    # 필요한 파일을 업로드하거나 사유 입력 안내
    st.markdown("필요한 파일을 업로드하거나, 해당 파일이 없는 경우 사유를 입력해주세요.")
    
    # 진행 상황 표시
    progress_container = st.container()
    progress_bar = st.progress(0)
    total_files = len(required_files)
    uploaded_count = 0
    
    # 각 파일에 대한 업로드 칸을 생성하고 체크 표시 및 사유 입력 받기
    for idx, file in enumerate(required_files):
        st.markdown(f"### {idx+1}. {file}")
        # DB에서 업로드된 파일 정보 확인
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute("SELECT id, file_name, file_path FROM uploaded_files WHERE submission_id = ? AND file_name LIKE ?", 
                  (submission_id, f"%{file}%"))
        uploaded_record = c.fetchone()
        c.execute("SELECT reason FROM missing_file_reasons WHERE submission_id = ? AND file_name = ?", 
                  (submission_id, file))
        reason_record = c.fetchone()
        conn.close()
        # 1. 이미 업로드된 파일이 있는 경우 - 삭제 버튼 및 사유 삭제 버튼 포함
        if uploaded_record:
            file_id, file_name, file_path = uploaded_record
            if reason_record:
                reason = reason_record[0]
                col1, col2, col3 = st.columns([4, 1, 1])
                with col1:
                    st.success(f"✅ {file_name}")
                    st.info(f"📝 {file}: {reason}")
                with col2:
                    show_delete_confirmation(file_name, file_id, file_path)
                with col3:
                    if st.button("❌", key=f"delete_reason_{file}", help="사유 삭제"):
                        if delete_missing_reason(submission_id, file):
                            st.success("사유가 삭제되었습니다.")
                            st.rerun()
                        else:
                            st.error("사유 삭제에 실패했습니다.")
            else:
                col1, col2 = st.columns([4, 1])
                with col1:
                    st.success(f"✅ {file_name}")
                with col2:
                    show_delete_confirmation(file_name, file_id, file_path)
            uploaded_count += 1
            continue
        # 2. 사유가 입력된 경우 - 사유 삭제 버튼 포함
        elif reason_record:
            reason = reason_record[0]
            col1, col2 = st.columns([4, 1])
            with col1:
                st.info(f"📝 {file}: {reason}")
            with col2:
                if st.button("❌", key=f"delete_reason_{file}", help="사유 삭제"):
                    if delete_missing_reason(submission_id, file):
                        st.success("사유가 삭제되었습니다.")
                        st.rerun()
                    else:
                        st.error("사유 삭제에 실패했습니다.")
            uploaded_count += 1
            continue
        # 3. 신규 업로드 또는 사유 입력
        else:
            col1, col2 = st.columns([3, 1])
            with col1:
                user_key = st.session_state["cookie_session_id"]
                if "timestamp" not in st.session_state:
                    st.session_state["timestamp"] = datetime.now().strftime("%Y%m%d%H%M%S")
                timestamp = st.session_state["timestamp"]
                uploaded_file = st.file_uploader(
                    f"📄 {file} 업로드", 
                    type=None,
                    key=f"uploader_{st.session_state['uploader_reset_token']}_{file}"
                )
            with col2:
                if uploaded_file:
                    is_valid, message = validate_file(uploaded_file)
                    if is_valid:
                        file_path = save_uploaded_file(uploaded_file, session_folder)
                        if file_path:
                            file_type = os.path.splitext(uploaded_file.name)[1]
                            save_file_to_db(
                                submission_id, 
                                f"{file} - {uploaded_file.name}",
                                file_path, 
                                file_type, 
                                uploaded_file.size
                            )
                            st.success(f"✅ 업로드 완료")
                            
                            # 실시간 파일 내용 분석
                            with st.expander(f"📄 {uploaded_file.name} 내용 미리보기", expanded=False):
                                with st.spinner("파일 내용을 추출하는 중..."):
                                    extracted_content = extract_file_content(file_path)
                                    if len(extracted_content) > 1000:
                                        st.text_area(
                                            "추출된 텍스트", 
                                            extracted_content[:1000] + "\n...(내용이 길어서 일부만 표시)", 
                                            height=200
                                        )
                                    else:
                                        st.text_area("추출된 텍스트", extracted_content, height=200)
                        
                            uploaded_count += 1
                            del uploaded_file
                            gc.collect()
                            st.rerun()
                    else:
                        st.error(message)
                else:
                    reason = st.text_input(
                        f"{file} 업로드하지 않은 이유", 
                        key=f"reason_{user_key}_{timestamp}_{file}",
                        help="파일을 업로드하지 않는 경우 반드시 사유를 입력해주세요."
                    )
                    if reason:
                        if save_missing_reason_to_db(submission_id, file, reason):
                            st.info("사유가 저장되었습니다.")
                            uploaded_count += 1
                            st.rerun()

    st.markdown("---")

    # 진행 상황 업데이트
    progress_bar.progress(uploaded_count / total_files)
    progress_container.info(f"진행 상황: {uploaded_count}/{total_files} 완료")
    
    # 다음 단계로 버튼 - DB에서 확인하도록 수정
    if st.button("다음 단계: 접수 완료", key="next_to_complete"):
        # DB에서 직접 파일 및 사유 정보 확인
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        
        # 파일명에 파일 유형 포함여부 확인
        incomplete_files = []
        for req_file in required_files:
            # 업로드 파일 확인
            c.execute("SELECT COUNT(*) FROM uploaded_files WHERE submission_id = ? AND file_name LIKE ?", 
                    (submission_id, f"%{req_file}%"))
            file_count = c.fetchone()[0]
            
            # 사유 제공 확인
            c.execute("SELECT COUNT(*) FROM missing_file_reasons WHERE submission_id = ? AND file_name = ?", 
                    (submission_id, req_file))
            reason_count = c.fetchone()[0]
            
            if file_count == 0 and reason_count == 0:
                incomplete_files.append(req_file)
        
        conn.close()
        current_missing_files = incomplete_files
        
        if incomplete_files:
            st.warning("다음 파일이 필요합니다:\n- " + "\n- ".join(incomplete_files))
        else:
            st.session_state["page"] = "접수 완료"
            st.rerun()
      
# 접수완료 페이지에서 사용할 통합 함수
def integrated_completion_page():
    """통합된 접수완료 페이지 로직"""
    submission_id = st.session_state["submission_id"]
    
    # 변수 기본값 설정
    department = manager = phone = contract_name = contract_date = contract_amount = "정보 없음"
    uploaded_db_files = []
    missing_db_files = []
    
    try:
        # DB에서 정보 조회
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        
        # 접수 정보 조회
        c.execute("""
            SELECT department, manager, phone, contract_name, contract_date, contract_amount
            FROM submissions WHERE submission_id = ?
        """, (submission_id,))
        result = c.fetchone()
        
        if result:
            department, manager, phone, contract_name, contract_date, contract_amount = result
        else:
            st.warning("접수 정보를 찾을 수 없습니다. 기본값으로 진행합니다.")
        
        # 파일 정보 조회
        c.execute("SELECT file_name, file_path FROM uploaded_files WHERE submission_id = ?", 
                  (submission_id,))
        uploaded_db_files = c.fetchall() or []
        
        c.execute("SELECT file_name, reason FROM missing_file_reasons WHERE submission_id = ?", 
                  (submission_id,))
        missing_db_files = c.fetchall() or []
        
        conn.close()
        
    except Exception as e:
        st.error(f"데이터 조회 오류: {str(e)}")
        logger.error(f"접수 완료 페이지 DB 오류: {str(e)}")
    
    # 안전한 기본값 설정
    department = department or "정보 없음"
    manager = manager or "정보 없음"
    phone = phone or "정보 없음"
    contract_name = contract_name or "정보 없음"
    contract_date = contract_date or "정보 없음"
    contract_amount = contract_amount or "정보 없음"
    
    # 접수 정보 표시
    st.subheader("📄 접수 정보")
    
    # 안전한 컬럼 표시
    try:
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**접수번호:** {submission_id}")
            st.write(f"**부서:** {department}")
            st.write(f"**담당자:** {manager}")
            st.write(f"**연락처:** {phone}")
        with col2:
            st.write(f"**계약명:** {contract_name}")
            st.write(f"**계약일:** {contract_date}")
            st.write(f"**계약금액:** {contract_amount}")
    except Exception as e:
        # 컬럼 실패 시 단일 컬럼으로 표시
        st.write(f"**접수번호:** {submission_id}")
        st.write(f"**부서:** {department}")
        st.write(f"**담당자:** {manager}")
        st.write(f"**연락처:** {phone}")
        st.write(f"**계약명:** {contract_name}")
        st.write(f"**계약일:** {contract_date}")
        st.write(f"**계약금액:** {contract_amount}")
    
    st.markdown("---")
    
    # 업로드된 파일 표시
    if uploaded_db_files:
        st.subheader("📎 업로드된 파일")
        for file_name, file_path in uploaded_db_files:
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                st.success(f"✅ {file_name} ({file_size:,} bytes)")
            else:
                st.error(f"❌ {file_name} (파일을 찾을 수 없음)")
    
    # 누락된 파일 표시
    if missing_db_files:
        st.subheader("📝 누락된 파일 및 사유")
        for file_name, reason in missing_db_files:
            st.info(f"• **{file_name}**: {reason}")
    
    st.markdown("---")
    
    # 개선된 보고서 생성 섹션
    report_path = improved_report_generation_section(
        submission_id, department, manager, phone,
        contract_name, contract_date, contract_amount,
        uploaded_db_files, missing_db_files
    )
    
    st.markdown("---")
    
    # 이메일 발송 섹션
    st.subheader("📧 이메일 발송")
    
    # 이메일 본문 생성
    email_body = f"""
[감사업무접수] 계약 감사 요청

■ 접수 정보
- 접수번호: {submission_id}
- 접수부서: {department}
- 담당자: {manager} ({phone})
- 계약명: {contract_name}
- 계약일: {contract_date}
- 계약금액: {contract_amount}

■ 첨부 파일
"""
    
    # 첨부 파일 목록 생성
    email_attachments = []
    
    for file_name, file_path in uploaded_db_files:
        if os.path.exists(file_path):
            email_attachments.append(file_path)
            email_body += f"* {file_name}\n"
    
    # 보고서가 생성된 경우 첨부 파일에 추가
    if report_path and os.path.exists(report_path):
        email_attachments.append(report_path)
        email_body += f"* AI 감사보고서 초안 ({os.path.basename(report_path)})\n"
    
    # 누락 파일 정보 추가
    if missing_db_files:
        email_body += "\n■ 누락된 파일 및 사유\n"
        for file_name, reason in missing_db_files:
            email_body += f"* {file_name}: {reason}\n"
    
    email_body += f"\n접수 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    
    # 이메일 미리보기
    with st.expander("📧 이메일 내용 미리보기"):
        st.text_area("이메일 본문", email_body, height=200)
        st.write(f"**첨부 파일 수:** {len(email_attachments)}개")
    
    # 이메일 발송 버튼
    if st.button("📧 이메일 전송", type="primary", use_container_width=True):
        if not email_attachments:
            st.warning("첨부할 파일이 없습니다. 그래도 발송하시겠습니까?")
            
        with st.spinner("이메일 발송 중..."):
            try:
                success = send_email_with_attachments(
                    to_email=to_email,
                    subject=f"[감사업무접수] {contract_name} - {submission_id}",
                    body=email_body,
                    attachment_paths=email_attachments
                )
                
                if success:
                    # DB 상태 업데이트
                    update_submission_status(submission_id, "접수완료", 1)
                    st.success("✅ 이메일이 성공적으로 전송되었습니다!")
                    st.balloons()
                    
                    # 성공 정보 표시
                    st.info(f"""
                    📧 **이메일 발송 완료**
                    - 수신자: {to_email}
                    - 첨부 파일: {len(email_attachments)}개
                    - 발송 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
                    """)
                else:
                    st.error("❌ 이메일 전송에 실패했습니다.")
                    
            except Exception as e:
                st.error(f"❌ 이메일 발송 중 오류: {str(e)}")
                logger.error(f"이메일 발송 오류: {str(e)}")

# 기존 접수완료 페이지 코드를 다음과 같이 교체:
if st.session_state["page"] == "접수 완료":
    integrated_completion_page()

def validate_api_keys() -> Tuple[bool, str]:
    """API 키 유효성 검증"""
    try:
        if not openai_api_key or openai_api_key == "":
            return False, "OpenAI API 키가 설정되지 않았습니다."
        if not openai_org_id or openai_org_id == "":
            return False, "OpenAI Organization ID가 설정되지 않았습니다."
        return True, "API 키가 유효합니다."
    except Exception as e:
        return False, f"API 키 검증 오류: {str(e)}"

def extract_and_validate_file_contents(submission_id: str) -> Tuple[Dict[str, str], int]:
    """파일 내용 추출 및 검증"""
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute(
            "SELECT file_name, file_path FROM uploaded_files WHERE submission_id = ?",
            (submission_id,)
        )
        file_records = c.fetchall()
        conn.close()
        
        logger.info(f"📁 DB에서 찾은 파일 수: {len(file_records)}")
        
        file_contents = {}
        success_count = 0
        
        for file_name, file_path in file_records:
            logger.info(f"🔍 파일 처리 시작: {file_name}")
            
            if not os.path.exists(file_path):
                logger.error(f"❌ 파일 존재하지 않음: {file_path}")
                continue
                
            content = extract_file_content(file_path)
            
            # 내용 검증
            if not content:
                logger.warning(f"⚠️ 빈 내용: {file_name}")
                continue
                
            if content.startswith("[") or "실패" in content or "오류" in content:
                logger.warning(f"⚠️ 추출 실패: {file_name} - {content[:100]}")
                continue
                
            if len(content.strip()) < 10:
                logger.warning(f"⚠️ 내용이 너무 짧음: {file_name} ({len(content)}자)")
                continue
                
            file_contents[file_name] = content[:5000]  # 내용 길이 제한
            success_count += 1
            logger.info(f"✅ 파일 처리 성공: {file_name} ({len(content)}자)")
        
        logger.info(f"📊 최종 처리 결과: {success_count}/{len(file_records)} 성공")
        return file_contents, success_count
        
    except Exception as e:
        logger.error(f"❌ 파일 내용 추출 오류: {str(e)}")
        return {}, 0

def create_gpt_prompt(submission_id: str, department: str, manager: str, phone: str,
                      contract_name: str, contract_date: str, contract_amount: str,
                      file_contents: Dict[str, str]) -> str:
    """GPT 프롬프트 생성"""
    
    user_message = f"""일상감사 보고서를 작성해주세요.

## 📋 감사 기본 정보
- **접수번호**: {submission_id}
- **계약명**: {contract_name or '정보 없음'}
- **계약금액**: {contract_amount or '정보 없음'}
- **계약일**: {contract_date or '정보 없음'}
- **주관부서**: {department or '정보 없음'}
- **담당자**: {manager or '정보 없음'} (연락처: {phone or '정보 없음'})

## 📄 제출된 문서 분석
"""

    if file_contents:
        user_message += f"총 {len(file_contents)}개 문서가 제출되었습니다.\n\n"
        
        for file_name, content in file_contents.items():
            # 내용을 적절한 길이로 요약
            content_preview = content[:2000] + "..." if len(content) > 2000 else content
            user_message += f"""
### 📄 {file_name}
```
{content_preview}
```

"""
    else:
        user_message += """
**⚠️ 주요 문제**: 필수 문서(계약서, 제안서 평가표, 업체 선정 관련 문서)가 제출되지 않았습니다.
"""

    user_message += """
## 📝 보고서 작성 요청

위 정보를 바탕으로 **일상감사 보고서**를 다음 형식으로 작성해주세요:

1. **감사 개요** (접수 정보 요약)
2. **제출 문서 현황** (제출된 문서 목록과 분석)
3. **주요 검토 사항** (계약 내용, 금액, 절차의 적정성)
4. **발견사항** (문제점이나 개선사항)
5. **권고사항** (구체적인 개선 방안)
6. **결론** (전체적인 감사 의견)

전문적이고 객관적인 톤으로 작성하되, 실무진이 이해하기 쉽게 구체적으로 서술해주세요.
"""

    return user_message

def improved_get_clean_answer_from_gpts(question: str) -> Tuple[str, bool]:
    """개선된 GPT API 호출 함수"""
    try:
        logger.info("🤖 GPT API 호출 시작")
        
        # 1. API 키 검증
        is_valid, message = validate_api_keys()
        if not is_valid:
            logger.error(f"❌ API 키 검증 실패: {message}")
            return message, False
        
        assistant_id = "asst_oTip4nhZNJHinYxehJ7itwG9"
        
        headers = {
            "Authorization": f"Bearer {openai_api_key}",
            "OpenAI-Organization": openai_org_id,
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v2"
        }
        
        # 2. 스레드 생성
        logger.info("📝 새 스레드 생성 중...")
        thread_url = "https://api.openai.com/v1/threads"
        thread_resp = requests.post(thread_url, headers=headers)
        
        if thread_resp.status_code != 200:
            error_msg = f"스레드 생성 실패 (HTTP {thread_resp.status_code}): {thread_resp.text}"
            logger.error(f"❌ {error_msg}")
            return error_msg, False
        
        thread_id = thread_resp.json()["id"]
        logger.info(f"✅ 스레드 생성 성공: {thread_id}")
        
        # 3. 사용자 메시지 추가
        logger.info("💬 사용자 메시지 전송 중...")
        msg_url = f"{thread_url}/{thread_id}/messages"
        user_msg = {"role": "user", "content": question}
        
        msg_resp = requests.post(msg_url, headers=headers, json=user_msg)
        if msg_resp.status_code != 200:
            error_msg = f"메시지 전송 실패 (HTTP {msg_resp.status_code}): {msg_resp.text}"
            logger.error(f"❌ {error_msg}")
            return error_msg, False
        
        logger.info("✅ 메시지 전송 성공")
        
        # 4. 실행 시작
        logger.info("⚡ Assistant 실행 시작...")
        run_url = f"{thread_url}/{thread_id}/runs"
        
        run_payload = {
            "assistant_id": assistant_id
        }
        
        run_resp = requests.post(run_url, headers=headers, json=run_payload)
        if run_resp.status_code != 200:
            error_msg = f"실행 요청 실패 (HTTP {run_resp.status_code}): {run_resp.text}"
            logger.error(f"❌ {error_msg}")
            return error_msg, False
        
        run_id = run_resp.json()["id"]

        # 5. 완료 대기 (개선된 폴링)
        logger.info("⏳ 응답 생성 대기 중...")
        max_wait_time = 120  # 2분으로 증가
        wait_time = 0
        
        while wait_time < max_wait_time:
            status_resp = requests.get(f"{run_url}/{run_id}", headers=headers)
            if status_resp.status_code != 200:
                error_msg = f"상태 확인 실패 (HTTP {status_resp.status_code}): {status_resp.text}"
                logger.error(f"❌ {error_msg}")
                return error_msg, False
            
            status_data = status_resp.json()
            status = status_data["status"]
            
            logger.info(f"📊 실행 상태: {status} (대기시간: {wait_time}초)")
            
            if status == "completed":
                logger.info("✅ 실행 완료!")
                break
            elif status in ["failed", "cancelled", "expired"]:
                error_info = status_data.get("last_error", {})
                error_msg = f"실행 실패 - 상태: {status}, 오류: {error_info}"
                logger.error(f"❌ {error_msg}")
                return error_msg, False
            elif status == "requires_action":
                logger.warning("⚠️ 추가 작업이 필요한 상태입니다.")
                time.sleep(5)
                wait_time += 5
                continue
            
            time.sleep(3)
            wait_time += 3
        
        if wait_time >= max_wait_time:
            error_msg = f"응답 타임아웃 ({max_wait_time}초 초과)"
            logger.error(f"❌ {error_msg}")
            return error_msg, False
        
        # 6. 응답 메시지 추출
        logger.info("📥 응답 메시지 추출 중...")
        msgs_resp = requests.get(msg_url, headers=headers)
        if msgs_resp.status_code != 200:
            error_msg = f"메시지 조회 실패 (HTTP {msgs_resp.status_code}): {msgs_resp.text}"
            logger.error(f"❌ {error_msg}")
            return error_msg, False
        
        msgs = msgs_resp.json()["data"]
        
        # 최신 assistant 메시지 찾기
        for msg in msgs:
            if msg.get("role") == "assistant":
                for content in msg.get("content", []):
                    if content.get("type") == "text":
                        response_text = content["text"]["value"].strip()
                        
                        # 응답 품질 검증
                        if len(response_text) < 100:
                            logger.warning(f"⚠️ 응답이 너무 짧음: {len(response_text)}자")
                            return "생성된 응답이 너무 짧습니다. 다시 시도해주세요.", False
                        
                        logger.info(f"✅ 응답 생성 완료: {len(response_text)}자")
                        return response_text, True
        
        error_msg = "Assistant 응답을 찾을 수 없습니다."
        logger.error(f"❌ {error_msg}")
        return error_msg, False

    except requests.exceptions.RequestException as e:
        error_msg = f"네트워크 오류: {str(e)}"
        logger.error(f"❌ {error_msg}")
        return error_msg, False
    except Exception as e:
        error_msg = f"예상치 못한 오류: {str(e)}"
        logger.error(f"❌ {error_msg}")
        logger.error(f"상세 오류: {traceback.format_exc()}")
        return error_msg, False

# 디버깅 및 테스트 도구

def debug_file_extraction(submission_id: str):
    """파일 추출 상태 디버깅"""
    st.subheader("🔍 파일 추출 디버그 정보")
    
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        c.execute("SELECT file_name, file_path FROM uploaded_files WHERE submission_id = ?", 
                  (submission_id,))
        files = c.fetchall()
        conn.close()
        
        st.write(f"**DB에 등록된 파일 수:** {len(files)}")
        
        for i, (file_name, file_path) in enumerate(files, 1):
            with st.expander(f"📄 {i}. {file_name}"):
                st.write(f"**파일 경로:** `{file_path}`")
                st.write(f"**파일 존재 여부:** {'✅ 존재' if os.path.exists(file_path) else '❌ 없음'}")
                
                if os.path.exists(file_path):
                    try:
                        file_size = os.path.getsize(file_path)
                        st.write(f"**파일 크기:** {file_size:,} bytes")
                        
                        # 파일 내용 추출 테스트
                        with st.spinner("내용 추출 중..."):
                            content = extract_file_content(file_path)
                        
                        if content:
                            st.write(f"**추출된 내용 길이:** {len(content)} 문자")
                            if len(content) > 200:
                                st.text_area("내용 미리보기", content[:200] + "...", height=100)
                            else:
                                st.text_area("전체 내용", content, height=100)
                        else:
                            st.error("내용 추출 실패")
                            
                    except Exception as e:
                        st.error(f"파일 처리 오류: {e}")
                        
    except Exception as e:
        st.error(f"디버깅 중 오류: {e}")

def test_gpt_connection():
    """GPT API 연결 테스트"""
    st.subheader("🤖 GPT API 연결 테스트")
    
    if st.button("API 연결 테스트 실행"):
        with st.spinner("API 연결 테스트 중..."):
            # 1. API 키 검증
            is_valid, message = validate_api_keys()
            if not is_valid:
                st.error(f"❌ API 키 검증 실패: {message}")
                return
            
            st.success("✅ API 키 유효")
            
            # 2. 간단한 테스트 호출
            test_question = "안녕하세요. 간단한 응답을 해주세요."
            
            try:
                response, success = improved_get_clean_answer_from_gpts(test_question)
                
                if success:
                    st.success("✅ GPT API 호출 성공")
                    st.text_area("응답 내용", response, height=100)
                else:
                    st.error(f"❌ GPT API 호출 실패: {response}")
                    
            except Exception as e:
                st.error(f"❌ 테스트 중 오류: {e}")

def show_submission_status(submission_id: str):
    """접수 상태 종합 확인"""
    st.subheader("📊 접수 상태 종합")
    
    try:
        conn = sqlite3.connect('audit_system.db')
        c = conn.cursor()
        
        # 접수 정보 확인
        c.execute("SELECT * FROM submissions WHERE submission_id = ?", (submission_id,))
        submission = c.fetchone()
        
        if submission:
            st.success("✅ 접수 정보 존재")
        else:
            st.error("❌ 접수 정보 없음")
            
        # 파일 개수 확인
        c.execute("SELECT COUNT(*) FROM uploaded_files WHERE submission_id = ?", (submission_id,))
        file_count = c.fetchone()[0]
        st.info(f"📄 업로드된 파일: {file_count}개")
        
        # 누락 사유 개수 확인
        c.execute("SELECT COUNT(*) FROM missing_file_reasons WHERE submission_id = ?", (submission_id,))
        reason_count = c.fetchone()[0]
        st.info(f"📝 누락 사유: {reason_count}개")
        
        conn.close()
        
        # 필수 파일 체크
        total_required = len(required_files)
        completed = file_count + reason_count
        
        progress_percentage = (completed / total_required) * 100
        st.progress(progress_percentage / 100)
        st.write(f"**완료율:** {progress_percentage:.1f}% ({completed}/{total_required})")
        
        if completed >= total_required:
            st.success("✅ 모든 필수 항목 완료")
        else:
            st.warning(f"⚠️ {total_required - completed}개 항목 미완료")
            
    except Exception as e:
        st.error(f"상태 확인 중 오류: {e}")

# 접수완료 페이지에서 사용할 개선된 보고서 생성 섹션

def improved_report_generation_section(submission_id, department, manager, phone,
                                     contract_name, contract_date, contract_amount,
                                     uploaded_db_files, missing_db_files):
    """개선된 보고서 생성 섹션"""
    
    st.subheader("🤖 AI 감사보고서 생성")
    
    # 디버그 모드 토글
    if st.checkbox("🔧 디버그 모드", help="상세한 진행 상황을 확인할 수 있습니다."):
        debug_file_extraction(submission_id)
        test_gpt_connection()
        show_submission_status(submission_id)
        st.markdown("---")
    
    # 보고서 생성 버튼
    if st.button("📋 감사보고서 생성", type="primary", use_container_width=True):
        # 진행 상황 표시
        progress_bar = st.progress(0)
        status_text = st.empty()
        try:
            # 1단계: 초기화
            status_text.text("🔄 1/4: 초기화 중...")
            progress_bar.progress(25)
            time.sleep(1)
            # 2단계: 파일 분석
            status_text.text("📄 2/4: 파일 내용 분석 중...")
            progress_bar.progress(50)
            file_contents, success_count = extract_and_validate_file_contents(submission_id)
            if success_count > 0:
                st.success(f"✅ {success_count}개 파일 분석 완료")
            else:
                st.warning("⚠️ 분석 가능한 파일이 없습니다")
            # 3단계: AI 보고서 생성
            status_text.text("🤖 3/4: AI 보고서 생성 중...")
            progress_bar.progress(75)
            # (이후 단계는 필요시 추가)
        except Exception as e:
            st.error(f"보고서 생성 중 오류: {e}")
