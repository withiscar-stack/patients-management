import google.generativeai as genai
import sys
import os

# 1. API 키 확인
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    print("❌ 에러: GEMINI_API_KEY 환경변수가 설정되지 않았습니다.")
    sys.exit(1)

genai.configure(api_key=api_key)

# 2. 내 계정에서 사용 가능한 '코딩 비서' 자동 색출하기
target_model_name = ""
print("🔍 사용 가능한 AI 비서를 찾고 있습니다...")

for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        name = m.name.replace("models/", "")
        # 음성(tts), 로봇(robotics), 비전(clip) 등 특수 목적 모델 제외
        if "tts" not in name and "robotics" not in name and "clip" not in name and "computer-use" not in name:
            target_model_name = name
            # 가급적 똑똑한 pro 나 빠릿한 flash 모델을 찾으면 즉시 채택
            if "pro" in name or "flash" in name:
                break

if not target_model_name:
    print("❌ 코딩이 가능한 텍스트 모델을 찾지 못했습니다.")
    sys.exit(1)

print(f"🤖 연결 성공! [ {target_model_name} ] 비서를 호출하여 코딩을 시작합니다.")

# 자동으로 찾은 비서에게 업무 지시
model = genai.GenerativeModel(target_model_name)

def vibe_coding():
    prompt = " ".join(sys.argv[1:])
    if not prompt:
        print("명령을 입력해주세요. (예: python vibe.py '안녕')")
        return

    current_code = ""
    if os.path.exists("app.py"):
        with open("app.py", "r", encoding="utf-8") as f:
            current_code = f.read()

    full_prompt = f"""
    당신은 한의원 전용 소프트웨어를 개발하는 파이썬/스트림릿(Streamlit) 전문가입니다.
    현재 app.py 코드:
    {current_code}

    사용자 요청:
    {prompt}

    위 요청에 따라 app.py 코드를 작성/수정해주세요. 
    출력은 반드시 ```python 으로 시작해서 ``` 로 끝나는 전체 코드 형태여야 합니다.
    """

    print("🚀 코드를 작성 중입니다. 잠시만 기다려주세요...")
    try:
        response = model.generate_content(full_prompt)
        new_code = response.text.replace("```python", "").replace("```", "").strip()
        
        with open("app.py", "w", encoding="utf-8") as f:
            f.write(new_code)
        
        print("✅ app.py가 성공적으로 업데이트되었습니다!")
    except Exception as e:
        print(f"❌ 코드 생성 중 에러가 발생했습니다: {e}")

if __name__ == "__main__":
    vibe_coding()