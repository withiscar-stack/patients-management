import streamlit as st
import fitz  # PyMuPDF
import re
import pandas as pd
from google.cloud import firestore
import json
import datetime
import io # io 모듈 추가: uploaded_file.read()의 반환값을 fitz.open에서 사용하기 위해 bytes-like object로 처리

# --- Firestore 클라이언트 초기화 함수 ---
@st.cache_resource
def get_firestore_client():
    if "firestore_client" not in st.session_state:
        try:
            # Streamlit secrets에서 Firestore 키 로드 시도 (배포 환경 권장)
            if st.secrets.get("firestore_key"):
                # secrets에서 직접 딕셔너리를 반환하는 경우를 처리
                key_info = st.secrets["firestore_key"]
                if isinstance(key_info, str): # 문자열이라면 JSON 파싱 시도
                    key_info = json.loads(key_info)
                st.session_state.firestore_client = firestore.Client.from_service_account_info(key_info)
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
        except json.JSONDecodeError:
            st.error("Firestore 클라이언트 초기화 실패: Streamlit secrets의 'firestore_key'가 유효한 JSON 형식이 아닙니다.")
            st.session_state.firestore_client = None
        except Exception as e:
            st.error(f"Firestore 클라이언트 초기화 실패: {e}")
            st.session_state.firestore_client = None
    return st.session_state.firestore_client

# --- PDF 텍스트 추출 함수 ---
def extract_text_from_pdf(uploaded_file):
    """
    업로드된 PDF 파일에서 텍스트를 추출합니다.
    Args:
        uploaded_file: Streamlit file_uploader로 업로드된 파일 객체.
    Returns:
        str: PDF에서 추출된 전체 텍스트.
    Raises:
        fitz.FileDataError: 파일이 유효한 PDF가 아닐 때.
        Exception: 그 외 PDF 처리 중 발생한 오류.
    """
    try:
        # uploaded_file.read()는 bytes를 반환하므로, io.BytesIO를 사용해 fitz.open에 전달
        doc = fitz.open(stream=io.BytesIO(uploaded_file.read()), filetype="pdf")
        text = ""
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            text += page.get_text()
        doc.close()
        return text
    except fitz.FileDataError:
        raise fitz.FileDataError("업로드된 파일이 유효한 PDF 파일이 아닙니다.")
    except Exception as e:
        raise Exception(f"PDF 처리 중 오류가 발생했습니다: {e}")

# --- 환자 정보 추출 함수 ---
def extract_patient_info(pdf_text):
    """
    PDF 텍스트에서 차트번호와 환자명 정보를 추출합니다.
    Args:
        pdf_text (str): PDF에서 추출된 전체 텍스트.
    Returns:
        list[dict]: 추출된 환자 정보 리스트 (예: [{"차트번호": "123456", "환자명": "김철수"}]).
    """
    found_pairs = set() # 중복 제거를 위해 set 사용

    # 시도 1: '차트번호: 123456 환자명: 김철수' 형태
    # '차트번호', 'chart no', '차트No', '차트' 중 하나, 공백, 콜론, 공백, 6자리 숫자 캡처
    # '환자명', 'patient name', '환자' 중 하나, 공백, 콜론, 공백, 한글 또는 공백 캡처
    pattern1 = re.compile(
        r'(?:차트번호|chart\s*no|차트No|차트)\s*:\s*(\d{6})\s*(?:환자명|patient\s*name|환자)\s*:\s*([가-힣\s]+)',
        re.IGNORECASE
    )

    matches1 = pattern1.findall(pdf_text)
    for chart_no, patient_name in matches1:
        found_pairs.add((chart_no.strip(), patient_name.strip()))

    # 참고: '123456 김철수'와 같이 레이블 없는 패턴은 오탐율이 높아 주석 처리합니다.
    # 만약 이런 형식이 반드시 필요하다면, 해당 텍스트 주변의 맥락을 고려하는 복잡한 로직이 필요합니다.
    # pattern2 = re.compile(r'(\d{6})\s+([가-힣]{2,5})\b')
    # matches2 = pattern2.findall(pdf_text)
    # for chart_no, patient_name in matches2:
    #     found_pairs.add((chart_no.strip(), patient_name.strip()))

    return [{"차트번호": cn, "환자명": pn} for cn, pn in sorted(list(found_pairs))]


# --- Streamlit 앱 시작 ---
st.set_page_config(layout="wide", page_title="한의원 일일결산서 분석")
st.title("🏥 한의원 일일결산서 PDF 분석 및 Firestore 연동")

db = get_firestore_client()

# --- 1. PDF 업로드 및 정보 추출 ---
st.header("1. PDF 일일결산서에서 정보 추출")
uploaded_file = st.file_uploader("PDF 일일결산서를 업로드하세요.", type="pdf")

if uploaded_file is not None:
    try:
        pdf_text = extract_text_from_pdf(uploaded_file)

        st.subheader("📄 PDF 내용 미리보기 (일부)")
        st.expander("전체 텍스트 보기", expanded=False).code(pdf_text)
        st.write(f"PDF에서 {len(pdf_text)}자 추출되었습니다.")

        if st.button("정보 추출 시작"):
            extracted_data = extract_patient_info(pdf_text)

            if extracted_data:
                df_extracted = pd.DataFrame(extracted_data)
                st.session_state.extracted_df = df_extracted

                st.subheader("✅ 추출된 환자 정보")
                st.dataframe(df_extracted, use_container_width=True)
                st.success(f"{len(extracted_data)} 건의 정보를 추출했습니다.")
            else:
                st.info("PDF에서 차트번호와 환자명 정보를 찾을 수 없습니다. 정규 표현식을 확인하거나 PDF 형식을 검토해주세요.")
                st.session_state.extracted_df = pd.DataFrame(columns=["차트번호", "환자명"])

    except fitz.FileDataError as e:
        st.error(e)
    except Exception as e:
        st.error(f"오류 발생: {e}")
else:
    # 파일이 업로드되지 않았을 때 세션 상태 초기화 (옵션)
    if 'extracted_df' in st.session_state:
        del st.session_state.extracted_df


# --- 2. 추출된 데이터 Firestore에 저장 ---
st.header("2. 추출된 데이터를 Firestore에 저장")
if db and 'extracted_df' in st.session_state and not st.session_state.extracted_df.empty:
    if st.button("✅ 추출된 데이터 Firestore에 저장", key="save_to_firestore_btn"): # key 추가
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
                        existing_docs = db.collection(collection_name).where("chart_number", "==", data_to_save["chart_number"]).where("patient_name", "==", data_to_save["patient_name"]).get()
                        if not existing_docs: # 문서가 없으면 추가
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
    if st.button("📊 Firestore 데이터 불러오기", key="load_from_firestore_btn"): # key 추가
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
                # 추출된 데이터가 없는 경우를 대비하여 컬럼 존재 여부 확인 후 재정렬
                cols_to_display = ["chart_number", "patient_name", "extraction_date", "Document ID"]
                existing_cols = [col for col in cols_to_display if col in df_firestore.columns]
                df_firestore = df_firestore[existing_cols]

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