import google.generativeai as genai
import sys
import os
import re  # 정규표현식 추가

# 1. API 키 확인 및 모델 설정 (아까 성공한 로직 유지)
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)

# 똑똑한 모델 자동 탐색
target_model_name = ""
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        name = m.name.replace("models/", "")
        if "tts" not in name and "robotics" not in name and "clip" not in name:
            target_model_name = name
            if "pro" in name or "flash" in name: break

model = genai.GenerativeModel(target_model_name)

def vibe_coding():
    prompt = " ".join(sys.argv[1:])
    if not prompt: return

    current_code = ""
    if os.path.exists("app.py"):
        with open("app.py", "r", encoding="utf-8") as f:
            current_code = f.read()

    full_prompt = f"현재 코드:\n{current_code}\n\n요청:\n{prompt}\n\n반드시 ```python ... ``` 안에 전체 코드를 작성해줘."

    print(f"🚀 {target_model_name} 비서가 코드를 정제 중입니다...")
    response = model.generate_content(full_prompt)
    
    # --- [핵심 수정] 마크다운 코드 블록만 정확히 추출 ---
    code_match = re.search(r"```python\s*(.*?)\s*```", response.text, re.DOTALL)
    
    if code_match:
        new_code = code_match.group(1).strip()
        with open("app.py", "w", encoding="utf-8") as f:
            f.write(new_code)
        print("✅ 인사말을 제외한 '순수 코드'만 app.py에 저장되었습니다!")
    else:
        print("❌ 코드를 찾지 못했습니다. AI의 응답을 확인해 주세요.")

if __name__ == "__main__":
    vibe_coding()