from google import genai
import sys
import os
import re

# 1. API 키 확인
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("❌ 에러: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

# 2. 새로운 SDK 클라이언트 설정
client = genai.Client(api_key=api_key)
# 원장님 계정에서 확인된 가장 최신 모델인 2.5-flash 사용
MODEL_ID = "gemini-2.5-flash"

def vibe_coding():
    prompt = " ".join(sys.argv[1:])
    if not prompt: return

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

    반드시 ```python ... ``` 안에 전체 코드를 작성해주세요.
    """

    print(f"🚀 최신형 {MODEL_ID} 비서가 코드를 정밀 가공 중입니다...")
    
    try:
        # 새로운 SDK의 생성 방식
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=full_prompt
        )
        
        # 마크다운 코드 블록 추출
        code_match = re.search(r"
```python\s*(.*?)\s*```", response.text, re.DOTALL)
        
        if code_match:
            new_code = code_match.group(1).strip()
            with open("app.py", "w", encoding="utf-8") as f:
                f.write(new_code)
            print("✅ 최신 SDK를 사용하여 app.py를 안전하게 업데이트했습니다!")
        else:
            print("❌ 코드를 찾지 못했습니다. AI 응답을 확인하세요.")
            
    except Exception as e:
        print(f"❌ 에러 발생: {e}")

if __name__ == "__main__":
    vibe_coding()