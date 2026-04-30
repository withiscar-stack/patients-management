import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
import firebase_admin
from firebase_admin import credentials, firestore

st.set_page_config(page_title="한의원 환자 관리 시스템", layout="wide")

# --- Firebase 초기화 ---
def init_firebase():
    # 이미 초기화된 앱이 없을 때만 실행
    if not firebase_admin._apps:
        # Streamlit Secrets에서 JSON 정보를 딕셔너리로 가져옴
        key_dict = dict(st.secrets["textkey"])
        creds = credentials.Certificate(key_dict)
        firebase_admin.initialize_app(creds)
    return firestore.client()

st.title("🏥 환자 정보 자동 추출 시스템")
st.info("PDF를 업로드하고 추출된 환자 명단을 Firebase에 저장하세요.")

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
    
    pattern = r"(\d+)([가-힣]{2,4})(\d{6})"
    matches = re.findall(pattern, target_text)
    
    # 첫 번째 노이즈(오류) 제외
    if len(matches) > 1:
        actual_matches = matches[1:]
        
        # 내원순서 제외, 이름과 차트번호만 수집
        data = [{"환자명": m[1], "차트번호": m[2]} for m in actual_matches]
        df = pd.DataFrame(data).drop_duplicates(subset=['차트번호']).reset_index(drop=True)
        
        st.subheader(f"📋 추출 결과 (총 {len(df)}명)")
        st.dataframe(df, use_container_width=True)
        
        # --- 🚀 실제 Firebase 저장 버튼 ---
        if st.button("🔥 데이터베이스(Firestore)에 최종 저장하기"):
            try:
                # Firestore 연결
                db = init_firebase()
                batch = db.batch() # 여러 개를 한 번에 저장 (배치 처리)
                
                # 데이터베이스의 'patients' 컬렉션(폴더)에 저장
                for _, row in df.iterrows():
                    # 문서 이름(ID)을 차트번호로 설정 (중복 저장 방지)
                    doc_ref = db.collection("patients").document(row["차트번호"])
                    batch.set(doc_ref, {
                        "name": row["환자명"],
                        "chart_no": row["차트번호"],
                        "last_visit_recorded": firestore.SERVER_TIMESTAMP
                    }, merge=True) # 기존 정보가 있으면 덮어쓰기
                
                batch.commit() # 실제 저장 실행!
                st.success(f"🎉 성공적으로 {len(df)}명의 환자 정보가 저장되었습니다!")
                st.balloons()
            except Exception as e:
                st.error(f"❌ 저장 중 오류 발생: {e}")
                
    else:
        st.error("데이터를 찾을 수 없습니다. 원본 텍스트를 확인해주세요.")

    with st.expander("🔍 원본 텍스트 확인"):
        st.text(target_text)