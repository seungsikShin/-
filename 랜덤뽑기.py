import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import random

# 페이지 설정
st.set_page_config(
    page_title="점심시간 제비뽑기",
    page_icon="🎯",
    layout="wide"
)

def get_monday_of_week(date=None):
    """주어진 날짜의 주 월요일 날짜 반환"""
    if date is None:
        date = datetime.now()
    days_since_monday = date.weekday()
    monday = date - timedelta(days=days_since_monday)
    return monday.date()

def is_new_week():
    """새로운 주인지 확인"""
    current_monday = get_monday_of_week()
    
    if 'schedule_week' not in st.session_state:
        return True
        
    stored_monday = st.session_state.schedule_week
    return current_monday != stored_monday

def reset_weekly_data():
    """주간 데이터 초기화"""
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
    
    # 쪽지 스타일 CSS
    st.markdown("""
    <style>
    .ticket-container {
        display: flex;
        flex-wrap: wrap;
        justify-content: center;
        gap: 20px;
        margin: 20px 0;
    }
    .ticket {
        position: relative;
        width: 100px;
        height: 130px;
        background: linear-gradient(135deg, #f8f9fa, #e9ecef);
        border: 2px solid #dee2e6;
        border-radius: 12px 12px 0 0;
        transform: rotate(1deg);
        box-shadow: 0 4px 8px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    .ticket.filled {
        background: linear-gradient(135deg, #FFD93D, #FFC107);
        transform: rotate(1deg) scale(1.05);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    .ticket::before {
        content: '';
        position: absolute;
        top: 8px;
        left: 50%;
        transform: translateX(-50%);
        width: 8px;
        height: 8px;
        background: white;
        border-radius: 50%;
        box-shadow: -15px 0 white, 15px 0 white;
    }
    .ticket-number {
        position: absolute;
        top: 25px;
        left: 50%;
        transform: translateX(-50%);
        width: 30px;
        height: 30px;
        background: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-weight: bold;
        font-size: 16px;
        color: #333;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
    .ticket-name {
        position: absolute;
        top: 65px;
        left: 8px;
        right: 8px;
        text-align: center;
        font-size: 11px;
        font-weight: bold;
        color: #333;
        background: rgba(255,255,255,0.9);
        border-radius: 4px;
        padding: 4px 2px;
        word-break: break-all;
        line-height: 1.2;
    }
    .ticket-check {
        position: absolute;
        top: -5px;
        right: -5px;
        width: 20px;
        height: 20px;
        background: #28a745;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 12px;
        font-weight: bold;
    }
    .ticket-shadow {
        position: absolute;
        top: 4px;
        left: 4px;
        width: 100px;
        height: 130px;
        background: rgba(0,0,0,0.1);
        border-radius: 12px 12px 0 0;
        transform: rotate(-1deg);
        z-index: -1;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # 쪽지들 표시
    ticket_html = '<div class="ticket-container">'
    
    for i in range(members):
        ticket_html += f'''
        <div style="text-align: center;">
            <div class="ticket-shadow"></div>
            <div class="ticket" id="ticket-{i}">
                <div class="ticket-number">{i+1}</div>
                <div class="ticket-name" id="name-{i}">이름 대기중</div>
            </div>
        </div>
        '''
    
    ticket_html += '</div>'
    
    st.markdown(ticket_html, unsafe_allow_html=True)
    
    # 이름 입력 그리드
    st.markdown("##### 각 번호에 해당하는 이름을 입력하세요")
    name_cols = st.columns(min(5, members))  # 최대 5열로 제한
    member_names = []
    
    for i in range(members):
        col_idx = i % len(name_cols)
        with name_cols[col_idx]:
            name = st.text_input(f"{i+1}번", key=f"member_{i}", placeholder="이름 입력")
            member_names.append(name)
    
    # JavaScript로 실시간 쪽지 업데이트
    filled_names = [name if name.strip() else "" for name in member_names]
    
    update_script = """
    <script>
    """
    
    for i, name in enumerate(filled_names):
        if name:
            update_script += f"""
            document.getElementById('ticket-{i}').classList.add('filled');
            document.getElementById('name-{i}').innerHTML = '{name}';
            """
        else:
            update_script += f"""
            document.getElementById('ticket-{i}').classList.remove('filled');
            document.getElementById('name-{i}').innerHTML = '이름 대기중';
            """
    
    update_script += """
    </script>
    """
    
    st.markdown(update_script, unsafe_allow_html=True)
    
    # 입력 상태 확인
    filled_names = [name for name in member_names if name.strip()]
    st.info(f"이름 입력 완료: {len(filled_names)}/{members}명")
    
    # 제비뽑기 실행
    if len(filled_names) == members:
        if st.button("🎯 제비뽑기 시작!", type="primary", use_container_width=True):
            with st.spinner("제비뽑기 진행 중..."):
                # 제비뽑기 수행
                results = conduct_lottery(member_names, item_labels)
                
                # 결과 저장
                st.session_state.weekly_schedule = results
                st.session_state.schedule_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                st.success("✅ 제비뽑기가 완료되었습니다!")
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
    
    st.markdown("### 🛠️ 현재 상태")
    if st.session_state.weekly_schedule:
        st.success("✅ 이번 주 결과 저장됨")
    else:
        st.info("⏳ 제비뽑기 대기 중")
    
    # 수동 초기화 버튼 (테스트용)
    if st.button("🗑️ 결과 초기화", help="테스트용 - 저장된 결과를 삭제합니다"):
        st.session_state.weekly_schedule = None
        st.session_state.schedule_date = None
        st.rerun()

# 푸터
st.markdown("---")
st.markdown("🎯 **점심시간 제비뽑기** - 매주 공정하고 재미있는 시간 배정을 위해")
