"""
Phase 3: Gemini calls - puzzle generation + judging.

Free-tier budget notes (Flash models, per Google's current pricing page):
- ~2 Gemini calls per round (1 puzzle gen + 1 judge) -> ~6 calls per 3-round match
- Cache the puzzle in the DB row so it's generated once per match, not once per player
- Wrap calls with backoff so a 429 shows a spinner, not a crash
"""

import json
import time
import google.generativeai as genai
import streamlit as st

from prompts.templates import PUZZLE_PROMPTS, JUDGE_PROMPT

genai.configure(api_key=st.secrets["gemini_api_key"])
MODEL_NAME = "gemini-3.5-flash"


def _call_with_backoff(model, prompt: str, max_retries: int = 3) -> str:
    for attempt in range(max_retries):
        try:
            resp = model.generate_content(prompt)
            return resp.text
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # 1s, 2s, 4s


def _parse_json(raw: str) -> dict:
    # strip accidental markdown fences before parsing
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


def generate_puzzle(problem_type: str, difficulty: str, topic: str, language: str | None) -> dict:
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = PUZZLE_PROMPTS[problem_type].format(
        difficulty=difficulty, topic=topic, language=language or "N/A"
    )
    raw = _call_with_backoff(model, prompt)
    return _parse_json(raw)


def judge_submissions(
    puzzle: dict, player_a: str, player_b: str, submission_a: dict,
    submission_b: dict, results_a: list, results_b: list,
) -> dict:
    model = genai.GenerativeModel(MODEL_NAME)
    prompt = JUDGE_PROMPT.format(
        puzzle=puzzle, player_a=player_a, player_b=player_b,
        submission_a=submission_a, submission_b=submission_b,
        results_a=results_a, results_b=results_b,
    )
    raw = _call_with_backoff(model, prompt)
    return _parse_json(raw)


# Phase 3 fallback: pre-generate ~15-20 puzzles offline (run this file's
# generate_puzzle in a script, save to fallback_puzzles.json) so a live
# rate-limit hit during your demo pulls from this pool instead of failing.
def get_fallback_puzzle(problem_type: str) -> dict:
    with open("prompts/fallback_puzzles.json") as f:
        pool = json.load(f)
    return pool[problem_type][0]  # TODO: randomize / rotate through the pool
