import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="한의원 환자 관리 시스템", layout="wide")

st.title("🏥 환자 정보 자동 추출 시스템")
st.info("헤더 이후의 데이터를 분석하며, 첫 번째 노이즈 데이터를 제외하고 추출합니다.")

uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

if uploaded_file is not None:
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text().replace("\n", "")
    
    # 2. 데이터 시작 지점 추적 ("통장" 2회 반복 지점)
    marker = "통장"
    first_idx = full_text.find(marker)
    target_text = full_text
    
    if first_idx != -1:
        second_idx = full_text.find(marker, first_idx + len(marker))
        if second_idx != -1:
            target_text = full_text[second_idx + len(marker):]
    
    # 3. 반복 패턴 추출
    pattern = r"(\d+)([가-힣]{2,4})(\d{6})"
    matches = re.findall(pattern, target_text)
    
    # --- [핵심 수정] 첫 번째 데이터가 오류일 경우 두 번째부터 슬라이싱 ---
    if len(matches) > 1:
        actual_matches = matches[1:]  # 첫 번째(0번 index)를 버리고 1번부터 가져옴
        st.success("✅ 헤더 노이즈를 제거하고 실제 환자 명단부터 추출을 시작합니다.")
    else:
        actual_matches = matches

    if actual_matches:
        data = []
        for m in actual_matches:
            data.append({
                "내원순서": m[0],
                "환자명": m[1],
                "차트번호": m[2]
            })
        
        df = pd.DataFrame(data)
        df = df.drop_duplicates(subset=['차트번호']).reset_index(drop=True)
        
        st.subheader(f"📋 추출 결과 (총 {len(df)}명)")
        st.dataframe(df, use_container_width=True)
        
        if st.button("데이터베이스에 저장하기"):
            st.info("Firestore 연동 준비 완료!")
            
    else:
        st.error("환자 정보를 찾지 못했습니다.")

    with st.expander("🔍 분석된 실데이터 구간 확인"):
        st.text(target_text)
else:
    st.write("파일을 업로드하면 분석이 시작됩니다.")