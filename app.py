import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="한의원 환자 관리 시스템", layout="wide")

st.title("🏥 환자 정보 자동 추출 시스템")
st.info("PDF 일일결산서를 업로드하면 성함과 차트번호를 자동으로 분류합니다.")

uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

if uploaded_file is not None:
    # 1. PDF 텍스트 추출
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    
    # 2. 정밀 추출 로직 (5김준007217 패턴 타격)
    # 그룹1: 내원번호(\d+), 그룹2: 이름([가-힣]{2,4}), 그룹3: 차트번호(\d{6})
    pattern = r"(\d+)([가-힣]{2,4})(\d{6})"
    matches = re.findall(pattern, full_text)
    
    if matches:
        st.success(f"총 {len(matches)}명의 환자 정보를 찾았습니다!")
        
        # 데이터 정리 (중복 제거 및 표 구성)
        data = []
        for match in matches:
            data.append({
                "내원순서": match[0],
                "환자명": match[1],
                "차트번호": match[2]
            })
        
        df = pd.DataFrame(data)
        
        # 화면 출력
        st.subheader("📋 추출된 환자 명단")
        st.dataframe(df, use_container_width=True)
        
        # 3. Firestore 연동 준비 (구조만 잡기)
        if st.button("데이터베이스(Firestore)에 저장하기"):
            st.warning("Firestore 연결 설정이 필요합니다. (Secrets 설정 확인)")
            # 원장님, 여기에 나중에 Firebase 저장 로직이 들어갑니다.
            
    else:
        st.error("환자 정보를 찾을 수 없습니다. 아래 원본 텍스트를 확인해 주세요.")

    # 4. 디버깅용 원본 텍스트 보기
    with st.expander("🔍 PDF 원본 텍스트 확인 (추출이 안 될 때 확인용)"):
        st.text(full_text)

else:
    st.write("파일을 업로드하면 분석이 시작됩니다.")