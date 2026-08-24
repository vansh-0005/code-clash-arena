"""
Shared match state (Phase 2) + persistent player profiles.

SCHEMA (Firebase Realtime Database):

/players/{player_name}:
    rating, wins, losses, matches_played
    history: {push_id: {rating, result, match_id, ts}}  # see record_rating_history()
    - persistent across matches. Using the same name again pulls your real
      rating instead of restarting at 1000. NOTE: names are the only
      identity key here (no auth) - two different people picking the same
      display name will collide and share a rating. Fine for a classroom
      demo, call it out as a known limitation in your design doc.

/matches/{match_id}:
    problem_type, language, status
        ("waiting" | "active" | "waiting_next_round" | "match_over" | "complete")
    rounds_total (int, chosen at creation - best of 1/3/5)
    round_number (1-indexed, current round)
    created_at (ms) - for sorting "recent matches" in analytics
    players: {name: {rating, city, lat, lon}}
        - city/lat/lon are a per-match SNAPSHOT (optional, from the
          create/join form), not pulled from the player's persistent
          profile - this is what powers the "Battle Origins - live
          players" map, which only shows players in matches that
          haven't completed yet.
    round_wins: {name: <count of rounds won so far>}
    puzzle_generation_claimed_by, puzzle_generation_claimed_at (ms)
        - see try_claim_puzzle_generation()
    rounds:
        "r1": {
            puzzle, submissions: {name: {...}}, test_results: {name: [...]},
            verdict: {...}, judging_claimed_by, judging_claimed_at
        },
        "r2": {...}, ...
    final_ratings: {name: new_rating}  # set once, when status -> complete

Streamlit has no websockets and no cross-session memory - each browser tab
is a fully isolated script rerun. Two players "communicate" only by
reading/writing this same row.
"""

import time
import uuid
import firebase_admin
from firebase_admin import credentials, db
import streamlit as st


def init_db():
    if not firebase_admin._apps:
        cred = credentials.Certificate(dict(st.secrets["firebase"]))
        firebase_admin.initialize_app(
            cred, {"databaseURL": st.secrets["firebase"]["database_url"]}
        )


def _now_ms() -> int:
    return int(time.time() * 1000)


def _round_key(round_number: int) -> str:
    """
    Round paths use "r1", "r2", ... instead of "1", "2", ... on purpose.

    Firebase Realtime Database auto-converts a node into a JSON ARRAY when
    every one of its direct child keys is a plain integer string. Since
    round keys start at "1" (no "0" ever exists), a plain-integer scheme
    gets read back as [null, {round1}, {round2}, ...] - array index 0 is
    null padding (no child key "0"), and index N holds the data for child
    key "N" (NOT "N-1"). Prefixing the key with a letter stops Firebase
    from ever triggering that coercion, so callers only ever see a plain
    dict - no list-vs-dict branching needed anywhere that reads rounds.
    """
    return f"r{round_number}"


# ---------------------------------------------------------------------------
# Persistent player profiles (real rating across matches, not a random reset)
# ---------------------------------------------------------------------------

def get_or_create_player(player_name: str) -> dict:
    """Call this instead of hardcoding a starting rating. Returns the
    player's real profile if that name has played before, else creates a
    fresh one at rating 1000."""
    init_db()
    ref = db.reference(f"players/{player_name}")
    profile = ref.get()
    if profile is None:
        profile = {"rating": 1000, "wins": 0, "losses": 0, "matches_played": 0}
        ref.set(profile)
    return profile


def list_players() -> list[dict]:
    """All players, for the leaderboard (utils/elo.py get_leaderboard)."""
    init_db()
    raw = db.reference("players").get() or {}
    return [
        {"name": name, **profile}
        for name, profile in raw.items()
    ]


def update_player_after_match(player_name: str, new_rating: int, result: str) -> None:
    """result: 'win' | 'loss' | 'tie' - ties (possible when an odd number
    of rounds includes a drawn round) count toward matches_played but not
    wins/losses."""
    init_db()
    ref = db.reference(f"players/{player_name}")
    profile = ref.get() or {"rating": 1000, "wins": 0, "losses": 0, "matches_played": 0}
    updates = {"rating": new_rating, "matches_played": profile.get("matches_played", 0) + 1}
    if result == "win":
        updates["wins"] = profile.get("wins", 0) + 1
    elif result == "loss":
        updates["losses"] = profile.get("losses", 0) + 1
    ref.update(updates)


# ---------------------------------------------------------------------------
# Match lifecycle
# ---------------------------------------------------------------------------

def create_match(problem_type: str, language: str | None, rounds_total: int = 1) -> str:
    """Player A calls this. Returns match_id to put in the URL and share."""
    init_db()
    match_id = str(uuid.uuid4())[:8]
    db.reference(f"matches/{match_id}").set(
        {
            "problem_type": problem_type,
            "language": language,
            "status": "waiting",
            "rounds_total": rounds_total,
            "round_number": 1,
            "players": {},
            "round_wins": {},
            "puzzle_generation_claimed_by": None,
            "puzzle_generation_claimed_at": None,
            "rounds": {_round_key(1): _empty_round()},
            "final_ratings": None,
            "created_at": _now_ms(),  # analytics: sort "recent matches"
        }
    )
    return match_id


def _empty_round() -> dict:
    return {"puzzle": None, "submissions": {}, "test_results": {}, "verdict": None}


def join_match(
    match_id: str, player_name: str, rating: int,
    city: str | None = None, lat: float | None = None, lon: float | None = None,
) -> None:
    """city/lat/lon are optional and only ever a per-MATCH snapshot (not
    saved to the persistent player profile) - they power the live
    "Battle Origins" map, which is only meant to show where CURRENTLY
    ACTIVE players are, not a permanent record of anyone's location."""
    init_db()
    db.reference(f"matches/{match_id}/players/{player_name}").set(
        {"rating": rating, "city": city, "lat": lat, "lon": lon}
    )
    db.reference(f"matches/{match_id}/round_wins/{player_name}").set(0)


def get_match_state(match_id: str) -> dict:
    """Call this every rerun / poll tick to pull the latest shared state."""
    init_db()
    return db.reference(f"matches/{match_id}").get() or {}


def get_round(state: dict, round_number: int | None = None) -> dict:
    """Convenience accessor - the current round's sub-dict. See _round_key()
    for why round keys are "r1"/"r2"/... rather than plain integers."""
    rn = round_number or state.get("round_number", 1)
    rounds = state.get("rounds", {}) or {}
    round_data = rounds.get(_round_key(rn))
    return round_data if round_data is not None else _empty_round()


# ---------------------------------------------------------------------------
# Generic "exactly one session should do this" claim guard, used for
# puzzle generation, judging, and rating application - all single Gemini/
# Elo operations that must not be triggered twice by two concurrent
# sessions polling the same state.
# ---------------------------------------------------------------------------

def _try_claim(claim_path: str, ts_path: str, player_name: str) -> bool:
    ref = db.reference(claim_path)

    def _txn(current_value):
        if current_value is not None:
            return current_value  # already claimed - abort, no-op
        return player_name

    new_value = ref.transaction(_txn)
    if new_value == player_name:
        db.reference(ts_path).set(_now_ms())
        return True
    return False


def _claim_is_stale(claimed_at, max_age_seconds: int = 20) -> bool:
    """True if a claim has sat unresolved for over max_age_seconds -
    almost certainly means the claiming session was interrupted mid-call.
    A claim with NO timestamp at all is also treated as stale (rather than
    permanently un-releasable), so a write that lost its timestamp for any
    reason can still self-heal instead of deadlocking the match forever."""
    if claimed_at is None:
        return True
    return (_now_ms() - claimed_at) > (max_age_seconds * 1000)


def _release_claim(claim_path: str, ts_path: str) -> None:
    # firebase_admin's .set(None) raises ValueError - .delete() is the
    # correct call to clear a reference back to "not present".
    db.reference(claim_path).delete()
    db.reference(ts_path).delete()


def try_claim_puzzle_generation(match_id: str, player_name: str) -> bool:
    init_db()
    return _try_claim(
        f"matches/{match_id}/puzzle_generation_claimed_by",
        f"matches/{match_id}/puzzle_generation_claimed_at",
        player_name,
    )


def claim_is_stale(state: dict, max_age_seconds: int = 180) -> bool:
    # 180s (not the 20s used for judging/rating) because this claim now
    # covers generating EVERY round's puzzle in one batch at match start -
    # worst case (retries + timeouts across up to 5 rounds) can
    # legitimately take a couple minutes.
    return _claim_is_stale(state.get("puzzle_generation_claimed_at"), max_age_seconds)


def release_stale_claim(match_id: str) -> None:
    init_db()
    _release_claim(
        f"matches/{match_id}/puzzle_generation_claimed_by",
        f"matches/{match_id}/puzzle_generation_claimed_at",
    )


def try_claim_judging(match_id: str, round_number: int, player_name: str) -> bool:
    init_db()
    return _try_claim(
        f"matches/{match_id}/rounds/{_round_key(round_number)}/judging_claimed_by",
        f"matches/{match_id}/rounds/{_round_key(round_number)}/judging_claimed_at",
        player_name,
    )


def judging_claim_is_stale(round_state: dict, max_age_seconds: int = 20) -> bool:
    return _claim_is_stale(round_state.get("judging_claimed_at"), max_age_seconds)


def release_stale_judging_claim(match_id: str, round_number: int) -> None:
    init_db()
    _release_claim(
        f"matches/{match_id}/rounds/{_round_key(round_number)}/judging_claimed_by",
        f"matches/{match_id}/rounds/{_round_key(round_number)}/judging_claimed_at",
    )


def try_claim_rating_application(match_id: str, player_name: str) -> bool:
    init_db()
    return _try_claim(
        f"matches/{match_id}/rating_claimed_by",
        f"matches/{match_id}/rating_claimed_at",
        player_name,
    )


def rating_claim_is_stale(state: dict, max_age_seconds: int = 20) -> bool:
    return _claim_is_stale(state.get("rating_claimed_at"), max_age_seconds)


def release_stale_rating_claim(match_id: str) -> None:
    init_db()
    _release_claim(f"matches/{match_id}/rating_claimed_by", f"matches/{match_id}/rating_claimed_at")


def set_puzzle(match_id: str, round_number: int, puzzle: dict) -> None:
    init_db()
    db.reference(f"matches/{match_id}/rounds/{_round_key(round_number)}/puzzle").set(puzzle)
    db.reference(f"matches/{match_id}/status").set("active")
    db.reference(f"matches/{match_id}/puzzle_generation_claimed_by").delete()
    db.reference(f"matches/{match_id}/puzzle_generation_claimed_at").delete()


# ---------------------------------------------------------------------------
# Submissions / results / verdict for the CURRENT round
# ---------------------------------------------------------------------------

def submit_solution(match_id: str, round_number: int, player_name: str, submission: dict) -> None:
    init_db()
    db.reference(
        f"matches/{match_id}/rounds/{_round_key(round_number)}/submissions/{player_name}"
    ).set(submission)


def increment_points(match_id: str, player_name: str, delta: int = 1) -> None:
    """Aptitude scoring: +1 per individually correct answer, tracked
    independent of head-to-head round_wins."""
    init_db()
    ref = db.reference(f"matches/{match_id}/points/{player_name}")

    def _txn(current):
        return (current or 0) + delta

    ref.transaction(_txn)


def record_test_results(match_id: str, round_number: int, player_name: str, results: list) -> None:
    init_db()
    db.reference(
        f"matches/{match_id}/rounds/{_round_key(round_number)}/test_results/{player_name}"
    ).set(results)


def both_submitted(round_state: dict, players: dict) -> bool:
    subs = round_state.get("submissions", {}) or {}
    return len(subs) >= 2 and set(subs.keys()) == set(players.keys())


def record_round_verdict(match_id: str, round_number: int, verdict: dict, round_winner: str | None) -> None:
    """round_winner: a player_name, or None for a tied round. ONLY writes
    the verdict + round_wins - deliberately does NOT touch status/
    round_number (see advance_round() below). This split exists so the
    round-result screen can stay visible until a player clicks CONTINUE,
    instead of the match silently jumping to the next round/match_over in
    the same write, which used to make the verdict flash and vanish
    before anyone could read it."""
    init_db()
    match_ref = db.reference(f"matches/{match_id}")
    state = match_ref.get()

    match_ref.child(f"rounds/{_round_key(round_number)}/verdict").set(verdict)

    if round_winner:
        current = state.get("round_wins", {}).get(round_winner, 0)
        match_ref.child(f"round_wins/{round_winner}").set(current + 1)


def advance_round(match_id: str, round_number: int) -> bool:
    """Moves the match on from a just-verdicted round to the next round
    (or to match_over if that was the last one). Called only when a
    player clicks CONTINUE - never automatically.

    Guarded with a transaction on round_number so that if both players'
    tabs click CONTINUE around the same time, only one of them actually
    performs the advance; the second call is a safe no-op."""
    init_db()
    match_ref = db.reference(f"matches/{match_id}")
    round_number_ref = match_ref.child("round_number")

    def _txn(current):
        if current != round_number:
            return current  # already advanced by the other tab - no-op
        return round_number + 1

    new_value = round_number_ref.transaction(_txn)
    if new_value != round_number + 1:
        return False

    state = match_ref.get()
    rounds_total = state.get("rounds_total", 1)
    if round_number < rounds_total:
        # Do NOT overwrite rounds/{next_round} here - its puzzle was
        # already written during the upfront batch-generation pass at
        # match start.
        match_ref.child("status").set("waiting_next_round")
    else:
        match_ref.child("status").set("match_over")  # ratings applied separately
    return True


def complete_match(match_id: str, final_ratings: dict) -> None:
    """Call once, after the last round's verdict, to write final ratings
    and flip status to 'complete'."""
    init_db()
    db.reference(f"matches/{match_id}").update(
        {"final_ratings": final_ratings, "status": "complete"}
    )


# ---------------------------------------------------------------------------
# Analytics - rating history log + aggregate match data.
# ---------------------------------------------------------------------------

def record_rating_history(player_name: str, rating: int, result: str, match_id: str) -> None:
    """/players/{name} only ever stores the CURRENT rating (overwritten
    every match) - this appends an immutable snapshot each time a match
    completes, so the analytics tab has an actual time series to chart."""
    init_db()
    db.reference(f"players/{player_name}/history").push({
        "rating": rating, "result": result, "match_id": match_id, "ts": _now_ms(),
    })


def get_player_history(player_name: str) -> list[dict]:
    """Chronological list of {rating, result, match_id, ts}, oldest first."""
    init_db()
    raw = db.reference(f"players/{player_name}/history").get() or {}
    entries = list(raw.values())
    entries.sort(key=lambda e: e.get("ts", 0))
    return entries


def get_all_matches() -> list[dict]:
    """Every match ever created, each tagged with its match_id - used for
    aggregate analytics (mode popularity, average rounds, recent-matches
    list) and the live Battle Origins map. Fine at demo scale; a real
    production version would want a secondary index instead of pulling
    the whole /matches tree."""
    init_db()
    raw = db.reference("matches").get() or {}
    return [{**(m or {}), "match_id": match_id} for match_id, m in raw.items()]