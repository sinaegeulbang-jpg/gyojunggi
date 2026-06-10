import streamlit as st
import anthropic
import json
import os

# ── 환경변수 (Streamlit Cloud secrets에서 설정) ───────────────
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ACCESS_CODE = os.environ.get("ACCESS_CODE", "")

# ── 프롬프트 ──────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 한국어 글쓰기 교정 전문가입니다. 문학적 감수성과 언어적 정확성을 갖추고 있습니다.

글을 읽고 아래 JSON 형식으로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.

{
  "issues": [
    {
      "type": "오탈자",
      "original": "원문에서 문제가 되는 구절 (짧게, 정확하게)",
      "problem": "무엇이 왜 문제인지 한 줄 설명",
      "suggestion": "제안 설명"
    }
  ],
  "overall_feedback": "글 전체에 대한 종합 피드백 (3~5문장)"
}

type은 반드시 다음 다섯 가지 중 하나:
- "오탈자": 맞춤법 오류, 띄어쓰기, 타이핑 실수
- "비문": 주어-서술어 호응 문제, 문장 구조 오류
- "단어교체": 더 정확하거나 잘 어울리는 단어가 있는 경우
- "표현오류": 어색한 표현, 논리 흐름 오류, 어휘 호응 오류
- "문체": 아래 문체 기준에 해당하는 경우

[문체 교정 기준]
1. 중복 표현 제거
   - 예) "무엇이든지 다" → "무엇이든지" / "질문을 묻다" → "질문하다" / "크기가 큰" → "큰"

2. 불필요한 피동 표현
   - 주의 표현: 느껴졌다 / 보였다 / 생각되었다 / 전해졌다 / 들려왔다
   - 예) "그의 말이 따뜻하게 느껴졌다" → "그의 말은 따뜻했다"

3. 이중 피동 제거
   - 예) "읽혀지는" → "읽히는"

4. '~같았다' 남용
   - 예) "특별한 것 같았다" → "특별했다" / "슬퍼 보이는 것 같았다" → "말이 없었다"

5. '나는 / 내가 생각하기에 / 내가 느끼기에 / 내 의견으로는' 제거
   - 예) "내가 느끼기에는 시험 준비가 덜 되어있다" → "시험 준비가 덜 되어있다"

규칙:
1. 글 전체를 절대 다시 쓰거나 교체하지 마세요.
2. 각 문제를 독립된 항목으로 하나씩 나열하세요.
3. original에는 원문의 해당 구절을 최대한 짧고 정확하게 인용하세요.
4. 문제 없는 부분은 언급하지 마세요.
5. JSON 외 다른 텍스트는 출력하지 마세요."""

TYPE_STYLE = {
    "오탈자":   {"border": "#e03131", "bg": "#fff0f0", "badge": "#e03131"},
    "비문":     {"border": "#e8590c", "bg": "#fff4e6", "badge": "#e8590c"},
    "단어교체":  {"border": "#1971c2", "bg": "#e7f5ff", "badge": "#1971c2"},
    "표현오류":  {"border": "#7048e8", "bg": "#f3f0ff", "badge": "#7048e8"},
    "문체":     {"border": "#2b8a3e", "bg": "#ebfbee", "badge": "#2b8a3e"},
}
CIRCLES = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"

def circle(n):
    return CIRCLES[n - 1] if n <= len(CIRCLES) else f"({n})"

def highlight_text(text, issues):
    replacements = []
    for i, issue in enumerate(issues, 1):
        phrase = issue.get("original", "").strip().strip("\"'\u201c\u201d\u2018\u2019")
        if not phrase:
            continue
        start = 0
        while True:
            idx = text.find(phrase, start)
            if idx == -1:
                break
            end = idx + len(phrase)
            if not any(s <= idx < e or s < end <= e for s, e, _, _, _ in replacements):
                replacements.append((idx, end, i, issue.get("type", "기타"), issue))
                break
            start = idx + 1

    replacements.sort(key=lambda x: x[0], reverse=True)
    result = text
    for s, e, num, type_, issue in replacements:
        st_ = TYPE_STYLE.get(type_, {"border": "#aaa", "bg": "#f0f0f0"})
        c = circle(num)
        problem = issue.get("problem", "").replace('"', "&quot;")
        suggestion = issue.get("suggestion", "").replace('"', "&quot;")
        result = (
            result[:s]
            + f'<span class="hl-wrap" tabindex="0">'
            + f'<mark style="background:{st_["bg"]}; border-bottom:2px solid {st_["border"]}; border-radius:3px; padding:1px 3px; cursor:pointer;">'
            + result[s:e]
            + f'<sup style="color:{st_["border"]}; font-weight:bold; font-size:0.8em; margin-left:1px;">{c}</sup>'
            + '</mark>'
            + f'<div class="hl-tooltip" style="border-color:{st_["border"]};">'
            + f'<span style="background:{st_["badge"]}; color:white; padding:2px 9px; border-radius:10px; font-size:11px; font-weight:bold;">{c} {type_}</span>'
            + f'<p style="margin:8px 0 4px; color:#333; font-size:13px;">{problem}</p>'
            + f'<p style="margin:0; color:#555; font-size:12px;">→ {suggestion}</p>'
            + '</div>'
            + '</span>'
            + result[e:]
        )
    return result.replace("\n", "<br>")

def run_correction(text):
    client = anthropic.Anthropic(api_key=API_KEY)
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"다음 글을 교정해주세요:\n\n{text}"}],
    )
    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)

st.set_page_config(page_title="시내글방 교정기", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.8rem; padding-bottom: 2rem; }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.1rem !important; }
    .no-select { -webkit-user-select:none; -moz-user-select:none; -ms-user-select:none; user-select:none; }
    .issue-card { padding:13px 16px; margin:8px 0; border-radius:8px; border-left:5px solid; line-height:1.65; }
    .badge { display:inline-block; color:white; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:bold; margin-bottom:8px; }
    .original-quote { font-style:italic; background:rgba(0,0,0,0.07); padding:2px 7px; border-radius:4px; }
    .overall-box { background:#f8f9fa; border:1px solid #dee2e6; padding:18px 22px; border-radius:8px; line-height:1.85; color:#222; white-space:pre-wrap; }
    .text-display { height:520px; overflow-y:auto; border:1px solid #e0e0e0; border-radius:8px; padding:18px 20px; background:white; line-height:2; font-size:0.95rem; color:#222; }
    .hl-wrap { position:relative; display:inline; outline:none; }
    .hl-tooltip { display:none; position:absolute; top:calc(100% + 6px); left:0; background:white; border:2px solid; border-radius:10px; padding:10px 13px; width:230px; z-index:999; box-shadow:0 4px 16px rgba(0,0,0,0.13); line-height:1.5; }
    .hl-wrap:focus-within .hl-tooltip { display:block; }
</style>
""", unsafe_allow_html=True)

if not API_KEY:
    st.error("서비스 준비 중입니다. 잠시 후 다시 시도해주세요.")
    st.stop()

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown("## 시내글방 교정기")
        st.markdown("<br>", unsafe_allow_html=True)
        code = st.text_input("수업 코드", type="password", placeholder="선생님께 받은 코드를 입력하세요", label_visibility="collapsed")
        if st.button("입장하기", type="primary", use_container_width=True):
            if code == ACCESS_CODE:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("코드가 맞지 않아요.")
    st.stop()

for k, v in {"result": None, "input_text": ""}.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown("# 시내글방 교정기")
st.caption("글을 붙여넣고 교정하기를 누르면 항목별로 하나씩 보여드려요.")

left, right = st.columns([1, 1], gap="large")

with left:
    if st.session_state.result is None:
        text_input = st.text_area("원고", height=520, placeholder="여기에 글을 붙여넣으세요...", label_visibility="visible")
        if st.button("교정하기  →", type="primary", use_container_width=True):
            if not text_input.strip():
                st.warning("글을 붙여넣어 주세요.")
            else:
                with st.spinner("교정 중입니다..."):
                    try:
                        result = run_correction(text_input)
                        st.session_state.result = result
                        st.session_state.input_text = text_input
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("응답 오류. 다시 시도해주세요.")
                    except Exception as e:
                        st.error(f"오류: {e}")
    else:
        st.markdown("**원고** (교정 항목 표시 — 클릭하면 설명)")
        issues = st.session_state.result.get("issues", [])
        highlighted = highlight_text(st.session_state.input_text, issues)
        st.markdown(f'<div class="text-display no-select">{highlighted}</div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← 다시 입력하기", use_container_width=True):
            st.session_state.result = None
            st.session_state.input_text = ""
            st.rerun()

with right:
    if st.session_state.result is not None:
        issues = st.session_state.result.get("issues", [])
        overall = st.session_state.result.get("overall_feedback", "")

        if not issues:
            st.success("교정할 내용이 없어요. 잘 쓴 글이에요!")
        else:
            st.markdown(f"**교정 결과** — 총 {len(issues)}건")
            for i, issue in enumerate(issues, 1):
                t = issue.get("type", "기타")
                s = TYPE_STYLE.get(t, {"border": "#aaa", "bg": "#f8f9fa", "badge": "#aaa"})
                st.markdown(f"""
                <div class="issue-card no-select" style="border-color:{s['border']}; background:{s['bg']};">
                    <span class="badge" style="background:{s['badge']};">{circle(i)} {t}</span><br>
                    <span class="original-quote">"{issue.get('original','')}"</span><br>
                    <span style="color:#333; display:block; margin-top:6px;">{issue.get('problem','')}</span>
                    <span style="color:#555; font-size:0.92em;">→ {issue.get('suggestion','')}</span>
                </div>
                """, unsafe_allow_html=True)

        if overall:
            st.markdown("---")
            st.markdown("**전체 피드백**")
            st.markdown(f'<div class="overall-box no-select">{overall}</div>', unsafe_allow_html=True)
