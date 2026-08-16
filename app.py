"""
Code Clash Arena - main entrypoint.

PHASE STATUS:
[x] Phase 1 - static layout, theme, pills (this file)
[ ] Phase 2 - shared match state (utils/db.py)
[ ] Phase 3 - Gemini puzzle gen + judging (utils/gemini.py, prompts/templates.py)
[ ] Phase 4 - grading dispatch incl. Judge0 (utils/grading.py)
[ ] Phase 5 - Elo + leaderboard (utils/elo.py)
[ ] Phase 6 - deploy + docs
"""

import streamlit as st
from styles.theme import get_theme_css

st.set_page_config(page_title="Code Clash Arena", layout="wide")
st.markdown(get_theme_css(), unsafe_allow_html=True)

# ---- session state defaults ----
if "language" not in st.session_state:
    st.session_state.language = "PY"
if "problem_type" not in st.session_state:
    st.session_state.problem_type = "coding"

LANGS = ["PY", "C++", "JAVA", "JS"]
TYPES = {"coding": "Coding", "aptitude": "Aptitude", "debug": "Debug", "logic": "Logic"}

st.markdown("### Code Clash Arena")

# ---- problem type pills (always shown) ----
type_cols = st.columns(len(TYPES))
for i, (key, label) in enumerate(TYPES.items()):
    with type_cols[i]:
        if st.button(label, key=f"type_{key}", use_container_width=True):
            st.session_state.problem_type = key

# ---- language pills (only relevant for coding / debug) ----
if st.session_state.problem_type in ("coding", "debug"):
    lang_cols = st.columns(len(LANGS))
    for i, lang in enumerate(LANGS):
        with lang_cols[i]:
            if st.button(lang, key=f"lang_{lang}", use_container_width=True):
                st.session_state.language = lang

st.caption(
    f"Mode: {TYPES[st.session_state.problem_type]}"
    + (f" · Language: {st.session_state.language}" if st.session_state.problem_type in ('coding', 'debug') else "")
)

# ---- static fight-card demo (Phase 1: layout only, no live match data yet) ----
# TODO Phase 2: replace hardcoded names/ratings/tests with utils.db.get_match_state(match_id)
st.markdown(
    """
    <div class="cc-card">
      <div class="cc-panel-a">
        <div class="cc-name">vansh_0005</div>
        <div class="cc-rating" style="color:#9FE1CB;">RATING 1454</div>
        <div class="cc-testbar">
          <div class="cc-seg" style="background:#5DCAA5;"></div>
          <div class="cc-seg" style="background:#5DCAA5;"></div>
          <div class="cc-seg" style="background:#5DCAA5;"></div>
          <div class="cc-seg" style="background:#04342C;"></div>
          <div class="cc-seg" style="background:#04342C;"></div>
        </div>
        <div class="cc-code" style="color:#C0DD97;">left, right = 0, 0<br>seen = set()</div>
      </div>
      <div class="cc-panel-b">
        <div class="cc-name">rival_ak</div>
        <div class="cc-rating" style="color:#F09595;">RATING 1502</div>
        <div class="cc-testbar cc-testbar-b">
          <div class="cc-seg" style="background:#E24B4A;"></div>
          <div class="cc-seg" style="background:#E24B4A;"></div>
          <div class="cc-seg" style="background:#E24B4A;"></div>
          <div class="cc-seg" style="background:#E24B4A;"></div>
          <div class="cc-seg" style="background:#E24B4A;"></div>
        </div>
        <div class="cc-code" style="color:#F7C1C1;">window = {}<br>lo = 0</div>
      </div>
      <div class="cc-vs">VS</div>
    </div>
    <div class="cc-judge">
      <div class="cc-judge-label">AI JUDGE</div>
      <div style="font-size:13px; color:#D3D1C7; line-height:1.5;">
        Static placeholder - wired to Gemini in Phase 3.
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
