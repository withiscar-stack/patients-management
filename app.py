import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta

st.set_page_config(page_title="한의원 스마트 CRM", layout="wide")

# --- Firebase 초기화 ---
def init_firebase():
    if not firebase_admin._apps:
        key_dict = dict(st.secrets["textkey"])
        creds = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(creds)
    return firestore.client()

db = init_firebase()

# 날짜 문자열 변환 도우미 (2026.04.30 또는 2026-04-30 처리)
def parse_date(date_str):
    clean_str = date_str.replace(".", "-")
    return datetime.strptime(clean_str, "%Y-%m-%d")

st.title("🏥 한의원 스마트 CRM 시스템")

# --- 화면을 두 개의 탭으로 분리 ---
tab1, tab2 = st.tabs(["📄 일일결산 PDF 업로드", "🔔 오늘 연락할 환자 (해피콜)"])

# ==========================================
# 탭 1: PDF 업로드 및 저장 로직
# ==========================================
with tab1:
    st.info("결산서를 업로드하면 최근 30일 내원 여부를 계산하여 알림 일정을 자동으로 세팅합니다.")
    uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

    if uploaded_file is not None:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        full_text = "".join([page.get_text().replace("\n", "") for page in doc])
        
        marker = "통장"
        first_idx = full_text.find(marker)
        target_text = full_text
        if first_idx != -1:
            second_idx = full_text.find(marker, first_idx + len(marker))
            if second_idx != -1:
                target_text = full_text[second_idx + len(marker):]
        
        pattern = r"(\d+)([가-힣]{2,4})(\d{6})(\d{4}[-.]\d{2}[-.]\d{2})"
        matches = re.findall(pattern, target_text)
        
        if len(matches) > 1:
            actual_matches = matches[1:]
            data = [{"환자명": m[1], "차트번호": m[2], "진료일자": m[3].replace(".", "-")} for m in actual_matches]
            df = pd.DataFrame(data).drop_duplicates(subset=['차트번호', '진료일자']).reset_index(drop=True)
            
            st.dataframe(df, use_container_width=True)
            
            if st.button("🔥 환자 정보 및 해피콜 일정 저장하기"):
                try:
                    batch = db.batch()
                    for _, row in df.iterrows():
                        patient_ref = db.collection("patients").document(row["차트번호"])
                        doc_snap = patient_ref.get()
                        
                        visit_date_obj = parse_date(row["진료일자"])
                        
                        # 과거 데이터 확인 (30일 이내 내원 여부)
                        stage = 0
                        if doc_snap.exists:
                            pat_data = doc_snap.to_dict()
                            last_visit_str = pat_data.get("last_visit", "2000-01-01")
                            last_visit_obj = parse_date(last_visit_str)
                            
                            days_passed = (visit_date_obj - last_visit_obj).days
                            
                            # 30일 이내에 온 적이 있다면 기존 알림 단계(stage) 유지
                            if days_passed <= 30:
                                stage = pat_data.get("notification_stage", 0)
                            # 30일이 넘었다면 새로운 치료 주기로 보고 stage 0으로 초기화
                        
                        # 다음 알림일 계산 로직
                        if stage == 0:
                            next_alert_obj = visit_date_obj + timedelta(days=3)
                        elif stage == 1:
                            next_alert_obj = visit_date_obj + timedelta(days=7)
                        else:
                            next_alert_obj = None # 2단계 이상이면 일단 알림 없음
                            
                        # 저장 실행
                        save_data = {
                            "name": row["환자명"],
                            "chart_no": row["차트번호"],
                            "last_visit": row["진료일자"],
                            "notification_stage": stage,
                            "updated_at": firestore.SERVER_TIMESTAMP
                        }
                        if next_alert_obj:
                            save_data["next_alert_date"] = next_alert_obj.strftime("%Y-%m-%d")
                            
                        batch.set(patient_ref, save_data, merge=True)
                    
                    batch.commit()
                    st.success("✅ 해피콜 일정이 완벽하게 세팅되었습니다!")
                except Exception as e:
                    st.error(f"❌ 저장 중 오류: {e}")

# ==========================================
# 탭 2: 해피콜 알림 대시보드
# ==========================================
with tab2:
    st.subheader("📞 오늘 연락해야 할 환자 목록")
    today_obj = datetime.now()
    today_str = today_obj.strftime("%Y-%m-%d")
    
    # 환자 데이터 불러오기
    patients_ref = db.collection("patients").stream()
    
    alerts_to_show = []
    
    for doc in patients_ref:
        pat = doc.to_dict()
        last_visit_str = pat.get("last_visit")
        next_alert_str = pat.get("next_alert_date")
        
        if not last_visit_str:
            continue
            
        last_visit_obj = parse_date(last_visit_str)
        days_since_last_visit = (today_obj - last_visit_obj).days
        
        # [조건 3] 30일이 지난 데이터 자동 정리 (알림 로직에서 제거)
        if days_since_last_visit >= 30 and ("next_alert_date" in pat or "notification_stage" in pat):
            db.collection("patients").document(pat["chart_no"]).update({
                "next_alert_date": firestore.DELETE_FIELD,
                "notification_stage": firestore.DELETE_FIELD
            })
            continue # 이번 목록에서 제외
            
        # 알림 날짜가 오늘이거나 이미 지난(밀린) 환자들 추출
        if next_alert_str and next_alert_str <= today_str:
            alerts_to_show.append(pat)

    # 화면에 목록 표시 및 연락 완료 처리
    if alerts_to_show:
        for a in alerts_to_show:
            stage = a.get("notification_stage", 0)
            target_days = 3 if stage == 0 else 7
            
            with st.expander(f"🚨 {a['name']} 환자님 (마지막 내원: {a['last_visit']} / {target_days}일 차 알림)", expanded=True):
                st.write(f"차트번호: {a['chart_no']}")
                
                # 연락 완료 버튼
                if st.button(f"✅ '{a['name']}' 연락 완료 처리", key=a['chart_no']):
                    patient_ref = db.collection("patients").document(a['chart_no'])
                    
                    if stage == 0:
                        # 3일 차 연락을 완료했으니, 다음은 7일 차로 세팅
                        next_date = parse_date(a['last_visit']) + timedelta(days=7)
                        patient_ref.update({
                            "notification_stage": 1,
                            "next_alert_date": next_date.strftime("%Y-%m-%d")
                        })
                        st.success(f"{a['name']} 환자 완료! 다음 알림은 7일 차에 뜹니다.")
                    else:
                        # 7일 차 연락까지 완료 (이번 사이클 종료)
                        patient_ref.update({
                            "notification_stage": 2,
                            "next_alert_date": firestore.DELETE_FIELD
                        })
                        st.success(f"{a['name']} 환자 완료! 이번 치료 주기 알림이 모두 끝났습니다.")
                    
                    # 화면 새로고침 (버튼 누르면 즉시 리스트에서 사라짐)
                    st.rerun()
    else:
        st.info("🎉 오늘 연락해야 할 환자가 없습니다! 밀린 업무가 없네요.")