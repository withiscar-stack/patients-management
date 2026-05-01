import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone # timezone 추가

st.set_page_config(page_title="한의원 스마트 CRM", layout="wide")

# --- 한국 시간(KST) 설정 ---
KST = timezone(timedelta(hours=9))

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
    st.info("한국 시간(KST) 기준으로 알림 날짜를 정확히 계산합니다.")
    uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

    if uploaded_file is not None:
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        full_text = "".join([page.get_text() for page in doc])
        
        marker = "통장"
        first_idx = full_text.find(marker)
        target_text = full_text
        if first_idx != -1:
            second_idx = full_text.find(marker, first_idx + len(marker))
            if second_idx != -1:
                target_text = full_text[second_idx + len(marker):]
        
        pattern = r"(\d+)\s*([가-힣]{2,10})\s*(\d{6})\s*(\d{4}[-.]\d{2}[-.]\d{2})\s*이차로"
        matches = re.findall(pattern, target_text)
        
        if len(matches) > 0:
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
                    batch = db.batch()

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

                        batch.set(patient_ref, {
                            "name": row["환자명"],
                            "chart_no": row["차트번호"],
                            "last_visit": row["진료일자"],
                            "notification_stage": stage,
                            "next_alert_date": next_date,
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
                        st.success(f"✅ {new_count}건의 데이터가 성공적으로 처리되었습니다!")
                        st.balloons()
                    if duplicates:
                        st.warning(f"⚠️ 이미 처리된 {len(duplicates)}건은 제외되었습니다.")
                
                except Exception as e:
                    st.error(f"❌ 오류: {e}")
        else:
            st.error("데이터를 찾지 못했습니다. 아래 '원본 텍스트'를 확인해주세요.")

    with st.expander("🔍 원본 텍스트 확인"):
        st.text(target_text)

# ==========================================
# 탭 2: 해피콜 타임라인 (KST 적용)
# ==========================================
with tab2:
    # [수정] 한국 시간 기준으로 오늘 날짜 가져오기
    today_obj = datetime.now(KST)
    timeline_dates = [(today_obj + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(-2, 3)]
    
    st.markdown("### 📅 해피콜 스케줄 보드 (한국 시간 기준)")
    alerts_by_date = {date: [] for date in timeline_dates}
    
    patients_ref = db.collection("patients").stream()
    for doc in patients_ref:
        pat = doc.to_dict()
        next_alert = pat.get("next_alert_date")
        last_visit = pat.get("last_visit")
        if not next_alert or not last_visit: continue
        
        # 한국 시간 기준으로 30일 경과 체크
        if (today_obj.replace(tzinfo=None) - parse_date(last_visit)).days >= 30:
            db.collection("patients").document(doc.id).update({
                "next_alert_date": firestore.DELETE_FIELD,
                "notification_stage": firestore.DELETE_FIELD
            })
            continue

        if next_alert in alerts_by_date:
            alerts_by_date[next_alert].append(pat)
        elif next_alert < timeline_dates[0]:
            alerts_by_date[timeline_dates[0]].append(pat)

    cols = st.columns(5)
    labels = ["D-2 (밀림)", "D-1", "✨ TODAY ✨", "D+1", "D+2"]
    for idx, (col, d_str) in enumerate(zip(cols, timeline_dates)):
        with col:
            if idx == 2:
                st.markdown(f"#### 🎯 **{labels[idx]}**")
                st.info(f"**{d_str}**")
            else:
                st.markdown(f"**{labels[idx]}**")
                st.caption(d_str)
            st.markdown("---")
            for p in alerts_by_date[d_str]:
                stage_text = "3일차" if p.get("notification_stage") == 0 else "7일차"
                st.write(f"**{p['name']}** ({stage_text})")
                st.markdown("---")