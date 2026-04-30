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

def parse_date(date_str):
    clean_str = date_str.replace(".", "-")
    return datetime.strptime(clean_str, "%Y-%m-%d")

st.title("🏥 한의원 스마트 CRM 시스템")

tab1, tab2 = st.tabs(["📄 일일결산 PDF 업로드", "🔔 해피콜 타임라인 (5일)"])

# ==========================================
# 탭 1: PDF 업로드 및 저장 (기존 동일)
# ==========================================
with tab1:
    st.info("결산서를 업로드하여 환자 정보와 진료일자를 등록하세요. 중복은 자동 필터링됩니다.")
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
            
            if st.button("🔥 데이터베이스 저장 실행"):
                try:
                    batch = db.batch()
                    new_count = 0
                    duplicate_names = []

                    for _, row in df.iterrows():
                        visit_id = f"{row['차트번호']}_{row['진료일자'].replace('-', '')}"
                        visit_ref = db.collection("visits").document(visit_id)
                        
                        if visit_ref.get().exists:
                            duplicate_names.append(f"{row['환자명']}({row['차트번호']})")
                            continue
                        
                        new_count += 1
                        visit_date_obj = parse_date(row["진료일자"])
                        
                        patient_ref = db.collection("patients").document(row["차트번호"])
                        doc_snap = patient_ref.get()
                        
                        stage = 0
                        if doc_snap.exists:
                            pat_data = doc_snap.to_dict()
                            last_visit_str = pat_data.get("last_visit", "2000-01-01")
                            if (visit_date_obj - parse_date(last_visit_str)).days <= 30:
                                stage = pat_data.get("notification_stage", 0)
                        
                        next_alert_date = (visit_date_obj + timedelta(days=3)).strftime("%Y-%m-%d") if stage == 0 else (visit_date_obj + timedelta(days=7)).strftime("%Y-%m-%d") if stage == 1 else None

                        batch.set(patient_ref, {
                            "name": row["환자명"],
                            "chart_no": row["차트번호"],
                            "last_visit": row["진료일자"],
                            "notification_stage": stage,
                            "next_alert_date": next_alert_date,
                            "updated_at": firestore.SERVER_TIMESTAMP
                        }, merge=True)
                        
                        batch.set(visit_ref, {
                            "chart_no": row["차트번호"],
                            "name": row["환자명"],
                            "visit_date": row["진료일자"],
                            "created_at": firestore.SERVER_TIMESTAMP
                        })

                    if new_count > 0:
                        batch.commit()
                        st.success(f"✅ 새롭게 {new_count}명의 데이터가 저장되었습니다!")
                        st.balloons()
                    if duplicate_names:
                        st.warning(f"⚠️ 이미 저장된 환자 {len(duplicate_names)}명은 제외되었습니다.")
                        
                except Exception as e:
                    st.error(f"❌ 오류 발생: {e}")

# ==========================================
# 탭 2: 해피콜 타임라인 (전후 2일 포함)
# ==========================================
with tab2:
    today_obj = datetime.now()
    
    # 5일간의 타임라인 생성 (-2일 ~ +2일)
    timeline_dates = [(today_obj + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(-2, 3)]
    
    st.markdown("### 📅 해피콜 스케줄 보드 (최근 5일)")
    
    # 데이터를 날짜별로 담을 딕셔너리 준비
    alerts_by_date = {date: [] for date in timeline_dates}
    
    # Firestore에서 환자 데이터 가져오기
    patients_ref = db.collection("patients").stream()
    
    for doc in patients_ref:
        pat = doc.to_dict()
        last_visit_str = pat.get("last_visit")
        next_alert_str = pat.get("next_alert_date")
        
        if not last_visit_str: continue
        
        # 30일 경과 시 알림 삭제 로직
        days_since_last_visit = (today_obj - parse_date(last_visit_str)).days
        if days_since_last_visit >= 30 and ("next_alert_date" in pat or "notification_stage" in pat):
            db.collection("patients").document(pat["chart_no"]).update({
                "next_alert_date": firestore.DELETE_FIELD,
                "notification_stage": firestore.DELETE_FIELD
            })
            continue
            
        # 다음 알림일이 타임라인 5일 안에 속하는지 확인
        if next_alert_str in alerts_by_date:
            alerts_by_date[next_alert_str].append(pat)
        # 만약 어제보다 더 과거에 밀린 연락이 있다면 '어제(-2일)' 칸에 함께 표시
        elif next_alert_str and next_alert_str < timeline_dates[0]:
            alerts_by_date[timeline_dates[0]].append(pat)

    # UI 구성 (5개의 컬럼으로 나누어 달력처럼 표시)
    cols = st.columns(5)
    labels = ["D-2 (밀림)", "D-1 (어제)", "✨ TODAY ✨", "D+1 (내일)", "D+2 (모레)"]
    
    for idx, (col, date_str) in enumerate(zip(cols, timeline_dates)):
        with col:
            # '오늘' 열을 시각적으로 강하게 강조
            if idx == 2:
                st.markdown(f"### 🎯 **{labels[idx]}**")
                st.markdown(f"**{date_str}**")
                st.markdown("---")
            else:
                st.markdown(f"**{labels[idx]}**")
                st.caption(date_str)
                st.markdown("---")
                
            # 해당 날짜의 환자 목록 출력
            patients_for_day = alerts_by_date[date_str]
            if not patients_for_day:
                st.write("대기 없음")
            else:
                for a in patients_for_day:
                    stage = a.get("notification_stage", 0)
                    target_days = 3 if stage == 0 else 7
                    
                    # 카드 스타일의 컨테이너
                    with st.container():
                        st.markdown(f"**{a['name']}** ({target_days}일차)")
                        # [연락 완료] 버튼 (누르면 다음 스테이지로 넘어감)
                        if st.button("✅ 완료", key=f"{a['chart_no']}_{date_str}"):
                            new_stage = stage + 1
                            update_data = {"notification_stage": new_stage}
                            if new_stage == 1:
                                update_data["next_alert_date"] = (parse_date(a['last_visit']) + timedelta(days=7)).strftime("%Y-%m-%d")
                            else:
                                update_data["next_alert_date"] = firestore.DELETE_FIELD
                                
                            db.collection("patients").document(a['chart_no']).update(update_data)
                            st.rerun() # 완료 후 즉시 화면 새로고침
                        st.markdown("---")