import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime, timedelta
import json

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
    col1, col2 = st.columns(2)
    
    schedule_data = st.session_state.weekly_schedule
    
    for idx, item in enumerate(schedule_data):
        with col1 if idx % 2 == 0 else col2:
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

# 제비뽑기 게임이 필요한 경우만 표시
if st.session_state.weekly_schedule is None:
    st.markdown("### 새로운 제비뽑기를 시작하세요")
    
    # HTML 컴포넌트 정의
    lottery_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            @keyframes bounce {
                0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
                40% { transform: translateY(-10px); }
                60% { transform: translateY(-5px); }
            }
            .bounce { animation: bounce 1s infinite; }
        </style>
    </head>
    <body class="bg-gray-50 p-4">
        <div class="max-w-4xl mx-auto">
            <!-- 설정 영역 -->
            <div class="bg-white rounded-lg p-6 mb-6 shadow-sm">
                <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                    <!-- 인원수 설정 -->
                    <div class="flex items-center justify-center gap-4">
                        <span class="text-blue-600 font-medium">인원수</span>
                        <button onclick="changeMembers(-1)" class="w-8 h-8 border border-gray-300 rounded flex items-center justify-center hover:bg-gray-100">−</button>
                        <span id="memberCount" class="text-xl font-semibold min-w-[3rem] text-center">5명</span>
                        <button onclick="changeMembers(1)" class="w-8 h-8 border border-gray-300 rounded flex items-center justify-center hover:bg-gray-100">+</button>
                    </div>
                    
                    <!-- 항목수 및 항목명 설정 -->
                    <div class="space-y-4">
                        <div class="flex items-center justify-center gap-4">
                            <span class="text-blue-600 font-medium">항목수</span>
                            <button onclick="changeItems(-1)" class="w-8 h-8 border border-gray-300 rounded flex items-center justify-center hover:bg-gray-100">−</button>
                            <span id="itemCount" class="text-xl font-semibold min-w-[3rem] text-center">2개</span>
                            <button onclick="changeItems(1)" class="w-8 h-8 border border-gray-300 rounded flex items-center justify-center hover:bg-gray-100">+</button>
                        </div>
                        
                        <!-- 각 항목 이름 입력 -->
                        <div class="space-y-2">
                            <label class="block text-sm font-medium text-gray-600 text-center">항목명 설정</label>
                            <div id="itemLabels">
                                <!-- 동적으로 생성 -->
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- 게임 영역 -->
            <div class="bg-amber-50 rounded-lg p-6 mb-6">
                <p id="gameMessage" class="text-center text-gray-700 mb-6 text-lg">
                    쪽지에 이름을 입력한 후 제비뽑기를 시작하세요
                </p>
                
                <!-- 쪽지 영역 -->
                <div id="ticketsArea" class="flex justify-center items-center gap-3 mb-6 flex-wrap">
                    <!-- 동적으로 생성 -->
                </div>
                
                <!-- 제비뽑기 버튼 -->
                <div class="text-center">
                    <button id="drawButton" onclick="startDraw()" class="px-8 py-3 rounded-lg font-medium text-white bg-gray-600 hover:bg-gray-700 shadow-lg hover:shadow-xl transition-all duration-200">
                        🎯 제비뽑기 시작
                    </button>
                    <button id="resetButton" onclick="resetGame()" class="ml-4 px-6 py-3 rounded-lg font-medium text-gray-600 border border-gray-300 hover:bg-gray-50 transition-all duration-200" style="display: none;">
                        다시 하기
                    </button>
                </div>
                
                <!-- 입력 상태 안내 -->
                <div class="text-center mt-4">
                    <p id="inputStatus" class="text-sm text-gray-600"></p>
                </div>
            </div>
            
            <!-- 결과 영역 -->
            <div id="resultArea" style="display: none;" class="bg-white rounded-lg p-6 shadow-sm mb-6">
                <h2 class="text-2xl font-bold text-center mb-6 text-gray-800">🎉 제비뽑기 결과</h2>
                <div id="resultContent"></div>
                
                <!-- 저장 버튼 -->
                <div class="text-center mt-6">
                    <button onclick="saveResult()" class="px-8 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 transition-all duration-200 shadow-lg">
                        📅 결과 저장하기 (일주일간 유지)
                    </button>
                </div>
            </div>
        </div>
        
        <script>
            let members = 5;
            let items = 2;
            let memberNames = ['', '', '', '', ''];
            let itemLabels = ['앞타임', '뒷타임'];
            let isDrawing = false;
            let results = null;
            
            const arrowColors = ['#FF6B6B', '#FFD93D', '#4ECDC4', '#95A5A6', '#98D8C8'];
            
            function changeMembers(delta) {
                const newCount = Math.max(2, Math.min(10, members + delta));
                if (newCount !== members) {
                    members = newCount;
                    // 이름 배열 조정
                    if (memberNames.length < members) {
                        while (memberNames.length < members) {
                            memberNames.push('');
                        }
                    } else {
                        memberNames = memberNames.slice(0, members);
                    }
                    updateUI();
                }
            }
            
            function changeItems(delta) {
                const newCount = Math.max(1, Math.min(10, items + delta));
                if (newCount !== items) {
                    items = newCount;
                    // 라벨 배열 조정
                    if (itemLabels.length < items) {
                        while (itemLabels.length < items) {
                            itemLabels.push(`항목${itemLabels.length + 1}`);
                        }
                    } else {
                        itemLabels = itemLabels.slice(0, items);
                    }
                    updateUI();
                }
            }
            
            function updateItemLabel(index, value) {
                itemLabels[index] = value;
            }
            
            function updateMemberName(index, value) {
                memberNames[index] = value;
                updateInputStatus();
                updateDrawButton();
            }
            
            function updateUI() {
                // 카운터 업데이트
                document.getElementById('memberCount').textContent = members + '명';
                document.getElementById('itemCount').textContent = items + '개';
                
                // 항목 라벨 UI 업데이트
                const itemLabelsDiv = document.getElementById('itemLabels');
                itemLabelsDiv.innerHTML = '';
                for (let i = 0; i < items; i++) {
                    const div = document.createElement('div');
                    div.className = 'flex items-center gap-2';
                    div.innerHTML = `
                        <span class="text-sm text-gray-500 min-w-[4rem]">항목 ${i + 1}</span>
                        <input type="text" value="${itemLabels[i]}" 
                               onchange="updateItemLabel(${i}, this.value)"
                               class="flex-1 px-3 py-2 border border-gray-300 rounded text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                               placeholder="항목 ${i + 1} 이름">
                    `;
                    itemLabelsDiv.appendChild(div);
                }
                
                // 쪽지 UI 업데이트
                updateTickets();
                updateInputStatus();
                updateDrawButton();
            }
            
            function updateTickets() {
                const ticketsArea = document.getElementById('ticketsArea');
                ticketsArea.innerHTML = '';
                
                for (let i = 0; i < members; i++) {
                    const ticketDiv = document.createElement('div');
                    ticketDiv.className = `relative transition-all duration-300 transform ${memberNames[i].trim() ? 'scale-105 shadow-xl' : 'shadow-md'}`;
                    
                    const color = arrowColors[i % arrowColors.length];
                    const hasName = memberNames[i].trim() !== '';
                    
                    ticketDiv.innerHTML = `
                        <div class="relative">
                            <div class="w-24 h-32 rounded-t-lg relative transform rotate-1 border border-gray-300 shadow-lg"
                                 style="background: ${hasName ? `linear-gradient(135deg, ${color}, ${color}dd)` : 'linear-gradient(135deg, #f8f9fa, #e9ecef)'}">
                                
                                <!-- 구멍들 -->
                                <div class="absolute top-2 left-1/2 transform -translate-x-1/2 flex gap-1">
                                    <div class="w-1.5 h-1.5 bg-white rounded-full opacity-80"></div>
                                    <div class="w-1.5 h-1.5 bg-white rounded-full opacity-80"></div>
                                    <div class="w-1.5 h-1.5 bg-white rounded-full opacity-80"></div>
                                </div>
                                
                                <!-- 번호 -->
                                <div class="absolute top-6 left-1/2 transform -translate-x-1/2">
                                    <div class="w-8 h-8 rounded-full flex items-center justify-center font-bold text-lg ${hasName ? 'bg-white text-gray-800 shadow-md' : 'bg-gray-200 text-gray-600'}">
                                        ${i + 1}
                                    </div>
                                </div>
                                
                                <!-- 이름 표시 -->
                                <div class="absolute top-16 left-2 right-2 bottom-8 flex items-center justify-center">
                                    ${hasName ? `<div class="bg-white bg-opacity-90 rounded px-1 py-0.5 text-xs font-medium text-gray-800 break-all text-center">${memberNames[i]}</div>` : ''}
                                </div>
                                
                                <!-- 완료 표시 -->
                                ${hasName ? '<div class="absolute -top-1 -right-1 w-6 h-6 bg-green-500 rounded-full flex items-center justify-center shadow-md"><span class="text-white text-xs font-bold">✓</span></div>' : ''}
                                
                                <!-- 찢어진 효과 -->
                                <div class="absolute bottom-0 left-0 right-0 h-2">
                                    <svg viewBox="0 0 80 8" class="w-full h-full">
                                        <path d="M0,4 Q10,0 20,4 T40,4 T60,4 T80,4 L80,8 L0,8 Z" fill="currentColor" class="text-gray-200"/>
                                    </svg>
                                </div>
                            </div>
                            
                            <!-- 그림자 -->
                            <div class="absolute top-1 left-1 w-24 h-32 rounded-t-lg bg-gray-400 opacity-20 -z-10" style="transform: rotate(-1deg)"></div>
                        </div>
                        
                        <!-- 이름 입력창 -->
                        <div class="mt-3">
                            <input type="text" value="${memberNames[i]}" 
                                   onchange="updateMemberName(${i}, this.value)"
                                   placeholder="이름 입력" 
                                   class="w-24 px-2 py-1 text-center text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                                   ${isDrawing ? 'disabled' : ''}>
                        </div>
                    `;
                    
                    ticketsArea.appendChild(ticketDiv);
                }
            }
            
            function updateInputStatus() {
                const completedCount = memberNames.filter(name => name.trim() !== '').length;
                const statusElement = document.getElementById('inputStatus');
                
                if (completedCount === members) {
                    statusElement.innerHTML = `<span class="text-green-600">✅ 모든 이름 입력 완료 (${completedCount}/${members}명)</span>`;
                } else {
                    statusElement.innerHTML = `이름 입력 완료: ${completedCount}/${members}명 <span class="text-red-600 ml-2">(모든 쪽지에 이름을 입력해주세요)</span>`;
                }
            }
            
            function updateDrawButton() {
                const drawButton = document.getElementById('drawButton');
                const allNamesEntered = memberNames.every(name => name.trim() !== '');
                
                if (allNamesEntered && !isDrawing) {
                    drawButton.disabled = false;
                    drawButton.className = 'px-8 py-3 rounded-lg font-medium text-white bg-gray-600 hover:bg-gray-700 shadow-lg hover:shadow-xl transition-all duration-200';
                } else {
                    drawButton.disabled = true;
                    drawButton.className = 'px-8 py-3 rounded-lg font-medium text-white bg-gray-400 cursor-not-allowed transition-all duration-200';
                }
            }
            
            function startDraw() {
                if (!memberNames.every(name => name.trim() !== '')) {
                    alert('모든 쪽지에 이름을 입력해주세요!');
                    return;
                }
                
                isDrawing = true;
                document.getElementById('gameMessage').textContent = '제비뽑기 진행 중...';
                document.getElementById('drawButton').textContent = '제비뽑기 진행 중...';
                updateDrawButton();
                
                // 애니메이션 효과
                const tickets = document.querySelectorAll('#ticketsArea > div');
                tickets.forEach(ticket => {
                    ticket.classList.add('bounce');
                });
                
                setTimeout(() => {
                    // 참여자들을 랜덤으로 섞기
                    const shuffledMembers = memberNames.map((name, index) => ({
                        index: index + 1,
                        name: name
                    })).sort(() => Math.random() - 0.5);
                    
                    // 각 항목에 배정할 인원수 계산
                    const membersPerItem = Math.floor(members / items);
                    const remainder = members % items;
                    
                    // 항목별로 인원 배정
                    const groupedResults = [];
                    let currentIndex = 0;
                    
                    for (let i = 0; i < items; i++) {
                        const itemMemberCount = membersPerItem + (i < remainder ? 1 : 0);
                        const assignedMembers = [];
                        
                        for (let j = 0; j < itemMemberCount; j++) {
                            assignedMembers.push(shuffledMembers[currentIndex]);
                            currentIndex++;
                        }
                        
                        groupedResults.push({
                            label: itemLabels[i],
                            members: assignedMembers
                        });
                    }
                    
                    results = groupedResults;
                    displayResults();
                    
                    isDrawing = false;
                    document.getElementById('gameMessage').textContent = '제비뽑기 결과입니다!';
                    document.getElementById('drawButton').textContent = '🎯 제비뽑기 시작';
                    document.getElementById('resetButton').style.display = 'inline-block';
                    
                    tickets.forEach(ticket => {
                        ticket.classList.remove('bounce');
                    });
                }, 2000);
            }
            
            function displayResults() {
                const resultArea = document.getElementById('resultArea');
                const resultContent = document.getElementById('resultContent');
                
                let html = '<div class="grid grid-cols-1 gap-4">';
                
                results.forEach((result, index) => {
                    const bgColor = index % 2 === 0 ? 'bg-blue-50 border-blue-200' : 'bg-green-50 border-green-200';
                    const textColor = index % 2 === 0 ? 'text-blue-800' : 'text-green-800';
                    const memberBg = index % 2 === 0 ? 'bg-white border-blue-100 text-blue-800' : 'bg-white border-green-100 text-green-800';
                    const numberBg = index % 2 === 0 ? 'bg-blue-500' : 'bg-green-500';
                    
                    html += `
                        <div class="rounded-lg p-4 border-2 ${bgColor}">
                            <h3 class="text-lg font-semibold mb-3 text-center ${textColor}">🏆 ${result.label}</h3>
                            <div class="flex justify-center gap-2 flex-wrap">
                    `;
                    
                    if (result.members.length > 0) {
                        result.members.forEach(member => {
                            html += `
                                <div class="inline-flex items-center gap-2 px-4 py-2 rounded-lg font-medium shadow-sm ${memberBg}">
                                    <span class="w-6 h-6 ${numberBg} rounded-full text-white font-bold text-sm flex items-center justify-center">${member.index}</span>
                                    ${member.name}
                                </div>
                            `;
                        });
                    } else {
                        html += '<div class="text-center text-gray-500 py-4">배정된 인원이 없습니다</div>';
                    }
                    
                    html += '</div></div>';
                });
                
                html += '</div>';
                resultContent.innerHTML = html;
                resultArea.style.display = 'block';
            }
            
            function resetGame() {
                results = null;
                memberNames = Array(members).fill('');
                document.getElementById('resultArea').style.display = 'none';
                document.getElementById('resetButton').style.display = 'none';
                document.getElementById('gameMessage').textContent = '쪽지에 이름을 입력한 후 제비뽑기를 시작하세요';
                updateTickets();
                updateInputStatus();
                updateDrawButton();
            }
            
            function saveResult() {
                if (results) {
                    // Streamlit으로 결과 전송
                    window.parent.postMessage({
                        type: 'saveResult',
                        data: results
                    }, '*');
                }
            }
            
            // 초기 UI 업데이트
            updateUI();
        </script>
    </body>
    </html>
    """

    # HTML 컴포넌트 렌더링 및 결과 수신
    result = components.html(lottery_html, height=800, key="lottery_game")

    # JavaScript에서 메시지 수신 처리
    if result:
        try:
            # 결과 저장
            st.session_state.weekly_schedule = result
            st.session_state.schedule_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            st.success("✅ 결과가 저장되었습니다! 일주일간 이 결과가 유지됩니다.")
            st.rerun()
        except:
            pass

# 사이드바에 정보 표시
with st.sidebar:
    st.markdown("### ℹ️ 사용 안내")
    st.markdown("""
    1. **인원수**와 **항목수**를 설정하세요
    2. 각 **항목명**을 입력하세요 (예: 앞타임, 뒷타임)
    3. 모든 **쪽지에 이름**을 입력하세요
    4. **제비뽑기 시작** 버튼을 클릭하세요
    5. 결과를 확인하고 **저장**하세요
    
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
