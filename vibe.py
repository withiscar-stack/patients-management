from google import genai
import sys
import os
import re

# 1. API 키 확인 (환경변수에서 가져오기)
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("❌ 에러: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

# 2. 최신 SDK 클라이언트 설정 (2026년 표준)
client = genai.Client(api_key=api_key)
MODEL_ID = "gemini-2.5-flash"

def vibe_coding():
    # 터미널 입력값 합치기
    prompt = " ".join(sys.argv[1:])
    if not prompt:
        print("💡 사용법: python vibe.py '수정하고 싶은 내용'")
        return

    # 기존 app.py 읽기
    current_code = ""
    if os.path.exists("app.py"):
        with open("app.py", "r", encoding="utf-8") as f:
            current_code = f.read()

    full_prompt = f"""
당신은 한의원 전용 소프트웨어 전문가입니다.
현재 app.py 코드:
{current_code}

사용자 요청:
{prompt}

반드시 ```python ... ``` 마크다운 형식 안에 전체 코드를 작성해주세요.
"""

    print(f"🚀 {MODEL_ID} 비서가 코딩을 시작합니다...")
    
    try:
        # AI 응답 생성
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=full_prompt
        )
        
        # --- 핵심: 마크다운 코드 블록만 정확히 추출 ---
        # 줄바꿈 오류 방지를 위해 텍스트 전체에서 추출
        code_pattern = r"```python\s*(.*?)\s*```"
        code_match = re.search(code_pattern, response.text, re.DOTALL)
        
        if code_match:
            new_code = code_match.group(1).strip()
            with open("app.py", "w", encoding="utf-8") as f:
                f.write(new_code)
            print("✅ app.py가 성공적으로 업데이트되었습니다!")
        else:
            print("⚠️ 코드를 찾지 못했습니다. AI가 코드 블록 형식을 지키지 않았을 수 있습니다.")
            # 만약 코드 블록이 없다면 응답 전체를 저장하는 안전장치
            if "import " in response.text:
                with open("app.py", "w", encoding="utf-8") as f:
                    f.write(response.text.strip())
                print("✅ 코드 블록은 없었지만, 감지된 코드를 app.py에 저장했습니다.")
            
    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    vibe_coding()