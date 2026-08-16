"""
Phase 4: grading dispatch.

Each problem_type routes to its own grading strategy:
- coding / debug -> deterministic (Judge0 executes real code against test cases)
- aptitude       -> deterministic (exact match, no AI needed, instant)
- logic          -> AI-judged only (no ground truth exists to check against)

This is the "hybrid grading" piece: Judge0 gives the hard correctness
signal, Gemini's judge_submissions() (see utils/gemini.py) adds the
qualitative layer on top - approach quality, complexity, style.
"""

import requests
import streamlit as st

JUDGE0_URL = "https://judge0-ce.p.rapidapi.com/submissions"
LANG_IDS = {"PY": 71, "C++": 54, "JAVA": 62, "JS": 63}


def run_code_judge0(code: str, language: str, stdin: str) -> str:
    headers = {
        "X-RapidAPI-Key": st.secrets["judge0_api_key"],
        "X-RapidAPI-Host": "judge0-ce.p.rapidapi.com",
        "Content-Type": "application/json",
    }
    payload = {"source_code": code, "language_id": LANG_IDS[language], "stdin": stdin}
    resp = requests.post(
        f"{JUDGE0_URL}?base64_encoded=false&wait=true", json=payload, headers=headers, timeout=15
    )
    resp.raise_for_status()
    return (resp.json().get("stdout") or "").strip()


def grade_coding(code: str, language: str, test_cases: list[dict]) -> list[bool]:
    results = []
    for tc in test_cases:
        output = run_code_judge0(code, language, tc["input"])
        results.append(output == tc["expected"].strip())
    return results


def grade_aptitude(selected_index: int, correct_index: int) -> bool:
    return selected_index == correct_index


def grade_debug(fixed_code: str, language: str, test_cases: list[dict]) -> list[bool]:
    return grade_coding(fixed_code, language, test_cases)


def grade(problem_type: str, **kwargs):
    """Single entry point - app.py calls grade(problem_type, ...) and
    doesn't need to know which grading path runs underneath."""
    dispatch = {
        "coding": grade_coding,
        "aptitude": grade_aptitude,
        "debug": grade_debug,
        "logic": lambda **kw: None,  # no deterministic check - AI judge only
    }
    return dispatch[problem_type](**kwargs)
