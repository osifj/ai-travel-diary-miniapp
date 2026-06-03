"""
DeepSeek 文本生成客户端。

用途 (MiMo 兜底):
  1. MiMo 图片识别失败时的保守描述
  2. MiMo 日记生成失败时的日记生成
  3. 用户对话 + 日记整合
"""

import json, logging, os, re
from pathlib import Path
from typing import Optional
import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_MAX_COMPLETION_TOKENS = int(os.getenv("DEEPSEEK_MAX_COMPLETION_TOKENS", "4096"))
DEEPSEEK_TEMPERATURE = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.8"))
DEEPSEEK_TIMEOUT_SECONDS = float(os.getenv("DEEPSEEK_TIMEOUT_SECONDS", "90"))
DEEPSEEK_THINKING_TYPE = os.getenv("DEEPSEEK_THINKING_TYPE", "disabled")


def is_configured() -> bool:
    return bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY != "your_deepseek_api_key_here")


def _extract_json(text: str) -> Optional[dict]:
    if not text: return None
    text = text.strip()
    try: return json.loads(text)
    except json.JSONDecodeError: pass
    m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if m:
        try: return json.loads(m.group(1))
        except json.JSONDecodeError: pass
    s = text.find("{"); e = text.rfind("}")
    if s != -1 and e != -1 and e > s:
        try: return json.loads(text[s:e+1])
        except json.JSONDecodeError: pass
    return None


def _chat_json(messages: list[dict], temperature: Optional[float] = None) -> dict:
    if not is_configured(): raise ValueError("DEEPSEEK_API_KEY 未配置")
    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL, "messages": messages,
        "temperature": DEEPSEEK_TEMPERATURE if temperature is None else temperature,
        "max_completion_tokens": DEEPSEEK_MAX_COMPLETION_TOKENS,
        "response_format": {"type": "json_object"}, "stream": False,
        "thinking": {"type": DEEPSEEK_THINKING_TYPE},
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS) as client:
        resp = client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        data = resp.json()
    choices = data.get("choices", [])
    if not choices: raise RuntimeError("DeepSeek returned empty choices")
    content = choices[0].get("message", {}).get("content", "")
    parsed = _extract_json(content)
    if not parsed: raise RuntimeError(f"DeepSeek JSON parse failed: {content[:200]}")
    return parsed


# ---- 照片兜底分析 ----
def generate_photo_fallback(photo_context: dict) -> dict:
    prompt = f"""你无法看到图片，只能根据已知元数据写保守兜底描述。
已知: {json.dumps(photo_context, ensure_ascii=False)}
输出 JSON: {{"scene_type":"unknown","activity":"unknown","food":[],"objects":[],"landmark_hint":"unknown","fun_fact":"","confidence":"low","diary_sentence":"..."}}"""
    return _chat_json([
        {"role":"system","content":"你是谨慎的旅行日志助手。"},
        {"role":"user","content":prompt}
    ], temperature=0.2)


# ---- 日记生成 (MiMo 失败时兜底) ----
def generate_rich_diary(context: dict) -> dict:
    prompt = f"""请根据以下旅行照片分析数据，写一篇自然、有知识性的中文游记。

数据:
{json.dumps(context, ensure_ascii=False, indent=2)}

输出 JSON:
{{
  "title": "简洁标题",
  "date": "YYYY-MM-DD 或 unknown",
  "city": "城市名",
  "place_intro": "1-2句地点介绍",
  "weather_summary": "天气简介",
  "content": "正文。按时间顺序叙事，每张照片的 food/fun_fact/people_description 自然融入。可以有感官描写和人物互动。300-800字。",
  "keywords": ["5-8个关键词"],
  "photo_summaries": [{{"taken_time":"...","city":"...","place_name":"...","scene_type":"...","activity":"...","diary_sentence":"..."}}]
}}

原则: 具体>抽象，观察>感受，可以描述人物，不编造。"""

    return _chat_json([
        {"role":"system","content":"你是中文旅行日记写作者。重事实、会叙事、善用科普。可以描述人物和互动。"},
        {"role":"user","content":prompt},
    ], temperature=0.55)


# ---- 用户补充 + 整合 ----
def refine_diary_with_user_notes(original_diary: dict, user_notes: str) -> dict:
    prompt = f"""将用户补充的信息整合进原有旅行日记。

原日记: {json.dumps(original_diary, ensure_ascii=False, indent=2)}
用户补充: {user_notes}

输出 JSON: {{"title":"标题","content":"整合后正文","keywords":["关键词"],"place_intro":"地点介绍"}}

规则: 用户说辞优先；用户提到的食物/地点加入科普；可以描述人物互动；不编造。"""

    return _chat_json([
        {"role":"system","content":"你是旅行日记写作者。用户说辞优先，善加科普。可以写人物。"},
        {"role":"user","content":prompt},
    ], temperature=0.6)


def restyle_diary(diary: dict, style: str) -> dict:
    guides = {
        "轻松": "用轻松幽默的口吻重写，加入俏皮比喻和日常感。",
        "正式": "用正式优雅的文学语言重写，像旅行杂志文章。",
        "简短": "用最精炼语言重写，100字以内。",
        "科普": "以科普为主线重写，大幅扩展知识。",
    }
    guide = guides.get(style, guides["轻松"])
    prompt = f"""按以下风格重写旅行日记。
原日记: {json.dumps(diary, ensure_ascii=False, indent=2)}
风格: {guide}
输出 JSON: {{"title":"标题","content":"正文","keywords":["关键词"]}}"""

    return _chat_json([
        {"role":"system","content":f"中文旅行日记写作者。风格：{style}。"},
        {"role":"user","content":prompt},
    ], temperature=0.7)


def chat_about_diary(messages: list[dict], diary_context: dict) -> str:
    ctx = json.dumps(diary_context, ensure_ascii=False, indent=2)
    prompt = f"""帮助用户完善这篇旅行日记。你可以:
1. 确认修改意见
2. 追问细节
3. 给出建议
4. 补充科普
5. 当用户满意或说"可以了/整合/就这样"，回复中必须包含「✅ 我已准备好整合日记」

当前日记: {ctx}
规则: 用户说辞为准；可以讨论人物；不编造；用中文像朋友聊天。"""

    msgs = [{"role":"system","content":prompt}, *messages[-20:]]
    return _chat_text(msgs, temperature=0.7)


def integrate_chat_history(original_diary: dict, messages: list[dict]) -> dict:
    history_text = "\n".join([
        f"{'用户' if m['role']=='user' else 'AI'}: {m['content'][:200]}"
        for m in messages if m['role'] in ('user','assistant')
    ])
    prompt = f"""把对话中用户补充的内容整合进日记。
原日记: {json.dumps(original_diary, ensure_ascii=False, indent=2)}
对话: {history_text}
输出 JSON: {{"title":"标题","content":"正文","keywords":["关键词"],"place_intro":"地点介绍"}}
规则: 用户说辞优先覆盖；食物/地点加科普；可写人物；不编造。"""

    return _chat_json([
        {"role":"system","content":"你是旅行日记整合者。用户说辞优先，善加科普。"},
        {"role":"user","content":prompt},
    ], temperature=0.5)


def _chat_text(messages: list[dict], temperature: float = 0.7) -> str:
    full = ""
    for chunk in _chat_text_stream(messages, temperature):
        full += chunk
    return full


def _chat_text_stream(messages: list[dict], temperature: float = 0.7):
    if not is_configured(): raise ValueError("DEEPSEEK_API_KEY 未配置")
    url = f"{DEEPSEEK_BASE_URL.rstrip('/')}/chat/completions"
    payload = {
        "model": DEEPSEEK_MODEL, "messages": messages,
        "temperature": temperature,
        "max_completion_tokens": DEEPSEEK_MAX_COMPLETION_TOKENS,
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=DEEPSEEK_TIMEOUT_SECONDS) as client:
        with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str == "[DONE]": return
                    try:
                        data = json.loads(data_str)
                        delta = data.get("choices",[{}])[0].get("delta",{})
                        c = delta.get("content","")
                        if c: yield c
                    except json.JSONDecodeError: pass
