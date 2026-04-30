네, 한의원 전용 소프트웨어 개발 요청에 맞춰 Streamlit 앱에 PDF에서 차트번호와 환자명을 추출하고 Firestore에 연동하는 기능을 구현한 `app.py` 코드를 작성/수정해 드리겠습니다.

Firestore 연동을 위해 `google-cloud-firestore` 라이브러리와 PDF 처리를 위한 `PyMuPDF` (fitz) 라이브러리가 필요합니다. 설치되어 있지 않다면 아래 명령어로 먼저 설치해주세요:
`pip install streamlit google-cloud-firestore PyMuPDF pandas`

**Firestore 설정 안내:**

1.  **Firebase 프로젝트 생성:** Firebase 콘솔에서 새 프로젝트를 생성합니다.
2.  **Firestore 활성화:** 프로젝트에서 Firestore Database를 활성화합니다. (Native mode 선택)
3.  **서비스 계정 키 생성:**
    *   Firebase 콘솔에서 '프로젝트 설정' -> '서비스 계정' 탭으로 이동합니다.
    *   '새 비공개 키 생성' 버튼을 클릭하여 JSON 파일을 다운로드합니다. 이 파일이 앱이 Firestore에 접근할 수 있도록 하는 인증 정보입니다.
4.  **인증 정보 설정 (두 가지 방법):**
    *   **로컬 개발 시:** 다운로드한 JSON 파일의 이름을 `serviceAccountKey.json`으로 변경하여 `app.py` 파일과 같은 디렉토리에 둡니다.
    *   **Streamlit Cloud 배포 시 (권장):**
        *   JSON 파일 내용을 복사합니다.
        *   Streamlit 앱 프로젝트의 `.streamlit` 폴더 안에 `secrets.toml` 파일을 생성합니다.
        *   `secrets.toml` 파일에 다음과 같이 추가합니다:
            toml
            [firestore_key]
            # JSON 파일의 내용을 여기에 붙여넣으세요.
            # 예:
            # type = "service_account"
            # project_id = "your-project-id"
            # private_key_id = "..."
            # private_key = "-----BEGIN PRIVATE KEY-----..."
            # client_email = "..."
            # client_id = "..."
            # auth_uri = "..."
            # token_uri = "..."
            # auth_provider_x509_cert_url = "..."
            # client_x509_cert_url = "..."
            # universe_domain = "..."
            
            `st.secrets["firestore_key"]`를 통해 이 정보를 로드할 것입니다.
            **주의:** `private_key` 값은 여러 줄로 되어 있으므로 `secrets.toml`에 붙여넣기 할 때 각 줄 앞에 `private_key = "`를 붙여주고 마지막에 `"`를 닫는 식으로 처리해야 합니다. 가장 쉬운 방법은 전체 JSON 내용을 한 줄로 만들어 저장하는 것이지만, 가독성을 위해 Streamlit Cloud의 Secrets 관리 인터페이스에서 직접 추가하는 것을 권장합니다.

아래는 `app.py` 코드입니다.


import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from google.cloud import firestore
import json
import datetime

# --- Firestore 클라이언트 초기화 함수 ---
@st.cache_resource
def get_firestore_client():
    if "firestore_client" not in st.session_state:
        try:
            # Streamlit secrets에서 Firestore 키 로드 시도 (배포 환경 권장)
            if st.secrets.get("firestore_key"):
                st.session_state.firestore_client = firestore.Client.from_service_account_info(st.secrets["firestore_key"])
                st.success("Firestore 클라이언트 초기화 완료 (Streamlit secrets).")
                return st.session_state.firestore_client
            else:
                st.warning("Streamlit secrets에 'firestore_key'가 없습니다. 로컬 'serviceAccountKey.json' 파일로 시도합니다.")

            # 로컬 serviceAccountKey.json 파일에서 Firestore 키 로드 시도 (개발 환경)
            with open("serviceAccountKey.json") as f:
                key_dict = json.load(f)
            st.session_state.firestore_client = firestore.Client.from_service_account_info(key_dict)
            st.success("Firestore 클라이언트 초기화 완료 (serviceAccountKey.json).")

        except FileNotFoundError:
            st.error("Firestore 클라이언트 초기화 실패: 'serviceAccountKey.json' 파일을 찾을 수 없습니다. (Streamlit secrets 또는 로컬 파일 필요)")
            st.session_state.firestore_client = None
        except Exception as e:
            st.error(f"Firestore 클라이언트 초기화 실패: {e}")
            st.session_state.firestore_client = None
    return st.session_state.firestore_client

# --- Streamlit 앱 시작 ---
st.set_page_config(layout="wide", page_title="한의원 일일결산서 분석")
st.title("🏥 한의원 일일결산서 PDF 분석 및 Firestore 연동")

db = get_firestore_client()

# --- 1. PDF 업로드 및 정보 추출 ---
st.header("1. PDF 일일결산서에서 정보 추출")
uploaded_file = st.file_uploader("PDF 일일결산서를 업로드하세요.", type="pdf")

extracted_data = []

if uploaded_file is not None:
    try:
        # PyMuPDF를 사용하여 PDF 텍스트 추출
        doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
        text = ""
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            text += page.get_text()
        doc.close()

        st.subheader("📄 PDF 내용 미리보기 (일부)")
        st.expander("전체 텍스트 보기", expanded=False).code(text)
        st.write(f"PDF에서 {len(text)}자 추출되었습니다.")

        if st.button("정보 추출 시작"):
            # 차트번호와 환자명 추출을 위한 정규 표현식
            # 일반적인 패턴: '차트번호: 123456 환자명: 김철수'
            # 또는 '123456 김철수' 가 특정 섹션에 등장할 수도 있음.
            # 여기서는 '차트번호' 또는 'chart no' 같은 키워드와 6자리 숫자,
            # 그리고 '환자명' 또는 'patient name' 키워드와 한국어 이름 또는 공백을 찾습니다.
            
            # 개선된 정규식: 차트번호와 환자명을 한 번에 찾아 매칭 시도
            # (?:...)는 비캡처 그룹을 의미합니다.
            # \s*는 공백 문자(0개 이상), \d{6}는 정확히 6자리 숫자, [가-힣\s]+는 한글 또는 공백(1개 이상)을 의미합니다.
            # 다양한 표기법을 고려하여 '차트번호'/'chart no'/'chart_no' 등을 포함합니다.
            # '환자명'/'patient name'/'환자' 등을 포함합니다.
            
            # 시도 1: '차트번호: 123456 환자명: 김철수' 형태
            pattern1 = re.compile(
                r'(?:차트번호|chart\s*no|차트No|차트)\s*:\s*(\d{6})\s*(?:환자명|patient\s*name|환자)\s*:\s*([가-힣\s]+)',
                re.IGNORECASE
            )
            # 시도 2: '123456 김철수'가 줄 시작 부분이나 특정 섹션에 나올 경우 (환자명 레이블 없음)
            # 이 패턴은 오탐율이 높을 수 있으므로 신중하게 사용해야 합니다.
            # 여기서는 6자리 숫자 뒤에 바로 한글 이름이 오는 경우를 가정
            pattern2 = re.compile(
                r'(\d{6})\s+([가-힣]{2,5})\b' # 6자리 숫자 뒤에 2~5글자 한글 이름 (단어 경계)
            )

            matches1 = pattern1.findall(text)
            matches2 = pattern2.findall(text)

            found_pairs = set() # 중복 제거를 위해 set 사용

            for chart_no, patient_name in matches1:
                found_pairs.add((chart_no.strip(), patient_name.strip()))
            
            # 패턴2는 오탐율이 높아 일단 주석 처리합니다.
            # 실제 데이터에 맞춰서 필요 시 활성화하고, 주변 텍스트와 함께 검증하는 로직이 필요합니다.
            # for chart_no, patient_name in matches2:
            #     # 패턴2의 경우, '환자명:' 레이블이 없기 때문에 오탐 방지를 위해 추가적인 검증이 필요할 수 있습니다.
            #     # 예를 들어, 해당 텍스트 주변에 다른 숫자가 없는지, 혹은 패턴1이 놓친 케이스만 보충하는 식으로.
            #     found_pairs.add((chart_no.strip(), patient_name.strip()))

            if found_pairs:
                extracted_data = [{"차트번호": cn, "환자명": pn} for cn, pn in sorted(list(found_pairs))]
                
                df_extracted = pd.DataFrame(extracted_data)
                st.session_state.extracted_df = df_extracted
                
                st.subheader("✅ 추출된 환자 정보")
                st.dataframe(df_extracted, use_container_width=True)
                st.success(f"{len(extracted_data)} 건의 정보를 추출했습니다.")
            else:
                st.info("PDF에서 차트번호와 환자명 정보를 찾을 수 없습니다. 정규 표현식을 확인하거나 PDF 형식을 검토해주세요.")
                st.session_state.extracted_df = pd.DataFrame(columns=["차트번호", "환자명"])

    except fitz.FileDataError:
        st.error("업로드된 파일이 유효한 PDF 파일이 아닙니다.")
    except Exception as e:
        st.error(f"PDF 처리 중 오류가 발생했습니다: {e}")

# --- 2. 추출된 데이터 Firestore에 저장 ---
st.header("2. 추출된 데이터를 Firestore에 저장")
if db and 'extracted_df' in st.session_state and not st.session_state.extracted_df.empty:
    if st.button("✅ 추출된 데이터 Firestore에 저장"):
        collection_name = "daily_settlements"
        with st.spinner("Firestore에 데이터를 저장 중..."):
            for index, row in st.session_state.extracted_df.iterrows():
                data_to_save = {
                    "chart_number": row["차트번호"],
                    "patient_name": row["환자명"],
                    "extraction_date": firestore.SERVER_TIMESTAMP # 서버 타임스탬프 사용
                }
                if data_to_save["chart_number"] and data_to_save["patient_name"]:
                    try:
                        # 동일한 차트번호 + 환자명 조합이 이미 있는지 확인 후 저장
                        # 실제 운영에서는 차트번호를 document ID로 사용하여 덮어쓰거나, 고유 ID를 생성하는 방식 고려
                        existing_doc = db.collection(collection_name).where("chart_number", "==", data_to_save["chart_number"]).where("patient_name", "==", data_to_save["patient_name"]).get()
                        if not existing_doc:
                            db.collection(collection_name).add(data_to_save)
                            st.success(f"데이터 저장 완료: 차트번호 '{data_to_save['chart_number']}', 환자명 '{data_to_save['patient_name']}'")
                        else:
                            st.info(f"이미 존재하는 데이터: 차트번호 '{data_to_save['chart_number']}', 환자명 '{data_to_save['patient_name']}' (저장 스킵)")
                    except Exception as e:
                        st.error(f"Firestore 저장 실패 (차트번호: {data_to_save['chart_number']}): {e}")
                else:
                    st.warning(f"일부 데이터가 누락되어 저장되지 않았습니다: {row}")
    
    st.markdown("---")
else:
    st.info("먼저 PDF에서 정보를 추출해야 Firestore에 저장할 수 있습니다.")


# --- 3. Firestore에 저장된 데이터 확인 ---
st.header("3. Firestore에 저장된 데이터 확인")
if db:
    if st.button("📊 Firestore 데이터 불러오기"):
        collection_name = "daily_settlements"
        try:
            with st.spinner("Firestore에서 데이터를 불러오는 중..."):
                docs = db.collection(collection_name).stream()
                firestore_data = []
                for doc in docs:
                    d = doc.to_dict()
                    d["Document ID"] = doc.id # Firestore 문서 ID 추가
                    
                    # Firestore TIMESTAMP를 datetime 객체로 변환하여 표시
                    if isinstance(d.get("extraction_date"), datetime.datetime):
                        d["extraction_date"] = d["extraction_date"].strftime("%Y-%m-%d %H:%M:%S")
                    
                    firestore_data.append(d)

            if firestore_data:
                df_firestore = pd.DataFrame(firestore_data)
                df_firestore = df_firestore[["chart_number", "patient_name", "extraction_date", "Document ID"]] # 순서 재정렬
                st.subheader("📋 Firestore에 저장된 일일결산 데이터")
                st.dataframe(df_firestore, use_container_width=True)
                st.success(f"Firestore에서 {len(firestore_data)} 건의 데이터를 불러왔습니다.")
            else:
                st.info("Firestore 컬렉션에 저장된 데이터가 없습니다.")
        except Exception as e:
            st.error(f"Firestore에서 데이터 불러오기 실패: {e}")
else:
    st.warning("Firestore 클라이언트가 초기화되지 않아 데이터베이스 기능을 사용할 수 없습니다.")

st.markdown("---")
st.caption("© 2023 한의원 전용 소프트웨어. Streamlit & Firestore 기반.")