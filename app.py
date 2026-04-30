import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(page_title="한의원 환자 관리 시스템", layout="wide")

# --- Firebase 초기화 ---
def init_firebase():
    if not firebase_admin._apps:
        key_dict = dict(st.secrets["textkey"])
        creds = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(creds)
    return firestore.client()

st.title("🏥 환자 정보 및 진료일자 자동 추출")
st.info("차트번호 뒤에 붙은 진료 날짜까지 자동으로 분류하여 저장합니다.")

uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

if uploaded_file is not None:
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    full_text = "".join([page.get_text().replace("\n", "") for page in doc])
    
    # 1. 데이터 시작 지점 추적 ("통장" 2회 반복 지점)
    marker = "통장"
    first_idx = full_text.find(marker)
    target_text = full_text
    if first_idx != -1:
        second_idx = full_text.find(marker, first_idx + len(marker))
        if second_idx != -1:
            target_text = full_text[second_idx + len(marker):]
    
    # 2. 정밀 추출 로직 (날짜 그룹 추가)
    # 그룹1:순서, 그룹2:이름, 그룹3:차트번호(6자리), 그룹4:날짜(YYYY-MM-DD 또는 YYYY.MM.DD 등)
    # 날짜 패턴을 유연하게 잡기 위해 (\d{4}[-.]\d{2}[-.]\d{2}) 형식을 추가했습니다.
    pattern = r"(\d+)([가-힣]{2,4})(\d{6})(\d{4}[-.]\d{2}[-.]\d{2})"
    matches = re.findall(pattern, target_text)
    
    # 첫 번째 줄 노이즈 제거
    if len(matches) > 1:
        actual_matches = matches[1:]
        
        # 데이터 정리 (환자명, 차트번호, 진료일자)
        data = []
        for m in actual_matches:
            data.append({
                "환자명": m[1],
                "차트번호": m[2],
                "진료일자": m[3]
            })
        
        df = pd.DataFrame(data).drop_duplicates(subset=['차트번호', '진료일자']).reset_index(drop=True)
        
        st.subheader(f"📋 추출 결과 (총 {len(df)}명)")
        st.dataframe(df, use_container_width=True)
        
        # --- 🚀 Firebase 저장 로직 (진료일자 포함) ---
        if st.button("🔥 데이터베이스에 날짜별로 저장하기"):
            try:
                db = init_firebase()
                batch = db.batch()
                
                for _, row in df.iterrows():
                    # 1. 환자 마스터 정보 업데이트 (patients 컬렉션)
                    patient_ref = db.collection("patients").document(row["차트번호"])
                    batch.set(patient_ref, {
                        "name": row["환자명"],
                        "chart_no": row["차트번호"],
                        "last_visit": row["진료일자"], # 가장 최근 진료일로 업데이트
                        "updated_at": firestore.SERVER_TIMESTAMP
                    }, merge=True)
                    
                    # 2. 상세 진료 이력 저장 (visits 하위 컬렉션)
                    # 이 부분을 추가하면 환자 한 명당 여러 날짜의 방문 기록을 다 남길 수 있습니다.
                    visit_id = f"{row['차트번호']}_{row['진료일자'].replace('-', '').replace('.', '')}"
                    visit_ref = db.collection("visits").document(visit_id)
                    batch.set(visit_ref, {
                        "chart_no": row["차트번호"],
                        "name": row["환자명"],
                        "visit_date": row["진료일자"],
                        "status": "진료완료"
                    }, merge=True)
                
                batch.commit()
                st.success(f"✅ {len(df)}명의 데이터와 진료일자가 안전하게 저장되었습니다!")
                st.balloons()
            except Exception as e:
                st.error(f"❌ 저장 중 오류 발생: {e}")
                
    else:
        st.error("환자 정보나 날짜를 찾지 못했습니다. 원본 텍스트의 날짜 형식을 확인해주세요.")

    with st.expander("🔍 원본 텍스트 확인 (날짜 형식 체크용)"):
        st.text(target_text)