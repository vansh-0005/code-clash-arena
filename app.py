"""
Code Clash Arena - main entrypoint.

PHASE STATUS:
[x] Phase 1 - static layout, theme, pills
[x] Phase 2 - shared match state + persistent player profiles
[x] Phase 3 - Gemini puzzle gen + judging (race-guarded)
[x] Phase 4 - Judge0 grading, incl. pre-submit sample-test running
[x] Phase 5 - Elo + leaderboard
[ ] Phase 6 - deploy + docs

Match structure: best-of-N rounds (N chosen at creation). Each round =
fresh puzzle -> both submit -> hybrid grade (deterministic pass ratio +
Gemini qualitative score) -> round winner. After the last round, Elo
applies once based on total rounds won.

BUSY-FLAG / AUTOREFRESH FIX (important - read before touching the slow
paths below): every blocking call (Gemini puzzle gen, Gemini judging,
JDoodle grading on submit) now follows a strict TWO-PHASE pattern:

    Phase 1 (trigger run): set the relevant `st.session_state` busy flag,
    then immediately `st.rerun()`. Do NOT do the slow call in this same
    script pass.

    Phase 2 (next run): the busy flag is now True *before* this run's
    `st_autorefresh(...)` call happens, so the poll interval is already
    slowed to 8000ms for this run. NOW it's safe to actually do the slow
    call (Gemini / JDoodle), because the fast 3000ms timer from the
    previous run cannot fire in the middle of it.

Why this matters: st_autorefresh's JS timer fires on a wall-clock
schedule, independent of what the Python script is doing. If a slow call
starts in the SAME run that sets the busy flag, the flag isn't in effect
yet for that run's own autorefresh timer - a fast refresh scheduled
before the flag existed can still land mid-call and Streamlit cancels the
in-flight script run. That cancellation is not a normal Exception, so
`except Exception:` around the slow call does not catch it. Net effect:
JDoodle/Gemini calls fire (credits spent, quota used) but the result
write after them (db.record_test_results / db.record_round_verdict)
never happens - a submission or verdict silently goes missing and the
match wedges with no error shown. Splitting into two script passes closes
that gap: by the time the slow call actually starts, the CURRENT run's
autorefresh has already been scheduled at the slow interval, and the
previous (fast-interval) timer has already fired-and-been-consumed by the
rerun that got us into phase 2.
"""

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import random
import pandas as pd

from styles.theme import get_theme_css
from utils import db, gemini, grading, elo

st.set_page_config(page_title="Code Clash Arena", layout="wide")
st.markdown(get_theme_css(), unsafe_allow_html=True)

LANGS = ["PY", "C++", "JAVA", "JS"]
TYPES = {"coding": "Coding", "aptitude": "Aptitude", "debug": "Debug", "logic": "Logic"}
ROUND_OPTIONS = {f"{n} round{'s' if n > 1 else ''}": n for n in range(1, 6)}

# Phase 3 defaults: generate_puzzle() needs difficulty/topic that match
# state doesn't store (not in the brief's locked feature list either).
# One reasonable default per type rather than blocking on a topic-picker UI.
DEFAULT_DIFFICULTY = "medium"
DEFAULT_TOPIC = {
    "coding": "arrays and hashing",
    "aptitude": "quantitative reasoning",
    "debug": "off-by-one and logic errors",
    "logic": "estimation (Fermi problems)",
}

# Topic pools for variety across rounds in the same match - without this,
# round 2 asking Gemini for "quantitative reasoning, medium" again with no
# other signal changed is very likely to come back near-identical to round
# 1's question. A different topic each round + an explicit "don't repeat
# these" list (built from prior rounds' actual questions, see
# render_puzzle_section) both push toward real variety.
TOPIC_POOL = {
    "coding": ["arrays and hashing", "two pointers", "binary search", "stacks/queues", "graphs (BFS/DFS)", "dynamic programming"],
    "aptitude": ["quantitative reasoning", "percentages and ratios", "time-speed-distance", "probability", "number series", "work and time"],
    "debug": ["off-by-one and logic errors", "mutable default arguments", "incorrect loop bounds", "wrong comparison operator", "type coercion bugs"],
    "logic": ["estimation (Fermi problems)", "lateral thinking riddles", "probability puzzles", "classic logic grid puzzles"],
}

_QUESTION_FIELD_LOOKUP = {"coding": "statement", "debug": "buggy_code", "aptitude": "question", "logic": "question"}

# Hybrid scoring weights for coding/debug: deterministic Judge0 pass ratio
# blended with Gemini's qualitative code-quality score, so credit reflects
# actual line-by-line approach quality, not just "did the output match".


# ---------------------------------------------------------------------------
# Local session identity - which player_name and match this browser TAB is.
# See db.py schema note + the KNOWN STREAMLIT BUG note below for why this
# is session_state-backed rather than trusting st.query_params directly.
# ---------------------------------------------------------------------------

def _my_name(match_id: str) -> str | None:
    return st.session_state.get(f"me_{match_id}")


def _set_my_name(match_id: str, name: str) -> None:
    st.session_state[f"me_{match_id}"] = name


# KNOWN STREAMLIT BUG (github.com/streamlit/streamlit/issues/7961): calling
# st.rerun() immediately after setting st.query_params[...] has a race
# condition - the browser's URL doesn't reliably sync in time, so a later
# poll-triggered rerun can read back an EMPTY query_params and bounce the
# app back to landing even though nothing errored. Fix: session_state is
# the source of truth for "which match is this tab in" (instant, no
# round-trip needed); query_params is only set/read for link sharing.

def _get_active_match_id() -> str | None:
    if "active_match_id" in st.session_state:
        return st.session_state["active_match_id"]
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
# Screen: landing - no match yet. Pick type/language/rounds, create or join.
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
            is_active = st.session_state.problem_type == key
            if st.button(
                label, key=f"type_{key}", use_container_width=True,
                type="primary" if is_active else "secondary",
            ):
                st.session_state.problem_type = key

    if st.session_state.problem_type in ("coding", "debug"):
        lang_cols = st.columns(len(LANGS))
        for i, lang in enumerate(LANGS):
            with lang_cols[i]:
                is_active = st.session_state.language == lang
                if st.button(
                    lang, key=f"lang_{lang}", use_container_width=True,
                    type="primary" if is_active else "secondary",
                ):
                    st.session_state.language = lang

    round_label = st.select_slider("Match length", options=list(ROUND_OPTIONS.keys()), value="1 round")
    rounds_total = ROUND_OPTIONS[round_label]

    st.caption(
        f"Mode: {TYPES[st.session_state.problem_type]}"
        + (f" · Language: {st.session_state.language}"
           if st.session_state.problem_type in ("coding", "debug") else "")
        + f" · {round_label}"
    )

    st.divider()
    tab_create, tab_join, tab_leaderboard = st.tabs(["CREATE MATCH", "JOIN MATCH", "LEADERBOARD"])

    with tab_create:
        with st.form("create_form"):
            name = st.text_input("Your name")
            go = st.form_submit_button("CREATE MATCH", type="primary")
        if go:
            if not name.strip():
                st.error("Enter your name.")
            else:
                language = (
                    st.session_state.language
                    if st.session_state.problem_type in ("coding", "debug")
                    else None
                )
                profile = db.get_or_create_player(name.strip())
                match_id = db.create_match(st.session_state.problem_type, language, rounds_total)
                db.join_match(match_id, name.strip(), profile["rating"])
                _set_my_name(match_id, name.strip())
                _set_active_match_id(match_id)
                st.rerun()

    with tab_join:
        with st.form("join_form"):
            name = st.text_input("Your name", key="join_name")
            code = st.text_input("Match code", key="join_code")
            go = st.form_submit_button("JOIN MATCH", type="primary")
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
                    profile = db.get_or_create_player(name.strip())
                    db.join_match(match_id, name.strip(), profile["rating"])
                    _set_my_name(match_id, name.strip())
                    _set_active_match_id(match_id)
                    st.rerun()

    with tab_leaderboard:
        players = elo.get_leaderboard(db)
        if not players:
            st.caption("No matches played yet.")
        else:
            # --- Pandas pipeline: raw player dicts -> clean, derived,
            # ranked table. Everything below this line operates on a real
            # DataFrame (not a list of dicts) so sorting/derived columns
            # are vectorized, not hand-rolled per-row Python.
            df = pd.DataFrame(players)
            for col, default in [("rating", 1000), ("wins", 0), ("losses", 0), ("matches_played", 0)]:
                if col not in df.columns:
                    df[col] = default
                df[col] = df[col].fillna(default)

            df["win_rate"] = (
                (df["wins"] / df["matches_played"].replace(0, pd.NA) * 100)
                .fillna(0)
                .round(1)
            )
            df = df.sort_values("rating", ascending=False).reset_index(drop=True)
            df.insert(0, "rank", df.index + 1)

            df = df.rename(columns={
                "rank": "Rank", "name": "Player", "rating": "Rating",
                "wins": "Wins", "losses": "Losses",
                "matches_played": "Matches", "win_rate": "Win Rate",
            })[["Rank", "Player", "Rating", "Win Rate", "Wins", "Losses", "Matches"]]

            # data_editor (not plain st.dataframe) for the built-in
            # sort/filter UI and richer column rendering (ProgressColumn
            # for win rate) - read-only via disabled=True since editing a
            # leaderboard by hand isn't meaningful, but the widget itself
            # still gives the interactive grid experience.
            st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                disabled=True,
                key="leaderboard_editor",
                column_config={
                    "Rank": st.column_config.NumberColumn("RANK", width="small"),
                    "Player": st.column_config.TextColumn("PLAYER", width="medium"),
                    "Rating": st.column_config.NumberColumn("RATING", width="small"),
                    "Win Rate": st.column_config.ProgressColumn(
                        "WIN RATE", min_value=0, max_value=100, format="%.0f%%",
                    ),
                    "Wins": st.column_config.NumberColumn("W", width="small"),
                    "Losses": st.column_config.NumberColumn("L", width="small"),
                    "Matches": st.column_config.NumberColumn("MATCHES", width="small"),
                },
            )


# ---------------------------------------------------------------------------
# Screen: inside a match
# ---------------------------------------------------------------------------

def render_match(match_id: str) -> None:
    state = db.get_match_state(match_id)
    round_number = state.get("round_number", 1) if state else 1

    # Slow down polling for THIS tab while it's mid-Gemini/JDoodle-call, so
    # the autorefresh timer doesn't fire (and interrupt/duplicate the call)
    # before a multi-second round-trip finishes. See the BUSY-FLAG /
    # AUTOREFRESH FIX note at the top of this file - the flags below are
    # only ever set to True in a "phase 1" run that does nothing else but
    # set-the-flag-and-rerun, specifically so this check here is already
    # seeing True by the time the slow call actually starts in phase 2.
    busy = bool(
        st.session_state.get(f"generating_{match_id}")
        or st.session_state.get(f"judging_{match_id}_{round_number}")
        or st.session_state.get(f"submitting_{match_id}_{round_number}")
    )
    st_autorefresh(interval=8000 if busy else 3000, key=f"poll_{match_id}_{round_number}")

    if not state:
        st.error(f"Match {match_id} not found - it may not exist yet.")
        if st.button("BACK"):
            _clear_active_match_id()
            st.rerun()
        return

    players = state.get("players", {})
    me = _my_name(match_id)

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
                    profile = db.get_or_create_player(name.strip())
                    db.join_match(match_id, name.strip(), profile["rating"])
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

    a_name, b_name = names[0], names[1]
    a, b = players[a_name], players[b_name]
    round_wins = state.get("round_wins", {})

    st.markdown(
        f"""
        <div class="cc-card">
          <div class="cc-panel-a">
            <div class="cc-name">{a_name}</div>
            <div class="cc-rating" style="color:#9FE1CB;">RATING {a['rating']} · ROUNDS {round_wins.get(a_name, 0)}</div>
          </div>
          <div class="cc-panel-b">
            <div class="cc-name">{b_name}</div>
            <div class="cc-rating" style="color:#F09595;">RATING {b['rating']} · ROUNDS {round_wins.get(b_name, 0)}</div>
          </div>
          <div class="cc-vs">VS</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    status = state.get("status")
    if status in ("waiting", "active", "waiting_next_round"):
        # "waiting" at this point always means "2 players present, puzzle
        # not generated yet" - the len(names) < 2 branch above already
        # handled the "waiting for opponent" case and returned. Status only
        # flips to "active" AFTER db.set_puzzle() succeeds, so this branch
        # has to also own the "waiting" state or puzzle generation never
        # gets triggered at all (that was the bug).
        render_puzzle_section(match_id, state, me, round_number, players)
    elif status == "match_over":
        render_match_finalize(match_id, state, players)
    elif status == "complete":
        render_match_complete(state, players)
    else:
        st.write(f"Unhandled status: {status}")

    if st.button("LEAVE MATCH"):
        _clear_active_match_id()
        st.rerun()


# ---------------------------------------------------------------------------
# Puzzle generation (race-guarded, self-healing on a stale/interrupted claim)
# ---------------------------------------------------------------------------

def _collect_prior_questions(state: dict, problem_type: str) -> list[str]:
    """Pulls the question/statement text from every earlier round in this
    match, so generate_puzzle() can ask Gemini to avoid repeating them.
    Field name differs per problem_type (coding/debug use "statement" or
    "buggy_code", aptitude/logic use "question")."""
    text_field = _QUESTION_FIELD_LOOKUP
    field = text_field.get(problem_type, "statement")
    rounds = state.get("rounds", {}) or {}
    prior = []
    for round_data in rounds.values():
        puzzle = (round_data or {}).get("puzzle")
        if puzzle and puzzle.get(field):
            prior.append(puzzle[field])
    return prior


def _generate_one_puzzle(problem_type: str, language: str | None, round_number: int, avoid: list[str]) -> dict:
    topic_pool = TOPIC_POOL.get(problem_type, [DEFAULT_TOPIC.get(problem_type, "general")])
    topic = topic_pool[0] if round_number == 1 else random.choice(topic_pool)
    try:
        return gemini.generate_puzzle(
            problem_type=problem_type, difficulty=DEFAULT_DIFFICULTY,
            topic=topic, language=language, avoid=avoid,
        )
    except Exception as e:
        st.warning(f"Gemini call failed for round {round_number} ({e}) - using a fallback puzzle.")
        return gemini.get_fallback_puzzle(problem_type, avoid=avoid)


def render_puzzle_section(match_id: str, state: dict, me: str, round_number: int, players: dict) -> None:
    round_state = db.get_round(state, round_number)
    puzzle = round_state.get("puzzle")
    problem_type = state["problem_type"]
    language = state.get("language")
    rounds_total = state.get("rounds_total", 1)

    gen_flag = f"generating_{match_id}"  # one flag for the whole batch, not per-round

    if puzzle is None:
        if state.get("puzzle_generation_claimed_by") and db.claim_is_stale(state):
            db.release_stale_claim(match_id)
            st.session_state[gen_flag] = False

        # --- Phase 2: we already own the claim from a previous run, and
        # this run's busy=True already slowed the autorefresh interval
        # before it fired. Safe to actually make the slow Gemini calls now.
        if st.session_state.get(gen_flag):
            spinner_msg = (
                "Preparing all questions for this match..." if rounds_total > 1
                else "Generating puzzle..."
            )
            try:
                # Generate every round's puzzle now, not just this one - so
                # rounds 2..N load instantly later instead of each round
                # making the players sit through a fresh Gemini call. This
                # only runs once per match (round 1's puzzle being None is
                # what triggers it); rounds 2+ finding puzzle=None here is
                # the fallback safety net, not the normal path.
                avoid: list[str] = _collect_prior_questions(state, problem_type)
                with st.spinner(spinner_msg):
                    for rn in range(round_number, rounds_total + 1):
                        p = _generate_one_puzzle(problem_type, language, rn, avoid)
                        db.set_puzzle(match_id, rn, p)
                        field = _QUESTION_FIELD_LOOKUP.get(problem_type, "question")
                        if p.get(field):
                            avoid = avoid + [p[field]]
            finally:
                st.session_state[gen_flag] = False
            st.rerun()
            return

        # --- Phase 1: try to claim, then ONLY set the flag and rerun.
        # Do not call Gemini in this same script pass - see file header.
        if db.try_claim_puzzle_generation(match_id, me):
            st.session_state[gen_flag] = True
            st.rerun()
            return
        else:
            st.info("Opponent is preparing the questions - hang tight...")
            return

    st.divider()
    rounds_total_for_rail = state.get("rounds_total", 1)
    rail_segs = "".join(
        f'<div class="cc-rail-seg {"cc-rail-done" if i < round_number - 1 else "cc-rail-current" if i == round_number - 1 else ""}"></div>'
        for i in range(rounds_total_for_rail)
    )
    st.markdown(
        f'<div class="cc-rail-wrap"><span class="cc-rail-label">ROUND {round_number}/{rounds_total_for_rail}</span>'
        f'<div class="cc-rail">{rail_segs}</div></div>',
        unsafe_allow_html=True,
    )

    sample_tests = (puzzle.get("test_cases") or [])[:2] if problem_type in ("coding", "debug") else []
    options = []
    default_code = ""

    if problem_type == "coding":
        st.markdown(f"**{puzzle.get('title', 'Puzzle')}**")
        st.write(puzzle.get("statement", ""))
        default_code = puzzle.get("starter_code", "")
    elif problem_type == "debug":
        st.markdown("**Find and fix the bug:**")
        st.write(puzzle.get("expected_behavior", ""))
        st.code(puzzle.get("buggy_code", ""))
        default_code = puzzle.get("buggy_code", "")
    elif problem_type == "aptitude":
        st.markdown(f"**{puzzle.get('question', '')}**")
        options = puzzle.get("options", [])
    elif problem_type == "logic":
        st.markdown(f"**{puzzle.get('question', '')}**")
    else:
        st.write(puzzle)

    if sample_tests:
        with st.expander(f"Sample test cases ({len(sample_tests)} shown - more are hidden for grading)"):
            for i, tc in enumerate(sample_tests, 1):
                st.code(f"Input: {tc['input']}\nExpected: {tc['expected']}")

    my_submission = round_state.get("submissions", {}).get(me)

    if my_submission is not None:
        st.success("Submitted. Waiting on your opponent...")
        my_results = round_state.get("test_results", {}).get(me)
        if my_results:
            passed = sum(1 for r in my_results if r.get("passed"))
            st.caption(f"Your result: {passed}/{len(my_results)} test cases passed.")
        if db.both_submitted(round_state, players):
            render_round_resolution(match_id, state, round_state, round_number, players, me)
        return

    _render_submission_form(match_id, round_number, me, problem_type, language, puzzle, default_code, options, sample_tests)


def _render_submission_form(
    match_id, round_number, me, problem_type, language, puzzle, default_code, options, sample_tests
) -> None:
    if problem_type == "aptitude":
        with st.form("submission_form"):
            choice = st.radio("Your answer", options) if options else None
            go = st.form_submit_button("SUBMIT")
        if go and choice is not None:
            idx = options.index(choice)
            db.submit_solution(match_id, round_number, me, {"answer": choice, "selected_index": idx})
            results = grading.grade("aptitude", selected_index=idx, correct_index=puzzle.get("correct_index"))
            db.record_test_results(match_id, round_number, me, results)
            if results and results[0].get("passed"):
                db.increment_points(match_id, me, 1)
            st.rerun()
        return

    if problem_type == "logic":
        answer = st.text_area("Your answer / reasoning", height=200, key=f"logic_{match_id}_{round_number}")
        if st.button("SUBMIT"):
            db.submit_solution(match_id, round_number, me, {"answer": answer})
            db.record_test_results(match_id, round_number, me, [])  # no deterministic check for logic
            st.rerun()
        return

    # coding / debug - Run (sample tests only) then Submit (all tests).
    # Submit is the slow/costly one (loops JDoodle calls across every test
    # case), so it gets the same two-phase busy-flag treatment as puzzle
    # generation and judging. Run is comparatively cheap (max 2 calls,
    # capped by sample_tests) and stays single-phase - a stalled Run just
    # shows nothing and can be re-clicked, it doesn't wedge the match.
    code = st.text_area("Your code", value=default_code, height=220, key=f"code_{match_id}_{round_number}")
    run_key = f"run_results_{match_id}_{round_number}_{me}"
    submit_flag = f"submitting_{match_id}_{round_number}"
    pending_code_key = f"pending_code_{match_id}_{round_number}"

    # --- Phase 2: submit was triggered on a previous run, busy=True has
    # already slowed this run's autorefresh before it fired. Safe to
    # actually call JDoodle now.
    if st.session_state.get(submit_flag):
        saved_code = st.session_state.get(pending_code_key, code)
        if not language:
            st.error("No language set for this match.")
            st.session_state[submit_flag] = False
        else:
            db.submit_solution(match_id, round_number, me, {"code": saved_code})
            with st.spinner("Grading against all test cases..."):
                try:
                    results = grading.grade(
                        problem_type, code=saved_code, language=language,
                        test_cases=puzzle.get("test_cases", []),
                    )
                except Exception as e:
                    st.error(f"Grading failed: {e}")
                    results = []
            db.record_test_results(match_id, round_number, me, results)
            st.session_state[submit_flag] = False
            st.session_state.pop(pending_code_key, None)
            st.session_state.pop(run_key, None)
            st.rerun()
            return

    col_run, col_submit = st.columns(2)
    with col_run:
        if st.button("RUN SAMPLE TESTS", use_container_width=True):
            if not language:
                st.error("No language set for this match.")
            elif not sample_tests:
                st.warning("No sample tests available for this puzzle.")
            else:
                with st.spinner("Running..."):
                    try:
                        st.session_state[run_key] = grading.run_sample_tests(code, language, sample_tests)
                    except Exception as e:
                        st.error(f"Run failed: {e}")

    with col_submit:
        submit_clicked = st.button("SUBMIT FINAL", type="primary", use_container_width=True)

    if run_key in st.session_state:
        for i, r in enumerate(st.session_state[run_key], 1):
            label = "PASS" if r["passed"] else "FAIL"
            st.write(f"Test {i}: **{label}**  ·  runtime {r.get('time_sec', '?')}s  ·  memory {r.get('memory_kb', '?')}KB")
            if not r["passed"]:
                st.caption(f"Expected: `{r['expected']}`  ·  Got: `{r['stdout']}`")

    # --- Phase 1: just record the code + flip the flag + rerun. The actual
    # JDoodle grading call happens above, on the NEXT run, once busy=True
    # has already taken effect for that run's autorefresh interval.
    if submit_clicked:
        if not language:
            st.error("No language set for this match.")
        else:
            st.session_state[pending_code_key] = code
            st.session_state[submit_flag] = True
            st.rerun()


# ---------------------------------------------------------------------------
# Round resolution: hybrid scoring (deterministic pass ratio + Gemini
# qualitative score) once both players have submitted.
# ---------------------------------------------------------------------------

def render_round_resolution(match_id, state, round_state, round_number, players, me) -> None:
    if round_state.get("verdict") is not None:
        # Verdict already exists in the DB - just show it and wait for a
        # CONTINUE click. Advancing to the next round / match_over now
        # happens ONLY from this explicit click (db.advance_round), not
        # automatically right after judging - that's what was causing the
        # result to flash and vanish: the old code advanced status in the
        # same write as the verdict, so the very next rerun already saw a
        # different screen before you could read this one.
        _render_verdict(round_state)
        rounds_total = state.get("rounds_total", 1)
        is_last_round = round_number >= rounds_total
        button_label = "SEE FINAL RESULT" if is_last_round else "NEXT ROUND"
        st.divider()
        if st.button(button_label, type="primary", use_container_width=True):
            db.advance_round(match_id, round_number)
            st.rerun()
        else:
            st.caption("Either player can click continue when ready.")
        return

    problem_type = state["problem_type"]

    if round_state.get("judging_claimed_by") and db.judging_claim_is_stale(round_state):
        db.release_stale_judging_claim(match_id, round_number)

    judge_flag = f"judging_{match_id}_{round_number}"

    # --- Phase 2: we already hold the judging claim from a previous run,
    # and busy=True already slowed this run's autorefresh before it fired.
    # Safe to actually call Gemini (and, for aptitude, just score) now.
    if st.session_state.get(judge_flag):
        try:
            names = list(players.keys())
            a_name, b_name = names[0], names[1]
            submissions = round_state.get("submissions", {})
            test_results = round_state.get("test_results", {})
            results_a, results_b = test_results.get(a_name, []), test_results.get(b_name, [])

            if problem_type == "aptitude":
                # No AI judging for MCQ - there's nothing qualitative to
                # judge, only right or wrong. Skips the Gemini call
                # entirely (saves a call, and avoids Gemini returning an
                # out-of-range "quality score" for a question type it was
                # never meant to score).
                correct_a = bool(results_a and results_a[0].get("passed"))
                correct_b = bool(results_b and results_b[0].get("passed"))
                score_a, score_b = (1 if correct_a else 0), (1 if correct_b else 0)
                verdict = {
                    "verdict": (
                        f"{a_name}: {'correct' if correct_a else 'incorrect'} · "
                        f"{b_name}: {'correct' if correct_b else 'incorrect'}"
                    ),
                    "score_a": score_a, "score_b": score_b,
                    "player_a": a_name, "player_b": b_name,
                    "time_complexity_a": "N/A", "space_complexity_a": "N/A",
                    "time_complexity_b": "N/A", "space_complexity_b": "N/A",
                }
                round_winner = None if score_a == score_b else (a_name if score_a > score_b else b_name)
                db.record_round_verdict(match_id, round_number, verdict, round_winner)
            else:
                ratio_a = grading.pass_ratio(results_a)
                ratio_b = grading.pass_ratio(results_b)

                with st.spinner("Judging round..."):
                    try:
                        ai_verdict = gemini.judge_submissions(
                            puzzle=round_state.get("puzzle"), player_a=a_name, player_b=b_name,
                            submission_a=submissions.get(a_name, {}), submission_b=submissions.get(b_name, {}),
                            results_a=results_a, results_b=results_b,
                        )
                    except Exception as e:
                        st.warning(f"Gemini judging failed ({e}) - scoring on test results only.")
                        ai_verdict = {
                            "verdict": "AI judge unavailable this round - scored on deterministic test results only.",
                            "quality_score_a": 5, "quality_score_b": 5,
                            "time_complexity_a": "N/A", "space_complexity_a": "N/A",
                            "time_complexity_b": "N/A", "space_complexity_b": "N/A",
                        }

                quality_a = ai_verdict.get("quality_score_a", 5) / 10
                quality_b = ai_verdict.get("quality_score_b", 5) / 10

                if problem_type == "logic":
                    score_a, score_b = quality_a, quality_b  # no ground truth - AI-judged only
                    round_winner = None if abs(score_a - score_b) < 1e-9 else (a_name if score_a > score_b else b_name)
                else:
                    # coding/debug: clean +1/0 marks (fully solved or not)
                    # - NOT a blended fractional number. Gemini's quality/
                    # complexity analysis is still shown to the player as
                    # feedback, but only breaks a TIE (both fully solved,
                    # or both failed) in deciding the round winner - it
                    # never changes the displayed marks themselves.
                    score_a = 1 if ratio_a == 1.0 else 0
                    score_b = 1 if ratio_b == 1.0 else 0
                    if score_a != score_b:
                        round_winner = a_name if score_a > score_b else b_name
                    else:
                        round_winner = (
                            None if abs(quality_a - quality_b) < 1e-9
                            else (a_name if quality_a > quality_b else b_name)
                        )

                verdict = {**ai_verdict, "score_a": score_a, "score_b": score_b,
                           "player_a": a_name, "player_b": b_name}
                db.record_round_verdict(match_id, round_number, verdict, round_winner)
        finally:
            st.session_state[judge_flag] = False
        st.rerun()
        return

    if not db.try_claim_judging(match_id, round_number, me):
        st.info("Opponent's session is scoring this round...")
        return

    # --- Phase 1: just claim + flag it, THEN rerun so the busy poll
    # interval is active before the slow Gemini call starts.
    st.session_state[judge_flag] = True
    st.rerun()


def _render_verdict(round_state: dict) -> None:
    v = round_state.get("verdict", {})
    st.markdown(
        f"""
        <div class="cc-verdict">
          <div class="cc-verdict-line">{v.get("verdict", "")}</div>
          <div class="cc-verdict-grid">
            <div class="cc-verdict-side cc-verdict-a">
              <div class="cc-verdict-name">{v.get('player_a', 'Player A')}</div>
              <div class="cc-verdict-score">{v.get('score_a', '?')}</div>
              <div class="cc-verdict-meta">TIME {v.get('time_complexity_a', 'N/A')} &middot; SPACE {v.get('space_complexity_a', 'N/A')}</div>
            </div>
            <div class="cc-verdict-side cc-verdict-b">
              <div class="cc-verdict-name">{v.get('player_b', 'Player B')}</div>
              <div class="cc-verdict-score">{v.get('score_b', '?')}</div>
              <div class="cc-verdict-meta">TIME {v.get('time_complexity_b', 'N/A')} &middot; SPACE {v.get('space_complexity_b', 'N/A')}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Match finalization: apply Elo once, after the last round.
# ---------------------------------------------------------------------------

def render_match_finalize(match_id: str, state: dict, players: dict) -> None:
    me = _my_name(match_id)
    rating_flag = f"applying_ratings_{match_id}"

    if state.get("rating_claimed_by") and db.rating_claim_is_stale(state):
        db.release_stale_rating_claim(match_id)

    if st.session_state.get(rating_flag):
        st.info("Finalizing match...")
        return

    if not db.try_claim_rating_application(match_id, me):
        st.info("Finalizing match...")
        return

    st.session_state[rating_flag] = True
    try:
        names = list(players.keys())
        a_name, b_name = names[0], names[1]

        if state["problem_type"] == "aptitude":
            # Rank by total correct answers (+1 each), not head-to-head
            # round_wins - see db.increment_points() for why these differ.
            points = state.get("points", {})
            wins_a, wins_b = points.get(a_name, 0), points.get(b_name, 0)
        else:
            round_wins = state.get("round_wins", {})
            wins_a, wins_b = round_wins.get(a_name, 0), round_wins.get(b_name, 0)

        score_a = 0.5 if wins_a == wins_b else (1.0 if wins_a > wins_b else 0.0)

        new_a, new_b = elo.update_elo(players[a_name]["rating"], players[b_name]["rating"], score_a)
        result_a = "tie" if score_a == 0.5 else ("win" if score_a == 1.0 else "loss")
        result_b = "tie" if score_a == 0.5 else ("win" if score_a == 0.0 else "loss")

        db.update_player_after_match(a_name, new_a, result_a)
        db.update_player_after_match(b_name, new_b, result_b)
        db.complete_match(match_id, {a_name: new_a, b_name: new_b})
    finally:
        st.session_state[rating_flag] = False
    st.rerun()


def render_match_complete(state: dict, players: dict) -> None:
    final = state.get("final_ratings", {})
    names = list(players.keys())
    a_name, b_name = names[0], names[1]
    is_aptitude = state["problem_type"] == "aptitude"
    tally = state.get("points", {}) if is_aptitude else state.get("round_wins", {})
    tally_label = "correct answer(s)" if is_aptitude else "round(s) won"

    st.markdown("### Match complete")
    col_a, col_b = st.columns(2)
    with col_a:
        delta_a = final.get(a_name, players[a_name]["rating"]) - players[a_name]["rating"]
        st.metric(a_name, f"{final.get(a_name, '?')}", delta=delta_a)
        st.caption(f"{tally.get(a_name, 0)} {tally_label}")
    with col_b:
        delta_b = final.get(b_name, players[b_name]["rating"]) - players[b_name]["rating"]
        st.metric(b_name, f"{final.get(b_name, '?')}", delta=delta_b)
        st.caption(f"{tally.get(b_name, 0)} {tally_label}")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

match_id = _get_active_match_id()
if match_id:
    render_match(match_id)
else:
    render_landing()