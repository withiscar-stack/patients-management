import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd

st.set_page_config(page_title="한의원 환자 관리 시스템", layout="wide")

st.title("🏥 환자 정보 자동 추출 시스템")
st.info("헤더('통장' 2회 반복) 이후의 실데이터를 정밀하게 추출합니다.")

uploaded_file = st.file_uploader("PDF 파일을 업로드하세요", type=['pdf'])

if uploaded_file is not None:
    # 1. PDF 전체 텍스트 추출
    doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    full_text = ""
    for page in doc:
        # 텍스트 간의 공백을 최소화하여 읽어들임
        full_text += page.get_text().replace("\n", "")
    
    # 2. 데이터 시작 지점 정밀 추적
    # "통장"이라는 단어가 두 번째로 나타나는 위치를 찾습니다.
    marker = "통장"
    first_idx = full_text.find(marker)
    target_text = full_text
    
    if first_idx != -1:
        second_idx = full_text.find(marker, first_idx + len(marker))
        if second_idx != -1:
            # 두 번째 "통장" 단어 바로 다음부터가 실제 데이터 구역
            target_text = full_text[second_idx + len(marker):]
            st.success("✅ 데이터 시작 구간(헤더 종료 지점)을 성공적으로 포착했습니다.")
    
    # 3. 반복 패턴 추출 (숫자 + 이름 + 차트번호6자리)
    # (\d+): 내원순서, ([가-힣]{2,4}): 이름, (\d{6}): 차트번호
    # 데이터 사이의 잡음을 건너뛰기 위해 패턴을 유연하게 잡습니다.
    pattern = r"(\d+)([가-힣]{2,4})(\d{6})"
    matches = re.findall(pattern, target_text)
    
    if matches:
        data = []
        for m in matches:
            data.append({
                "내원순서": m[0],
                "환자명": m[1],
                "차트번호": m[2]
            })
        
        df = pd.DataFrame(data)
        # 차트번호 기준 중복 제거 (데이터가 겹쳐 읽히는 경우 방지)
        df = df.drop_duplicates(subset=['차트번호']).reset_index(drop=True)
        
        st.subheader(f"📋 추출 결과 (총 {len(df)}명)")
        st.dataframe(df, use_container_width=True)
        
        # 4. 저장 버튼
        if st.button("데이터베이스에 저장하기"):
            st.info("Firestore 연동을 위한 준비가 완료되었습니다.")
            
    else:
        st.error("데이터 구역에서 환자 패턴을 찾지 못했습니다. 아래 원본을 확인해주세요.")

    # 5. 디버깅용 원본 확인
    with st.expander("🔍 분석된 실데이터 구간 확인"):
        st.text(target_text)

else:
    st.write("파일을 업로드하면 분석이 시작됩니다.")