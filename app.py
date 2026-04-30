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

tab1, tab2 = st.tabs(["📄 일일결산 PDF 업로드", "🔔 오늘 연락할 환자 (해피콜)"])

# ==========================================
# 탭 1: PDF 업로드 및 저장 (중복 체크 강화)
# ==========================================
with tab1:
    st.info("중복된 진료 데이터는 자동으로 걸러지며 저장되지 않습니다.")
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
                        # 중복 여부 확인용 고유 ID 생성 (차트번호_날짜)
                        visit_id = f"{row['차트번호']}_{row['진료일자'].replace('-', '')}"
                        visit_ref = db.collection("visits").document(visit_id)
                        
                        # [핵심] 이미 해당 날짜의 진료 기록이 있는지 확인
                        if visit_ref.get().exists:
                            duplicate_names.append(f"{row['환자명']}({row['차트번호']})")
                            continue
                        
                        # 중복이 아닐 경우 저장 진행
                        new_count += 1
                        visit_date_obj = parse_date(row["진료일자"])
                        
                        # 환자 마스터 정보 확인 및 알림 단계 설정
                        patient_ref = db.collection("patients").document(row["차트번호"])
                        doc_snap = patient_ref.get()
                        
                        stage = 0
                        if doc_snap.exists:
                            pat_data = doc_snap.to_dict()
                            last_visit_str = pat_data.get("last_visit", "2000-01-01")
                            days_passed = (visit_date_obj - parse_date(last_visit_str)).days
                            if days_passed <= 30:
                                stage = pat_data.get("notification_stage", 0)
                        
                        next_alert_date = (visit_date_obj + timedelta(days=3)).strftime("%Y-%m-%d") if stage == 0 else (visit_date_obj + timedelta(days=7)).strftime("%Y-%m-%d") if stage == 1 else None

                        # 1. 마스터 정보 업데이트
                        batch.set(patient_ref, {
                            "name": row["환자명"],
                            "chart_no": row["차트번호"],
                            "last_visit": row["진료일자"],
                            "notification_stage": stage,
                            "next_alert_date": next_alert_date,
                            "updated_at": firestore.SERVER_TIMESTAMP
                        }, merge=True)
                        
                        # 2. 상세 진료 기록 저장
                        batch.set(visit_ref, {
                            "chart_no": row["차트번호"],
                            "name": row["환자명"],
                            "visit_date": row["진료일자"],
                            "created_at": firestore.SERVER_TIMESTAMP
                        })

                    # 결과 리포트
                    if new_count > 0:
                        batch.commit()
                        st.success(f"✅ 새롭게 {new_count}명의 데이터가 저장되었습니다!")
                        st.balloons()
                    
                    if duplicate_names:
                        st.warning(f"⚠️ 아래 데이터는 이미 저장되어 있어 제외되었습니다:\n\n{', '.join(duplicate_names)}")
                        
                except Exception as e:
                    st.error(f"❌ 오류 발생: {e}")

# ==========================================
# 탭 2: 해피콜 알림 대시보드 (기존 동일)
# ==========================================
with tab2:
    st.subheader("📞 오늘 연락해야 할 환자 목록")
    today_obj = datetime.now()
    today_str = today_obj.strftime("%Y-%m-%d")
    patients_ref = db.collection("patients").stream()
    
    alerts_to_show = []
    for doc in patients_ref:
        pat = doc.to_dict()
        last_visit_str = pat.get("last_visit")
        next_alert_str = pat.get("next_alert_date")
        if not last_visit_str: continue
        
        days_since_last_visit = (today_obj - parse_date(last_visit_str)).days
        if days_since_last_visit >= 30 and ("next_alert_date" in pat or "notification_stage" in pat):
            db.collection("patients").document(pat["chart_no"]).update({
                "next_alert_date": firestore.DELETE_FIELD,
                "notification_stage": firestore.DELETE_FIELD
            })
            continue
            
        if next_alert_str and next_alert_str <= today_str:
            alerts_to_show.append(pat)

    if alerts_to_show:
        for a in alerts_to_show:
            stage = a.get("notification_stage", 0)
            target_days = 3 if stage == 0 else 7
            with st.expander(f"🚨 {a['name']} 환자님 ({target_days}일 차 알림)", expanded=True):
                if st.button(f"✅ '{a['name']}' 연락 완료 처리", key=a['chart_no']):
                    new_stage = stage + 1
                    update_data = {"notification_stage": new_stage}
                    if new_stage == 1:
                        update_data["next_alert_date"] = (parse_date(a['last_visit']) + timedelta(days=7)).strftime("%Y-%m-%d")
                    else:
                        update_data["next_alert_date"] = firestore.DELETE_FIELD
                    db.collection("patients").document(a['chart_no']).update(update_data)
                    st.rerun()
    else:
        st.info("🎉 오늘 연락해야 할 환자가 없습니다.")