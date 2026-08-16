"""
Phase 2: shared match state.

Streamlit has no websockets and no cross-session memory - each browser
tab is a fully isolated script rerun. Two players "communicate" only by
reading/writing the same row in an external store, keyed by match_id.

match_id lives in st.query_params so both players land on the same row
just by opening the same URL.

Uses Firebase Realtime Database (free Spark plan is enough for this).
Swap for Supabase/Postgres later if you outgrow it - only this file
would need to change, nothing else in the app touches Firebase directly.
"""

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


def create_match(problem_type: str, language: str | None) -> str:
    """Player A calls this. Returns match_id to put in the URL and share."""
    init_db()
    match_id = str(uuid.uuid4())[:8]
    db.reference(f"matches/{match_id}").set(
        {
            "problem_type": problem_type,
            "language": language,
            "status": "waiting",  # waiting -> active -> judged -> complete
            "players": {},
            "puzzle": None,
            "submissions": {},
            "test_results": {},
            "verdict": None,
        }
    )
    return match_id


def join_match(match_id: str, player_name: str, rating: int):
    init_db()
    db.reference(f"matches/{match_id}/players/{player_name}").set(
        {"rating": rating, "joined": True}
    )


def get_match_state(match_id: str) -> dict:
    """Call this every rerun / poll tick to pull the latest shared state."""
    init_db()
    return db.reference(f"matches/{match_id}").get() or {}


def set_puzzle(match_id: str, puzzle: dict):
    init_db()
    db.reference(f"matches/{match_id}/puzzle").set(puzzle)
    db.reference(f"matches/{match_id}/status").set("active")


def submit_solution(match_id: str, player_name: str, submission: dict):
    init_db()
    db.reference(f"matches/{match_id}/submissions/{player_name}").set(submission)


def both_submitted(match_state: dict) -> bool:
    subs = match_state.get("submissions", {})
    players = match_state.get("players", {})
    return len(subs) >= 2 and set(subs.keys()) == set(players.keys())


def set_verdict(match_id: str, verdict: dict, new_ratings: dict):
    init_db()
    db.reference(f"matches/{match_id}").update(
        {"verdict": verdict, "status": "complete", "final_ratings": new_ratings}
    )
