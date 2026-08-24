"""
Phase 3: Gemini calls - puzzle generation + judging + audio transcription.

Uses the current google-genai SDK (the old google.generativeai package is
deprecated and flagged unstable - see migration note below).

IMPORTANT - verify your model name before the demo: free-tier model
availability on Gemini has been volatile through 2026. Check
https://aistudio.google.com (API keys -> your project) for the exact
free-tier model ID available to YOUR key right now, and update MODEL_NAME
below if it differs. Don't assume the model in the original brief is still
correct without checking.

Free-tier budget notes:
- ~2 Gemini calls per round (1 puzzle gen + 1 judge) -> ~6 calls per 3-round match
- transcribe_audio() adds one more call per voice submission (Logic mode only)
- Cache the puzzle in the DB row so it's generated once per match, not once per player
- Wrap calls with backoff so a 429 shows a spinner, not a crash
"""

import json
import time
import random
import difflib
import concurrent.futures
from google import genai
from google.genai import types

from prompts.templates import PUZZLE_PROMPTS, JUDGE_PROMPT

MODEL_NAME = "gemini-3.5-flash"  # confirmed available via list_models.py
CALL_TIMEOUT_SECONDS = 20  # hard ceiling per attempt - see _call_with_backoff
DUPLICATE_SIMILARITY_THRESHOLD = 0.55  # see _is_duplicate
MAX_DEDUP_ATTEMPTS = 3

_client = None
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)


def _get_client():
    """Lazy init - do NOT create the client at module import time. This
    module gets imported by app.py just to be available; creating the
    client eagerly means every page load (even the plain landing screen)
    would crash if gemini_api_key isn't set yet, which defeats the point
    of Phase 1/2 being independently testable."""
    global _client
    if _client is None:
        import streamlit as st
        _client = genai.Client(api_key=st.secrets["gemini_api_key"])
    return _client


def _call_with_backoff(prompt: str, max_retries: int = 3) -> str:
    """
    Hard-timeouts each attempt at CALL_TIMEOUT_SECONDS.

    Without this, a hung network call (bad key behaving oddly, DNS stall,
    firewall silently dropping packets) never raises, so the retry/backoff
    logic below never triggers either - the calling Streamlit script just
    blocks forever on that one synchronous call, which is what "stuck on
    Generating puzzle..." for 5+ minutes actually was. Running the call in
    a worker thread with .result(timeout=...) forces a TimeoutError instead,
    so the caller's except block (which falls back to a pre-baked puzzle)
    actually gets a chance to run.
    """
    client = _get_client()
    for attempt in range(max_retries):
        try:
            future = _executor.submit(
                client.models.generate_content, model=MODEL_NAME, contents=prompt
            )
            resp = future.result(timeout=CALL_TIMEOUT_SECONDS)
            return resp.text
        except Exception:
            if attempt == max_retries - 1:
                raise
            time.sleep(2 ** attempt)  # 1s, 2s, 4s


def _parse_json(raw: str) -> dict:
    # strip accidental markdown fences before parsing
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(cleaned)


_QUESTION_FIELD = {"coding": "statement", "debug": "buggy_code", "aptitude": "question", "logic": "question"}


def _is_duplicate(candidate_text: str, avoid: list[str]) -> bool:
    """
    Asking Gemini nicely to 'not repeat' isn't reliable enough on its own -
    trailing instructions like that get deprioritized, and for a narrow
    domain (aptitude questions especially - there are only so many classic
    templates: train-speed, percentages, work-time...) the model tends to
    converge on the same handful of questions regardless. This does actual
    similarity checking so a near-duplicate gets caught and retried instead
    of silently shown to the player.

    Uses normalized text + difflib ratio rather than exact match, since a
    reworded-but-structurally-identical question ("A train covers 60km in
    45 min..." vs "A train travels 60 km in 45 minutes...") should still
    count as a repeat.
    """
    norm_candidate = " ".join(candidate_text.lower().split())
    for prior in avoid:
        norm_prior = " ".join(prior.lower().split())
        similarity = difflib.SequenceMatcher(None, norm_candidate, norm_prior).ratio()
        if similarity >= DUPLICATE_SIMILARITY_THRESHOLD:
            return True
    return False


def generate_puzzle(
    problem_type: str, difficulty: str, topic: str, language: str | None,
    avoid: list[str] | None = None,
) -> dict:
    avoid = avoid or []
    field = _QUESTION_FIELD.get(problem_type, "question")
    base_prompt = PUZZLE_PROMPTS[problem_type].format(
        difficulty=difficulty, topic=topic, language=language or "N/A"
    )

    last_puzzle = None
    for attempt in range(MAX_DEDUP_ATTEMPTS):
        prompt = base_prompt
        if avoid:
            avoid_list = "\n".join(f"- {q}" for q in avoid)
            prompt += (
                f"\n\nDo NOT repeat or closely rephrase any of these previously-used "
                f"questions in this same match:\n{avoid_list}"
            )
        if attempt > 0:
            # The plain "don't repeat" instruction wasn't enough last try -
            # force real divergence with a concrete random constraint,
            # which is much harder for the model to ignore than a vague
            # instruction.
            forcing_seeds = [
                "Use a completely different scenario/setting than usual.",
                "Base it on a real-world context involving sports.",
                "Base it on a real-world context involving cooking or recipes.",
                "Base it on a real-world context involving travel or maps.",
                "Use different numbers and a different structure than a typical textbook example.",
            ]
            prompt += f"\n\n{random.choice(forcing_seeds)}"

        raw = _call_with_backoff(prompt)
        puzzle = _parse_json(raw)
        last_puzzle = puzzle

        candidate_text = puzzle.get(field, "")
        if not candidate_text or not _is_duplicate(candidate_text, avoid):
            return puzzle
        # else: loop again, now also avoiding this rejected duplicate
        avoid = avoid + [candidate_text]

    # Exhausted retries - return the last attempt rather than fail the
    # round outright. A near-duplicate is a much better outcome than a
    # crashed match, and this is a genuinely rare path (3 straight
    # duplicate detections in one match).
    return last_puzzle


def judge_submissions(
    puzzle: dict, player_a: str, player_b: str, submission_a: dict,
    submission_b: dict, results_a: list, results_b: list,
) -> dict:
    prompt = JUDGE_PROMPT.format(
        puzzle=puzzle, player_a=player_a, player_b=player_b,
        submission_a=submission_a, submission_b=submission_b,
        results_a=results_a, results_b=results_b,
    )
    raw = _call_with_backoff(prompt)
    return _parse_json(raw)


# ---------------------------------------------------------------------------
# Multimodal: mic-recorder transcription for Logic-round voice answers.
# Player records their spoken reasoning via st.audio_input in app.py; this
# sends the raw audio bytes straight to Gemini (audio understanding, not a
# separate speech-to-text API) and gets back a clean transcript, which then
# flows through the exact same text-based judging pipeline as a typed
# answer - no changes needed anywhere else in the scoring logic.
# ---------------------------------------------------------------------------

def transcribe_audio(audio_bytes: bytes, mime_type: str = "audio/wav") -> str:
    """Takes the raw bytes from st.audio_input (WebM/WAV depending on
    browser) and returns a clean transcript string via Gemini's native
    audio understanding. Raises on failure - callers should catch and
    show an error / let the player fall back to typing instead."""
    client = _get_client()
    prompt = (
        "Transcribe this spoken answer verbatim as plain text. Keep the "
        "reasoning content exactly as spoken - only clean up obvious "
        "filler words (um, uh) if they clearly interrupt sentence flow. "
        "Return ONLY the transcript text, nothing else - no preamble, "
        "no markdown, no quotation marks around it."
    )
    future = _executor.submit(
        client.models.generate_content,
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            prompt,
        ],
    )
    resp = future.result(timeout=CALL_TIMEOUT_SECONDS)
    return (resp.text or "").strip()


# Phase 3 fallback: pre-generate ~15-20 puzzles offline (run this file's
# generate_puzzle in a script, save to fallback_puzzles.json) so a live
# rate-limit hit during your demo pulls from this pool instead of failing.
def get_fallback_puzzle(problem_type: str, avoid: list[str] | None = None) -> dict:
    with open("prompts/fallback_puzzles.json") as f:
        pool = json.load(f)
    candidates = pool.get(problem_type, [])
    if not candidates:
        raise ValueError(f"No fallback puzzles for problem_type={problem_type!r}")

    field = _QUESTION_FIELD.get(problem_type, "question")
    avoid = avoid or []
    unused = [p for p in candidates if not _is_duplicate(p.get(field, ""), avoid)]
    return random.choice(unused) if unused else random.choice(candidates)