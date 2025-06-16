import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import random
import json
import os

# 페이지 설정
st.set_page_config(
    page_title="점심시간 제비뽑기",
    page_icon="🎯",
    layout="wide"
)

# 데이터 저장 경로
DATA_FILE = "weekly_schedule.json"

def get_monday_of_week(date=None):
    """주어진 날짜의 주 월요일 날짜 반환"""
    if date is None:
        date = datetime.now()
    days_since_monday = date.weekday()
    monday = date - timedelta(days=days_since_monday)
    return monday.date()

def save_weekly_data(schedule_data):
    """주간 데이터를 파일에 저장"""
    try:
        data = {
            'weekly_schedule': schedule_data,
            'schedule_week': get_monday_of_week().isoformat(),
            'schedule_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'created_timestamp': datetime.now().isoformat()
        }
        
        # Streamlit Cloud에서는 파일 쓰기 권한이 제한적이므로 
        # 임시 디렉토리나 메모리 기반 저장 시도
        try:
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except:
            # 파일 저장 실패 시 session_state로 폴백
            st.session_state.persistent_data = data
            return False
    except Exception as e:
        st.error(f"데이터 저장 중 오류: {e}")
        return False

def load_weekly_data():
    """주간 데이터를 파일에서 로드"""
    try:
        # 먼저 파일에서 로드 시도
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # 주차 확인
            stored_week = datetime.fromisoformat(data['schedule_week']).date()
            current_week = get_monday_of_week()
            
            if stored_week == current_week:
                return data
            else:
                # 오래된 데이터 삭제
                os.remove(DATA_FILE)
                return None
        
        # 파일이 없으면 session_state에서 확인
        elif 'persistent_data' in st.session_state:
            data = st.session_state.persistent_data
            stored_week = datetime.fromisoformat(data['schedule_week']).date()
            current_week = get_monday_of_week()
            
            if stored_week == current_week:
                return data
            else:
                del st.session_state.persistent_data
                return None
                
    except Exception as e:
        st.error(f"데이터 로드 중 오류: {e}")
        return None
    
    return None

def is_new_week():
    """새로운 주인지 확인"""
    current_monday = get_monday_of_week()
    
    # 저장된 데이터 확인
    saved_data = load_weekly_data()
    if saved_data is None:
        return True
        
    stored_monday = datetime.fromisoformat(saved_data['schedule_week']).date()
    return current_monday != stored_monday

def reset_weekly_data():
    """주간 데이터 초기화"""
    # 파일 삭제
    if os.path.exists(DATA_FILE):
        try:
            os.remove(DATA_FILE)
        except:
            pass
    
    # session_state 초기화
    if 'persistent_data' in st.session_state:
        del st.session_state.persistent_data
    
    st.session_state.weekly_schedule = None
    st.session_state.schedule_week = get_monday_of_week()
    st.session_state.schedule_date = None

def conduct_lottery(member_names, item_labels):
    """제비뽑기 수행"""
    # 참여자들을 랜덤으로 섞기
    members_with_index = [(i+1, name) for i, name in enumerate(member_names)]
    random.shuffle(members_with_index)
    
    # 각 항목에 배정할 인원수 계산 (균등 분배)
    total_members = len(member_names)
    total_items = len(item_labels)
    members_per_item = total_members // total_items
    remainder = total_members % total_items
    
    # 항목별로 인원 배정
    results = []
    current_index = 0
    
    for i, label in enumerate(item_labels):
        # 이 항목에 배정될 인원수 (나머지는 앞 항목들에 우선 배정)
        item_member_count = members_per_item + (1 if i < remainder else 0)
        assigned_members = []
        
        for j in range(item_member_count):
            if current_index < len(members_with_index):
                index, name = members_with_index[current_index]
                assigned_members.append({'index': index, 'name': name})
                current_index += 1
        
        results.append({
            'label': label,
            'members': assigned_members
        })
    
    return results

# 앱 시작 시 데이터 로드
saved_data = load_weekly_data()
if saved_data:
    st.session_state.weekly_schedule = saved_data['weekly_schedule']
    st.session_state.schedule_week = datetime.fromisoformat(saved_data['schedule_week']).date()
    st.session_state.schedule_date = saved_data['schedule_date']
else:
    # 세션 상태 초기화
    if 'weekly_schedule' not in st.session_state:
        st.session_state.weekly_schedule = None
        
    if 'schedule_week' not in st.session_state:
        st.session_state.schedule_week = None
        
    if 'schedule_date' not in st.session_state:
        st.session_state.schedule_date = None

# 새로운 주 체크 및 초기화
if is_new_week():
    if st.session_state.weekly_schedule is not None:
        st.info("🗓️ 새로운 주가 시작되어 이전 결과를 초기화합니다.")
    reset_weekly_data()

# 메인 UI
st.title("🎯 점심시간 제비뽑기")

# 현재 주차 정보 표시
current_monday = get_monday_of_week()
current_sunday = current_monday + timedelta(days=6)
st.info(f"📅 현재 주차: {current_monday.strftime('%Y-%m-%d')} ~ {current_sunday.strftime('%Y-%m-%d')}")

# 저장된 결과가 있는 경우 표시
if st.session_state.weekly_schedule is not None:
    st.success("🎉 이번 주 제비뽑기 결과")
    
    # 결과 표시
    schedule_data = st.session_state.weekly_schedule
    
    cols = st.columns(len(schedule_data))
    
    for idx, item in enumerate(schedule_data):
        with cols[idx % len(cols)]:
            st.markdown(f"### 🏆 {item['label']}")
            
            if item['members']:
                for member in item['members']:
                    st.markdown(f"- **{member['name']}** ({member['index']}번)")
            else:
                st.markdown("- 배정된 인원이 없습니다")
    
    # 결과 생성 시간 표시
    if st.session_state.schedule_date:
        st.caption(f"생성일시: {st.session_state.schedule_date}")
    
    # 새로 뽑기 버튼
    if st.button("🔄 새로 제비뽑기 하기", type="secondary"):
        st.session_state.weekly_schedule = None
        st.session_state.schedule_date = None
        st.rerun()
    
    st.divider()

# 제비뽑기 설정 및 실행
if st.session_state.weekly_schedule is None:
    st.markdown("### 새로운 제비뽑기를 시작하세요")
    
    # 설정 영역
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("#### 기본 설정")
        members = st.number_input("인원수", min_value=2, max_value=20, value=5)
        items = st.number_input("항목수", min_value=1, max_value=10, value=2)
    
    with col2:
        st.markdown("#### 항목명 설정")
        item_labels = []
        for i in range(items):
            default_label = "앞타임" if i == 0 else "뒷타임" if i == 1 else f"항목{i+1}"
            label = st.text_input(f"항목 {i+1}", value=default_label, key=f"item_{i}")
            item_labels.append(label if label.strip() else f"항목{i+1}")
    
    st.divider()
    
    # 이름 입력 영역
    st.markdown("#### 참여자 이름 입력")
    
    # 이름 입력 그리드
    name_cols = st.columns(min(5, members))  # 최대 5열로 제한
    member_names = []
    
    for i in range(members):
        col_idx = i % len(name_cols)
        with name_cols[col_idx]:
            name = st.text_input(f"{i+1}번", key=f"member_{i}", placeholder="이름 입력")
            member_names.append(name)
    
    # 쪽지 상태를 시각적으로 표시 (간단한 방식)
    st.markdown("##### 쪽지 현황")
    
    # 색상과 이모지로 간단하게 표현
    colors = ["🟢", "🔴", "🟡", "🔵", "⚫"]
    
    # 쪽지들을 그리드로 표시
    ticket_cols = st.columns(min(5, members))
    
    for i in range(members):
        col_idx = i % len(ticket_cols)
        with ticket_cols[col_idx]:
            name = member_names[i]
            color_emoji = colors[i % len(colors)]
            
            if name.strip():
                # 이름이 입력된 쪽지
                st.markdown(f"""
                **{color_emoji} {i+1}번**  
                ✅ **{name}**
                """)
            else:
                # 빈 쪽지
                st.markdown(f"""
                ⚪ **{i+1}번**  
                ⏳ *대기중*
                """)
    
    # 입력 상태 확인
    filled_names = [name for name in member_names if name.strip()]
    st.info(f"이름 입력 완료: {len(filled_names)}/{members}명")
    
    # 제비뽑기 실행
    if len(filled_names) == members:
        if st.button("🎯 제비뽑기 시작!", type="primary", use_container_width=True):
            with st.spinner("제비뽑기 진행 중..."):
                # 제비뽑기 수행
                results = conduct_lottery(member_names, item_labels)
                
                # 결과 저장 (파일 + session_state)
                save_success = save_weekly_data(results)
                
                # session_state에도 저장 (즉시 표시용)
                st.session_state.weekly_schedule = results
                st.session_state.schedule_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                st.session_state.schedule_week = get_monday_of_week()
                
                if save_success:
                    st.success("✅ 제비뽑기가 완료되고 파일에 저장되었습니다! (새로고침해도 유지)")
                else:
                    st.warning("✅ 제비뽑기가 완료되었습니다! (파일 저장 실패 - 세션만 유지)")
                
                st.rerun()
    else:
        st.warning("모든 참여자의 이름을 입력해주세요.")

# 사이드바에 정보 표시
with st.sidebar:
    st.markdown("### ℹ️ 사용 안내")
    st.markdown("""
    1. **인원수**와 **항목수**를 설정하세요
    2. 각 **항목명**을 입력하세요 (예: 앞타임, 뒷타임)
    3. 모든 **참여자 이름**을 입력하세요
    4. **제비뽑기 시작** 버튼을 클릭하세요
    
    📅 **저장된 결과는 일주일간 유지됩니다**
    🔄 **매주 월요일에 자동으로 초기화됩니다**
    """)
    
    st.divider()
    
    # 현재 주차 결과 표시
    st.markdown("### 📋 이번 주 결과")
    
    if st.session_state.weekly_schedule:
        # 저장된 결과가 있는 경우
        st.success("✅ 제비뽑기 완료")
        
        # 컴팩트한 결과 표시
        for idx, item in enumerate(st.session_state.weekly_schedule):
            # 각 항목별로 표시
            if item['members']:
                st.markdown(f"**🏆 {item['label']}**")
                for member in item['members']:
                    colors = ["🟢", "🔴", "🟡", "🔵", "⚫"]
                    color_emoji = colors[(member['index']-1) % len(colors)]
                    st.markdown(f"  {color_emoji} **{member['name']}** ({member['index']}번)")
            else:
                st.markdown(f"**{item['label']}**: *없음*")
        
        # 생성 시간
        if st.session_state.schedule_date:
            st.caption(f"📅 {st.session_state.schedule_date}")
        
        st.divider()
        
        # 빠른 수정 버튼들
        st.markdown("**⚡ 빠른 작업**")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 재뽑기", help="새로운 제비뽑기 진행", use_container_width=True):
                # 파일과 세션 모두 초기화
                reset_weekly_data()
                st.rerun()
        
        with col2:
            if st.button("📤 공유", help="결과를 복사용 텍스트로 생성", use_container_width=True):
                # 결과를 텍스트로 변환
                share_text = f"📋 이번 주 점심시간 제비뽑기 결과\n"
                share_text += f"📅 {st.session_state.schedule_date}\n\n"
                
                for item in st.session_state.weekly_schedule:
                    share_text += f"🏆 {item['label']}\n"
                    if item['members']:
                        for member in item['members']:
                            share_text += f"  • {member['name']} ({member['index']}번)\n"
                    else:
                        share_text += "  • 배정된 인원 없음\n"
                    share_text += "\n"
                
                st.text_area("📋 공유용 텍스트", share_text, height=200)
    
    else:
        # 저장된 결과가 없는 경우
        st.info("⏳ 제비뽑기 대기 중")
        st.markdown("아직 이번 주 제비뽑기를 진행하지 않았습니다.")
    
    st.divider()
    
    # 상태 및 관리
    st.markdown("### 🛠️ 시스템 상태")
    
    # 현재 주차 정보
    current_monday = get_monday_of_week()
    current_sunday = current_monday + timedelta(days=6)
    st.markdown(f"""
    **현재 주차**  
    {current_monday.strftime('%m/%d')} ~ {current_sunday.strftime('%m/%d')}
    """)
    
    # 다음 초기화 시간
    next_monday = current_monday + timedelta(days=7)
    st.markdown(f"""
    **다음 초기화**  
    {next_monday.strftime('%Y-%m-%d')} (월요일)
    """)
    
    # 수동 초기화 버튼 (관리자용)
    if st.button("🗑️ 결과 삭제", help="관리자용 - 저장된 결과를 즉시 삭제합니다", type="secondary"):
        reset_weekly_data()
        st.success("결과가 완전히 삭제되었습니다!")
        st.rerun()
    
    # 저장 상태 표시
    st.divider()
    st.markdown("### 💾 저장 상태")
    
    file_exists = os.path.exists(DATA_FILE)
    session_exists = 'persistent_data' in st.session_state
    
    if file_exists:
        st.success("📁 파일 저장됨 (영구)")
    elif session_exists:
        st.warning("💭 세션 저장됨 (임시)")
    else:
        st.info("❌ 저장된 데이터 없음")
    
    # 저장 방식 설명
    with st.expander("💡 저장 방식 설명"):
        st.markdown("""
        **🏆 이상적인 경우 (파일 저장)**
        - `weekly_schedule.json` 파일로 저장
        - 새로고침, 브라우저 종료해도 유지
        - 주차 종료까지 완전 보존
        
        **⚠️ 제한적인 경우 (세션 저장)**  
        - 메모리에만 임시 저장
        - 브라우저 종료 시 사라질 수 있음
        - Streamlit Cloud 제약 환경
        
        **📋 권장사항**
        - 중요한 결과는 '📤 공유' 버튼으로 백업
        - 매주 월요일에 자동 초기화됨
        """)

# 푸터
st.markdown("---")
st.markdown("🎯 **점심시간 제비뽑기** - 매주 공정하고 재미있는 시간 배정을 위해")

# 개발자 정보 (숨김)
with st.expander("🔧 개발자 정보"):
    st.markdown(f"""
    **버전**: 2.0 (영구저장 지원)  
    **데이터 파일**: `{DATA_FILE}`  
    **현재 주차**: {get_monday_of_week()}  
    **저장 상태**: {'파일' if os.path.exists(DATA_FILE) else '세션' if 'persistent_data' in st.session_state else '없음'}
    """)
