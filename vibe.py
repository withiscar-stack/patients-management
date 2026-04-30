import google.generativeai as genai
import sys
import os

# API 키 설정
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("❌ 에러: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

def vibe_coding():
    prompt = " ".join(sys.argv[1:])
    if not prompt:
        print("명령을 입력해주세요. (예: python vibe.py '로딩 화면 예쁘게 만들어줘')")
        return

    # 현재 app.py의 내용을 읽어옴 (없으면 빈 문자열)
    current_code = ""
    if os.path.exists("app.py"):
        with open("app.py", "r", encoding="utf-8") as f:
            current_code = f.read()

    full_prompt = f"""
    당신은 숙련된 한의원용 소프트웨어 개발자입니다.
    현재 app.py 코드:
    {current_code}

    사용자 요청:
    {prompt}

    위 요청에 따라 app.py 코드를 수정해주세요. 
    반드시 '전체 코드'를 출력해야 하며, ```python 으로 시작해서 ``` 로 끝나는 마크다운 형식을 지켜주세요.
    """

    print("🚀 Gemini가 코드를 생성 중입니다...")
    response = model.generate_content(full_prompt)
    
    # 생성된 코드에서 마크다운 제거 후 저장
    new_code = response.text.replace("```python", "").replace("```", "").strip()
    
    with open("app.py", "w", encoding="utf-8") as f:
        f.write(new_code)
    
    print("✅ app.py가 성공적으로 업데이트되었습니다! 이제 다시 배포하거나 실행해보세요.")

if __name__ == "__main__":
    vibe_coding()