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
# 탭 1: PDF 업로드 및 지능형 저장 로직
# ==========================================
with tab1:
    st.info("원장님 성함(이차로)이 포함된 유효한 데이터만 자동으로 추출합니다.")
    uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

    if uploaded_file is not None:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        full_text = "".join([page.get_text().replace("\n", "") for page in doc])
        
        # 1. 데이터 시작 마커 찾기
        marker = "통장"
        first_idx = full_text.find(marker)
        target_text = full_text
        if first_idx != -1:
            second_idx = full_text.find(marker, first_idx + len(marker))
            if second_idx != -1:
                target_text = full_text[second_idx + len(marker):]
        
        # 2. 유효 데이터 패턴 (차트번호 + 날짜 + 원장님 성함 필수)
        # 그룹2: 환자명, 그룹3: 차트번호, 그룹4: 진료일자
        # 패턴 끝에 '이차로'를 명시하여 유효 데이터만 낚아챕니다.
        pattern = r"(\d+)([가-힣]{2,4})(\d{6})(\d{4}[-.]\d{2}[-.]\d{2})이차로"
        matches = re.findall(pattern, target_text)
        
        if len(matches) > 0:
            # [수정] 무조건 matches[1:] 하던 코드를 삭제하고, 모든 matches를 유효 데이터로 봅니다.
            data = [{"환자명": m[1], "차트번호": m[2], "진료일자": m[3].replace(".", "-")} for m in matches]
            df = pd.DataFrame(data).drop_duplicates(subset=['차트번호', '진료일자'])
            
            df['date_obj'] = df['진료일자'].apply(parse_date)
            df = df.sort_values(by='date_obj').reset_index(drop=True)
            
            st.subheader(f"📋 확인된 유효 데이터 (총 {len(df)}건)")
            st.dataframe(df[["환자명", "차트번호", "진료일자"]], use_container_width=True)
            
            if st.button("🔥 데이터 분석 및 저장 실행"):
                try:
                    new_count = 0
                    duplicates = []

                    for _, row in df.iterrows():
                        visit_id = f"{row['차트번호']}_{row['진료일자'].replace('-', '')}"
                        visit_ref = db.collection("visits").document(visit_id)
                        
                        if visit_ref.get().exists:
                            duplicates.append(f"{row['환자명']}({row['진료일자']})")
                            continue
                        
                        new_count += 1
                        current_visit_obj = row['date_obj']
                        patient_ref = db.collection("patients").document(row["차트번호"])
                        doc_snap = patient_ref.get()
                        
                        stage = 0
                        if doc_snap.exists:
                            pat_data = doc_snap.to_dict()
                            last_v_str = pat_data.get("last_visit", "2000-01-01")
                            last_v_obj = parse_date(last_v_str)
                            old_next_alert = pat_data.get("next_alert_date")
                            
                            if (current_visit_obj - last_v_obj).days > 30:
                                stage = 0
                            elif old_next_alert and parse_date(old_next_alert) <= current_visit_obj:
                                stage = 1
                            else:
                                stage = pat_data.get("notification_stage", 0)
                        
                        next_date = (current_visit_obj + timedelta(days=3)).strftime("%Y-%m-%d") if stage == 0 else (current_visit_obj + timedelta(days=7)).strftime("%Y-%m-%d")

                        patient_ref.set({
                            "name": row["환자명"],
                            "chart_no": row["차트번호"],
                            "last_visit": row["진료일자"],
                            "notification_stage": stage,
                            "next_alert_date": next_date,
                            "updated_at": firestore.SERVER_TIMESTAMP
                        }, merge=True)
                        
                        visit_ref.set({
                            "chart_no": row["차트번호"],
                            "name": row["환자명"],
                            "visit_date": row["진료일자"],
                            "created_at": firestore.SERVER_TIMESTAMP
                        })

                    if new_count > 0:
                        st.success(f"✅ {new_count}건의 데이터가 성공적으로 처리되었습니다!")
                        st.balloons()
                    if duplicates:
                        st.warning(f"⚠️ 이미 처리된 {len(duplicates)}건은 제외되었습니다.")
                
                except Exception as e:
                    st.error(f"❌ 오류: {e}")
        else:
            st.error("유효한 데이터(날짜+이차로)를 찾지 못했습니다. 원본 텍스트를 확인해주세요.")

    with st.expander("🔍 원본 텍스트 확인"):
        st.text(target_text)

# (해피콜 타임라인 탭은 기존과 동일)
with tab2:
    # ... (기존 코드와 동일)
