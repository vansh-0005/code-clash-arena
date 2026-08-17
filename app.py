"""
Code Clash Arena - main entrypoint.

PHASE STATUS:
[x] Phase 1 - static layout, theme, pills
[x] Phase 2 - shared match state (utils/db.py) - THIS FILE
[ ] Phase 3 - Gemini puzzle gen + judging (utils/gemini.py, prompts/templates.py)
[ ] Phase 4 - grading dispatch incl. Judge0 (utils/grading.py)
[ ] Phase 5 - Elo + leaderboard (utils/elo.py)
[ ] Phase 6 - deploy + docs
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh

from styles.theme import get_theme_css
from utils import db

st.set_page_config(page_title="Code Clash Arena", layout="wide")
st.markdown(get_theme_css(), unsafe_allow_html=True)

LANGS = ["PY", "C++", "JAVA", "JS"]
TYPES = {"coding": "Coding", "aptitude": "Aptitude", "debug": "Debug", "logic": "Logic"}
STARTING_RATING = 1000


# ---------------------------------------------------------------------------
# Local session identity (which player_name THIS browser tab is, per match)
# db.py keys players by name, not by a_player/b_player, so this tab needs to
# remember its own name across reruns/polls to know which submissions are
# "mine" once Phase 4 wires that in.
# ---------------------------------------------------------------------------

def _my_name(match_id: str) -> str | None:
    return st.session_state.get(f"me_{match_id}")


def _set_my_name(match_id: str, name: str) -> None:
    st.session_state[f"me_{match_id}"] = name


# ---------------------------------------------------------------------------
# Active match_id for THIS tab.
#
# KNOWN STREAMLIT BUG (github.com/streamlit/streamlit/issues/7961): calling
# st.rerun() immediately after setting st.query_params[...] has a race
# condition - the browser's URL bar doesn't reliably sync in time, so a
# later poll-triggered rerun can read back an EMPTY query_params and bounce
# the app back to the landing screen even though nothing actually errored.
#
# Fix: st.session_state is the source of truth for "which match is this tab
# in" (instant, no round-trip needed). st.query_params is still set/read
# ONLY for sharing the link / picking up a fresh tab that opens a shared
# URL - never trusted as the sole source once we're already inside a match.
# ---------------------------------------------------------------------------

def _get_active_match_id() -> str | None:
    if "active_match_id" in st.session_state:
        return st.session_state["active_match_id"]
    # Fresh tab / fresh load - fall back to the URL (deep link / shared link).
    from_url = st.query_params.get("match_id")
    if from_url:
        st.session_state["active_match_id"] = from_url
    return from_url


def _set_active_match_id(match_id: str) -> None:
    st.session_state["active_match_id"] = match_id
    st.query_params["match_id"] = match_id  # best-effort, for shareable URL


def _clear_active_match_id() -> None:
    st.session_state.pop("active_match_id", None)
    st.query_params.clear()


# ---------------------------------------------------------------------------
# Screen: landing - no match_id yet. Pick type/language, then create or join.
# ---------------------------------------------------------------------------

def render_landing() -> None:
    if "language" not in st.session_state:
        st.session_state.language = "PY"
    if "problem_type" not in st.session_state:
        st.session_state.problem_type = "coding"

    st.markdown("### Code Clash Arena")

    type_cols = st.columns(len(TYPES))
    for i, (key, label) in enumerate(TYPES.items()):
        with type_cols[i]:
            if st.button(label, key=f"type_{key}", use_container_width=True):
                st.session_state.problem_type = key

    if st.session_state.problem_type in ("coding", "debug"):
        lang_cols = st.columns(len(LANGS))
        for i, lang in enumerate(LANGS):
            with lang_cols[i]:
                if st.button(lang, key=f"lang_{lang}", use_container_width=True):
                    st.session_state.language = lang

    st.caption(
        f"Mode: {TYPES[st.session_state.problem_type]}"
        + (f" · Language: {st.session_state.language}"
           if st.session_state.problem_type in ("coding", "debug") else "")
    )

    st.divider()
    tab_create, tab_join = st.tabs(["CREATE MATCH", "JOIN MATCH"])

    with tab_create:
        with st.form("create_form"):
            name = st.text_input("Your name")
            go = st.form_submit_button("CREATE MATCH")
        if go:
            if not name.strip():
                st.error("Enter your name.")
            else:
                language = (
                    st.session_state.language
                    if st.session_state.problem_type in ("coding", "debug")
                    else None
                )
                match_id = db.create_match(st.session_state.problem_type, language)
                db.join_match(match_id, name.strip(), STARTING_RATING)
                _set_my_name(match_id, name.strip())
                _set_active_match_id(match_id)
                st.rerun()

    with tab_join:
        with st.form("join_form"):
            name = st.text_input("Your name", key="join_name")
            code = st.text_input("Match code", key="join_code")
            go = st.form_submit_button("JOIN MATCH")
        if go:
            if not name.strip() or not code.strip():
                st.error("Enter your name and the match code.")
            else:
                match_id = code.strip()
                state = db.get_match_state(match_id)
                if not state:
                    st.error(f"No match found with code {match_id}.")
                elif name.strip() in state.get("players", {}):
                    st.error("That name is already taken in this match.")
                elif len(state.get("players", {})) >= 2:
                    st.error("This match is already full.")
                else:
                    db.join_match(match_id, name.strip(), STARTING_RATING)
                    _set_my_name(match_id, name.strip())
                    _set_active_match_id(match_id)
                    st.rerun()


# ---------------------------------------------------------------------------
# Screen: inside a match (match_id resolved via _get_active_match_id())
# ---------------------------------------------------------------------------

def render_match(match_id: str) -> None:
    st_autorefresh(interval=3000, key=f"poll_{match_id}")

    state = db.get_match_state(match_id)
    if not state:
        st.error(f"Match {match_id} not found - it may not exist yet.")
        if st.button("BACK"):
            _clear_active_match_id()
            st.rerun()
        return

    players = state.get("players", {})
    me = _my_name(match_id)

    # This tab doesn't know its own identity yet (fresh load of a shared
    # URL) - route through a join form if there's still a free slot.
    if me is None:
        if len(players) < 2:
            st.markdown(f"#### Join match `{match_id}`")
            with st.form("late_join_form"):
                name = st.text_input("Your name")
                go = st.form_submit_button("JOIN")
            if go:
                if not name.strip():
                    st.error("Enter your name.")
                elif name.strip() in players:
                    st.error("That name is already taken in this match.")
                else:
                    db.join_match(match_id, name.strip(), STARTING_RATING)
                    _set_my_name(match_id, name.strip())
                    st.rerun()
            return
        else:
            st.error("This match is full and you're not one of the players.")
            if st.button("BACK"):
                _clear_active_match_id()
                st.rerun()
            return

    st.markdown(f'<span class="cc-judge-label">MATCH CODE</span> `{match_id}`', unsafe_allow_html=True)

    names = list(players.keys())
    if len(names) < 2:
        st.markdown("### Waiting for opponent...")
        st.write(f"**{names[0]}** (rating {players[names[0]]['rating']}) is in the arena.")
        st.caption("Share the match code above - the fight card appears the moment someone joins.")
        if st.button("LEAVE"):
            _clear_active_match_id()
            st.rerun()
        return

    # Two players present - render the real fight card (Phase 1 visual,
    # Phase 2 data). Test bars / code panes are left blank until Phase 3
    # (puzzle) and Phase 4 (submissions/grading) are wired in.
    a_name, b_name = names[0], names[1]
    a, b = players[a_name], players[b_name]

    st.markdown(
        f"""
        <div class="cc-card">
          <div class="cc-panel-a">
            <div class="cc-name">{a_name}</div>
            <div class="cc-rating" style="color:#9FE1CB;">RATING {a['rating']}</div>
          </div>
          <div class="cc-panel-b">
            <div class="cc-name">{b_name}</div>
            <div class="cc-rating" style="color:#F09595;">RATING {b['rating']}</div>
          </div>
          <div class="cc-vs">VS</div>
        </div>
        <div class="cc-judge">
          <div class="cc-judge-label">STATUS</div>
          <div style="font-size:13px; color:#D3D1C7; line-height:1.5;">
            Both players in. Mode: {TYPES.get(state.get('problem_type'), state.get('problem_type'))}
            {f" · {state.get('language')}" if state.get('language') else ""}.
            Puzzle generation is Phase 3 - not wired in yet.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("LEAVE MATCH"):
        _clear_active_match_id()
        st.rerun()


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

match_id = _get_active_match_id()
if match_id:
    render_match(match_id)
else:
    render_landing()