import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="한의원 환자 관리 시스템", layout="wide")

st.title("🏥 환자 정보 자동 추출 시스템")
st.info("'환자목록' 및 '통장' 키워드 이후의 데이터를 정밀 분석합니다.")

uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

if uploaded_file is not None:
    # 1. PDF 전체 텍스트 추출
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text()
    
    # 2. 데이터 시작 지점 필터링 (원장님이 발견하신 규칙 적용)
    # "환자목록"을 찾고, 그 뒤에 나오는 "통장" 위치를 찾습니다.
    target_text = full_text
    start_marker = "환자목록"
    sub_marker = "통장"
    
    start_pos = full_text.find(start_marker)
    if start_pos != -1:
        sub_pos = full_text.find(sub_marker, start_pos)
        if sub_pos != -1:
            # "통장" 글자 이후부터만 분석 대상으로 삼음
            target_text = full_text[sub_pos + len(sub_marker):]
            st.success("'통장' 키워드 이후의 데이터 구간을 확인했습니다.")
    
    # 3. 정밀 추출 로직 (5김준007217 패턴)
    pattern = r"(\d+)([가-힣]{2,4})(\d{6})"
    matches = re.findall(pattern, target_text)
    
    if matches:
        # 데이터 정리 (내원순서, 환자명, 차트번호)
        data = []
        for m in matches:
            data.append({
                "내원순서": m[0],
                "환자명": m[1],
                "차트번호": m[2]
            })
        
        df = pd.DataFrame(data)
        # 중복 데이터 제거 (혹시 모를 중복 방지)
        df = df.drop_duplicates(subset=['차트번호'])
        
        st.subheader(f"📋 추출 결과 (총 {len(df)}명)")
        st.dataframe(df, use_container_width=True)
        
        # 4. 저장 버튼
        if st.button("데이터베이스에 저장하기"):
            st.info("Firestore 연동 로직 대기 중...")
            
    else:
        st.error("데이터 구간에서 환자 정보를 찾지 못했습니다. 원본을 다시 확인해주세요.")

    # 5. 디버깅용 원본 확인
    with st.expander("🔍 분석된 텍스트 구간 확인"):
        st.text(target_text)

else:
    st.write("파일을 업로드하면 분석이 시작됩니다.")