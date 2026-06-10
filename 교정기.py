import streamlit as st
import anthropic
import json
import os
from pathlib import Path

# ── API 키 ────────────────────────────────────────────────────
KEY_FILE = Path(__file__).parent / ".api_key"

def load_key():
    if KEY_FILE.exists():
        return KEY_FILE.read_text().strip()
    return os.environ.get("ANTHROPIC_API_KEY", "")

def save_key(key):
    KEY_FILE.write_text(key.strip())

# ── 프롬프트 ──────────────────────────────────────────────────
SYSTEM_PROMPT = """당신은 한국어 글쓰기 교정 전문가입니다. 문학적 감수성과 언어적 정확성을 갖추고 있습니다.

글을 읽고 아래 JSON 형식으로만 응답하세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.

{
  "issues": [
    {
      "type": "오탈자",
      "original": "원문에서 문제가 되는 구절 (짧게, 정확하게)",
      "problem": "무엇이 왜 문제인지 한 줄 설명",
      "suggestion": "제안 설명",
      "corrected": "original을 대체할 수정 텍스트만 (설명 없이, 짧게)"
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
   - 의미가 겹치는 표현은 하나만 남김
   - 예) "무엇이든지 다" → "무엇이든지" / "질문을 묻다" → "질문하다" / "크기가 큰" → "큰" / "색깔이 노란" → "노란"

2. 불필요한 피동 표현
   - 피동은 문장을 흐리게 만듦. 능동으로 바꿀 수 있으면 바꿈
   - 주의 표현: 느껴졌다 / 보였다 / 생각되었다 / 전해졌다 / 들려왔다
   - 예) "그의 말이 따뜻하게 느껴졌다" → "그의 말은 따뜻했다"
   - 예) "그는 조금 외로워 보였다" → "그는 외로웠다"

3. 이중 피동 제거
   - -혀지다 / -려지다 / -어지다 등 이중 피동은 단순 피동으로
   - 예) "읽혀지는" → "읽히는"

4. '~같았다' 남용
   - 확신 없는 추측형이 반복되면 글의 힘이 약해짐
   - 단정형으로 바꾸거나 구체적 묘사나 행동으로 표현
   - 예) "특별한 것 같았다" → "특별했다" / "슬퍼 보이는 것 같았다" → "말이 없었다"

5. '나는 / 내가 생각하기에 / 내가 느끼기에 / 내 의견으로는' 제거
   - 에세이는 어차피 필자의 글. 이런 표현은 불필요하게 시점을 드러냄
   - 예) "내가 느끼기에는 내일 시험 준비가 덜 되어있다" → "내일 시험 준비가 덜 되어있다"

규칙:
1. 글 전체를 절대 다시 쓰거나 교체하지 마세요.
2. 각 문제를 독립된 항목으로 하나씩 나열하세요.
3. original에는 원문의 해당 구절을 최대한 짧고 정확하게 인용하세요. 원문에 실제로 존재하는 텍스트여야 합니다.
4. corrected에는 original 자리에 그대로 들어갈 수정 텍스트만 쓰세요. 설명 없이.
5. 문제 없는 부분은 언급하지 마세요.
6. JSON 외 다른 텍스트는 출력하지 마세요."""

# ── 스타일 상수 ───────────────────────────────────────────────
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

# ── 유틸 함수 ─────────────────────────────────────────────────
def highlight_text(text, issues):
    """원문 전체에 번호+색깔 하이라이트 + 호버 툴팁."""
    replacements = []
    for i, issue in enumerate(issues, 1):
        phrase = issue.get("original", "").strip().strip("\"'""''")
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
            + f'<mark style="background:{st_["bg"]}; border-bottom:2px solid {st_["border"]}; '
              f'border-radius:3px; padding:1px 3px; cursor:pointer;">'
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

def get_context(text, phrase, window=120):
    """작가용: phrase 주변 문맥(앞뒤 문장) 반환. (context, p_start, p_end)"""
    idx = text.find(phrase)
    if idx == -1:
        return phrase, 0, len(phrase)
    end_idx = idx + len(phrase)

    # 앞 경계: 최대 window 자 이내의 가장 가까운 문장 끝
    start = max(0, idx - window)
    for sep in ["\n\n", "\n", ". ", "! ", "? "]:
        pos = text.rfind(sep, start, idx)
        if pos != -1:
            start = pos + len(sep)
            break

    # 뒤 경계: 최대 window 자 이내의 다음 문장 끝
    end = min(len(text), end_idx + window)
    for sep in ["\n\n", ".\n", "!\n", "?\n", ". ", "! ", "? "]:
        pos = text.find(sep, end_idx, end)
        if pos != -1:
            end = pos + len(sep)
            break

    context = text[start:end].strip()
    p = context.find(phrase)
    if p == -1:
        return context, 0, 0
    return context, p, p + len(phrase)

def apply_correction(text, original, corrected):
    """원문에서 original 첫 번째 등장을 corrected로 교체."""
    idx = text.find(original)
    if idx == -1:
        return text
    return text[:idx] + corrected + text[idx + len(original):]

def make_combined_doc(text, issues, overall):
    """수강생용 다운로드: 원문(번호 마커) + 교정 항목 + 전체 피드백."""
    replacements = []
    for i, issue in enumerate(issues, 1):
        phrase = issue.get("original", "").strip().strip("\"'""''")
        if not phrase:
            continue
        idx = text.find(phrase)
        if idx != -1:
            end = idx + len(phrase)
            if not any(s <= idx < e or s < end <= e for s, e, _ in replacements):
                replacements.append((idx, end, i))

    replacements.sort(key=lambda x: x[0], reverse=True)
    marked = text
    for s, e, num in replacements:
        marked = marked[:s] + f"[{circle(num)}{marked[s:e]}]" + marked[e:]

    lines = [
        "[교정 원고]",
        "※ 괄호+번호로 표시된 부분이 교정 항목입니다.",
        "", marked, "",
        "─" * 38,
        f"[교정 항목] (총 {len(issues)}건)", "",
    ]
    for i, iss in enumerate(issues, 1):
        lines += [
            f"{circle(i)} [{iss.get('type','')}]",
            f"   원문: \"{iss.get('original','')}\"",
            f"   문제: {iss.get('problem','')}",
            f"   제안: {iss.get('suggestion','')}",
            "",
        ]
    if overall:
        lines += ["─" * 38, "[전체 피드백]", "", overall]
    return "\n".join(lines)

def run_correction(text, api_key):
    client = anthropic.Anthropic(api_key=api_key)
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

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(page_title="시내글방 교정기", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
<style>
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.8rem; padding-bottom: 2rem; }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.1rem !important; }
    .badge {
        display: inline-block; color: white; padding: 2px 10px;
        border-radius: 12px; font-size: 12px; font-weight: bold; margin-bottom: 8px;
    }
    .original-quote {
        font-style: italic; background: rgba(0,0,0,0.07);
        padding: 2px 7px; border-radius: 4px;
    }
    /* 수강생용 카드 */
    .issue-card {
        padding: 13px 16px; margin: 8px 0; border-radius: 8px;
        border-left: 5px solid; line-height: 1.65;
    }
    .overall-box {
        background: #f8f9fa; border: 1px solid #dee2e6; padding: 18px 22px;
        border-radius: 8px; line-height: 1.85; color: #222; white-space: pre-wrap;
    }
    /* 공통 텍스트 표시박스 */
    .text-display {
        height: 520px; overflow-y: auto; border: 1px solid #e0e0e0; border-radius: 8px;
        padding: 18px 20px; background: white; line-height: 2; font-size: 0.95rem; color: #222;
    }
    .hl-wrap { position: relative; display: inline; outline: none; }
    .hl-tooltip {
        display: none; position: absolute; top: calc(100% + 6px); left: 0;
        background: white; border: 2px solid; border-radius: 10px;
        padding: 10px 13px; width: 230px; z-index: 999;
        box-shadow: 0 4px 16px rgba(0,0,0,0.13); line-height: 1.5;
    }
    .hl-wrap:focus-within .hl-tooltip { display: block; }
    /* 작가용 맥락 박스 */
    .context-box {
        background: #fafafa; border: 1px solid #e0e0e0; border-radius: 10px;
        padding: 18px 20px; line-height: 2; font-size: 0.97rem; color: #333;
        min-height: 100px; margin: 10px 0;
    }
    /* 작가용 이슈 설명 카드 */
    .review-card {
        background: white; border: 1px solid #dee2e6; border-radius: 10px;
        padding: 16px 18px; margin: 10px 0; line-height: 1.7;
    }
    /* 최종 원고 텍스트박스 */
    .final-text {
        border: 2px solid #40c057; border-radius: 8px; padding: 20px;
        background: #f4fce3; line-height: 2; font-size: 0.95rem;
        color: #222; white-space: pre-wrap; cursor: text; min-height: 200px;
    }
    .setup-center {
        max-width: 460px; margin: 5rem auto; padding: 2rem;
        border: 1px solid #dee2e6; border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

# ── API 키 설정 화면 ──────────────────────────────────────────
api_key = load_key()
if not api_key:
    col = st.columns([1, 2, 1])[1]
    with col:
        st.markdown('<div class="setup-center">', unsafe_allow_html=True)
        st.markdown("## 시내글방 교정기")
        st.caption("처음 한 번만 API 키를 입력하면 다음부터는 바로 시작해요.")
        st.markdown("---")
        st.markdown("**Anthropic API 키**")
        st.caption("console.anthropic.com → API Keys에서 발급")
        key_input = st.text_input("", type="password", placeholder="sk-ant-...", label_visibility="collapsed")
        if st.button("저장하고 시작하기", type="primary", use_container_width=True):
            if key_input.strip().startswith("sk-ant-"):
                save_key(key_input)
                st.rerun()
            else:
                st.error("올바른 API 키 형식이 아니에요. (sk-ant- 로 시작)")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ── 세션 상태 초기화 ──────────────────────────────────────────
for k, v in {
    "result": None, "input_text": "", "review_index": 0,
    "decisions": {}, "working_text": "",
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── 헤더 ─────────────────────────────────────────────────────
h1, h2 = st.columns([6, 1])
with h1:
    st.markdown("# 시내글방 교정기")
    st.caption("글을 붙여넣고 교정하기를 누르면 항목별로 하나씩 보여드려요.")
with h2:
    if st.button("키 재설정", help="API 키를 다시 입력합니다"):
        KEY_FILE.unlink(missing_ok=True)
        st.session_state.result = None
        st.rerun()

# ── 본문 레이아웃 ─────────────────────────────────────────────
left, right = st.columns([1, 1], gap="large")

# ── 왼쪽 패널 ─────────────────────────────────────────────────
with left:
    if st.session_state.result is None:
        # 입력 모드
        text_input = st.text_area(
            "원고", height=520,
            placeholder="여기에 글을 붙여넣으세요...",
            label_visibility="visible",
        )
        if st.button("교정하기  →", type="primary", use_container_width=True):
            if not text_input.strip():
                st.warning("글을 붙여넣어 주세요.")
            else:
                with st.spinner("교정 중입니다..."):
                    try:
                        result = run_correction(text_input, api_key)
                        st.session_state.result = result
                        st.session_state.input_text = text_input
                        st.session_state.review_index = 0
                        st.session_state.decisions = {}
                        st.session_state.working_text = text_input
                        st.rerun()
                    except json.JSONDecodeError:
                        st.error("응답 오류. 다시 시도해주세요.")
                    except anthropic.AuthenticationError:
                        st.error("API 키가 올바르지 않아요.")
                    except Exception as e:
                        st.error(f"오류: {e}")
    else:
        # 결과 모드: 수강생용은 원본 하이라이트, 작가용은 수정 중인 텍스트
        issues = st.session_state.result.get("issues", [])
        st.markdown("**원고**")
        highlighted = highlight_text(st.session_state.input_text, issues)
        st.markdown(f'<div class="text-display">{highlighted}</div>', unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← 다시 입력하기", use_container_width=True):
            for k in ("result", "input_text", "working_text"):
                st.session_state[k] = "" if k != "result" else None
            st.session_state.review_index = 0
            st.session_state.decisions = {}
            st.rerun()

# ── 오른쪽 패널 ───────────────────────────────────────────────
with right:
    if st.session_state.result is None:
        st.markdown("&nbsp;")  # placeholder
    else:
        issues = st.session_state.result.get("issues", [])
        overall = st.session_state.result.get("overall_feedback", "")

        tab_student, tab_author = st.tabs(["📄  수강생용", "✍️  작가용"])

        # ════════════════════════════════════════════════════
        # 수강생용 탭
        # ════════════════════════════════════════════════════
        with tab_student:
            if not issues:
                st.success("교정할 내용이 없어요. 잘 쓴 글이에요!")
            else:
                st.markdown(f"**교정 결과** — 총 {len(issues)}건")
                for i, issue in enumerate(issues, 1):
                    t = issue.get("type", "기타")
                    s = TYPE_STYLE.get(t, {"border": "#aaa", "bg": "#f8f9fa", "badge": "#aaa"})
                    st.markdown(f"""
                    <div class="issue-card" style="border-color:{s['border']}; background:{s['bg']};">
                        <span class="badge" style="background:{s['badge']};">{circle(i)} {t}</span><br>
                        <span class="original-quote">"{issue.get('original','')}"</span><br>
                        <span style="color:#333; display:block; margin-top:6px;">{issue.get('problem','')}</span>
                        <span style="color:#555; font-size:0.92em;">→ {issue.get('suggestion','')}</span>
                    </div>
                    """, unsafe_allow_html=True)

            if overall:
                st.markdown("---")
                st.markdown("**전체 피드백**")
                st.markdown(f'<div class="overall-box">{overall}</div>', unsafe_allow_html=True)

            if issues or overall:
                st.markdown("---")
                st.download_button(
                    "저장하기  📄",
                    data=make_combined_doc(st.session_state.input_text, issues, overall),
                    file_name="교정원고.txt",
                    mime="text/plain",
                    use_container_width=True,
                    help="원문(번호 표시) + 교정 항목 + 전체 피드백 한 파일",
                )

        # ════════════════════════════════════════════════════
        # 작가용 탭
        # ════════════════════════════════════════════════════
        with tab_author:
            if not issues:
                st.success("교정할 내용이 없어요!")
            else:
                decisions = st.session_state.decisions
                all_done = len(decisions) == len(issues)

                # ── 검토 완료 화면 ──────────────────────────
                if all_done:
                    accepted = sum(1 for v in decisions.values() if v == "accept")
                    rejected = len(issues) - accepted
                    st.success(f"검토 완료 — {accepted}개 적용 / {rejected}개 건너뜀")
                    st.markdown("**수정된 원고** — 드래그해서 복사하세요")
                    st.text_area(
                        "수정된 원고",
                        value=st.session_state.working_text,
                        height=420,
                        label_visibility="collapsed",
                    )
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("처음부터 다시 검토하기", use_container_width=True):
                        st.session_state.review_index = 0
                        st.session_state.decisions = {}
                        st.session_state.working_text = st.session_state.input_text
                        st.rerun()

                # ── 검토 진행 화면 ──────────────────────────
                else:
                    # 현재 볼 이슈 인덱스 결정
                    idx = st.session_state.review_index
                    # 범위 초과 방지
                    idx = max(0, min(idx, len(issues) - 1))
                    issue = issues[idx]
                    already_decided = idx in decisions

                    t = issue.get("type", "기타")
                    s = TYPE_STYLE.get(t, {"border": "#aaa", "bg": "#f8f9fa", "badge": "#aaa"})
                    original = issue.get("original", "").strip().strip("\"'""''")
                    corrected = issue.get("corrected", issue.get("suggestion", ""))
                    problem = issue.get("problem", "")
                    suggestion = issue.get("suggestion", "")

                    # 진행 상황
                    done_count = len(decisions)
                    st.markdown(f"**{done_count + 1} / {len(issues)}**")
                    st.progress(done_count / len(issues) if len(issues) > 0 else 0)

                    # 맥락 박스
                    context, p_start, p_end = get_context(st.session_state.working_text, original)
                    if p_start < p_end:
                        before = context[:p_start].replace("\n", "<br>")
                        highlight = context[p_start:p_end]
                        after = context[p_end:].replace("\n", "<br>")
                        context_html = (
                            before
                            + f'<mark style="background:{s["bg"]}; border-bottom:3px solid {s["border"]}; '
                              f'border-radius:3px; padding:1px 4px; font-weight:bold;">{highlight}</mark>'
                            + after
                        )
                    else:
                        context_html = context.replace("\n", "<br>")

                    st.markdown(f'<div class="context-box">{context_html}</div>', unsafe_allow_html=True)

                    # 이슈 설명 카드
                    if already_decided:
                        dec_label = "✓ 적용됨" if decisions[idx] == "accept" else "✗ 건너뜀"
                        dec_color = "#2f9e44" if decisions[idx] == "accept" else "#868e96"
                        st.markdown(f"""
                        <div class="review-card" style="opacity:0.7;">
                            <span class="badge" style="background:{s['badge']};">{t}</span>
                            <span style="float:right; color:{dec_color}; font-weight:bold; font-size:0.85em;">{dec_label}</span><br>
                            <span class="original-quote">"{original}"</span><br>
                            <span style="color:#555; display:block; margin-top:6px;">{problem}</span>
                            <span style="color:#555; font-size:0.92em;">→ <strong>{corrected}</strong></span>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="review-card">
                            <span class="badge" style="background:{s['badge']};">{t}</span><br>
                            <span class="original-quote">"{original}"</span><br>
                            <span style="color:#333; display:block; margin-top:6px;">{problem}</span>
                            <span style="color:#555; font-size:0.92em;">→ <strong>{corrected}</strong></span>
                        </div>
                        """, unsafe_allow_html=True)

                    # 버튼 행
                    b_prev, b_skip, b_apply, b_next = st.columns([1, 1.5, 1.5, 1])

                    with b_prev:
                        if st.button("← 이전", use_container_width=True, disabled=(idx == 0)):
                            st.session_state.review_index = idx - 1
                            st.rerun()

                    with b_skip:
                        if st.button(
                            "건너뜀", use_container_width=True,
                            disabled=already_decided,
                        ):
                            st.session_state.decisions[idx] = "reject"
                            # 다음 미결정 항목으로
                            nxt = next((i for i in range(idx + 1, len(issues)) if i not in st.session_state.decisions), idx + 1)
                            st.session_state.review_index = nxt
                            st.rerun()

                    with b_apply:
                        if st.button(
                            "✓ 적용", type="primary", use_container_width=True,
                            disabled=already_decided,
                        ):
                            st.session_state.working_text = apply_correction(
                                st.session_state.working_text, original, corrected
                            )
                            st.session_state.decisions[idx] = "accept"
                            nxt = next((i for i in range(idx + 1, len(issues)) if i not in st.session_state.decisions), idx + 1)
                            st.session_state.review_index = nxt
                            st.rerun()

                    with b_next:
                        if st.button("다음 →", use_container_width=True, disabled=(idx >= len(issues) - 1)):
                            st.session_state.review_index = idx + 1
                            st.rerun()

                    # 검토 기록 (하단)
                    if decisions:
                        st.markdown("---")
                        parts = []
                        for j in sorted(decisions):
                            icon = "✓" if decisions[j] == "accept" else "✗"
                            parts.append(f"{icon} {circle(j+1)}")
                        st.caption("  ".join(parts))
