"""
Phase 4: grading dispatch.

Each problem_type routes to its own grading strategy:
- coding / debug -> deterministic (JDoodle executes real code against test cases)
- aptitude       -> deterministic (exact match, no AI needed, instant)
- logic          -> AI-judged only (no ground truth exists to check against)

Uses JDoodle's Compiler API (free tier, no per-call billing) instead of
Judge0/RapidAPI - Judge0's RapidAPI "Basic" plan is pay-per-use
($0.0017/call), not actually free, and Piston's public API went
whitelist-only in Feb 2026. JDoodle's free daily credit allocation is a
genuine $0 tier. Sign up at jdoodle.com -> Dashboard -> API to get your
clientId/clientSecret (no card required), then add both to secrets.toml:
    jdoodle_client_id = "..."
    jdoodle_client_secret = "..."

This is the "hybrid grading" piece: JDoodle gives the hard correctness
signal (plus real runtime/memory, like LeetCode's per-submission stats),
Gemini's judge_submissions() (see utils/gemini.py) adds the qualitative
layer on top - approach quality, complexity, style, per-line reasoning.
"""

import requests
import streamlit as st

JDOODLE_URL = "https://api.jdoodle.com/v1/execute"

# language code + versionIndex per JDoodle's supported-languages table -
# picked stable, well-established versions rather than bleeding-edge ones.
LANG_CONFIG = {
    "PY": {"language": "python3", "versionIndex": "5"},   # Python 3.11.5
    "C++": {"language": "cpp17", "versionIndex": "2"},    # g++17 GCC 13.2.1
    "JAVA": {"language": "java", "versionIndex": "4"},    # JDK 17.0.1
    "JS": {"language": "nodejs", "versionIndex": "5"},    # Node 20.9.0
}


def run_code_jdoodle(code: str, language: str, stdin: str) -> dict:
    """Returns the full execution result, not just stdout - JDoodle also
    reports cpuTime and memory per run, which is what powers the
    LeetCode-style 'Runtime: Xms, Memory: YKB' display."""
    if language not in LANG_CONFIG:
        raise ValueError(f"Unsupported language: {language!r}")

    payload = {
        "clientId": st.secrets["jdoodle_client_id"],
        "clientSecret": st.secrets["jdoodle_client_secret"],
        "script": code,
        "stdin": stdin,
        **LANG_CONFIG[language],
    }
    resp = requests.post(JDOODLE_URL, json=payload, timeout=15)
    resp.raise_for_status()
    body = resp.json()

    if body.get("statusCode") == 429:
        raise RuntimeError("JDoodle daily free-tier credit limit reached - try again tomorrow.")

    output = (body.get("output") or "").strip()
    is_compiled = body.get("isCompiled", True)
    is_success = body.get("isExecutionSuccess", True)

    return {
        "stdout": output if is_success else "",
        "stderr": "" if is_success else output,  # JDoodle puts compile/runtime errors in "output" too
        "compile_output": output if not is_compiled else "",
        "status": "Accepted" if (is_compiled and is_success) else "Error",
        "time_sec": float(body["cpuTime"]) if body.get("cpuTime") else None,
        "memory_kb": body.get("memory"),
    }


def run_sample_tests(code: str, language: str, test_cases: list[dict]) -> list[dict]:
    """Runs code against a SMALL set of sample test cases (the ones shown
    to the player in the puzzle statement) so they can check their work
    before final submission - a 'Run' button distinct from 'Submit', same
    idea as LeetCode. Returns one result dict per test case."""
    results = []
    for tc in test_cases:
        run = run_code_jdoodle(code, language, tc["input"])
        passed = run["stdout"] == tc["expected"].strip()
        results.append({**run, "passed": passed, "expected": tc["expected"], "input": tc["input"]})
    return results


def grade_coding(code: str, language: str, test_cases: list[dict]) -> list[dict]:
    """Full grading against ALL test cases (sample + hidden), used for the
    final submission, not the pre-submit sample-test 'Run'."""
    return run_sample_tests(code, language, test_cases)


def grade_aptitude(selected_index: int, correct_index: int) -> list[dict]:
    return [{"passed": selected_index == correct_index}]


def grade_debug(fixed_code: str, language: str, test_cases: list[dict]) -> list[dict]:
    return grade_coding(fixed_code, language, test_cases)


def grade(problem_type: str, **kwargs) -> list[dict]:
    """Single entry point - app.py calls grade(problem_type, ...) and
    doesn't need to know which grading path runs underneath. Always
    returns a list of {"passed": bool, ...} dicts so app.py's scoring
    logic (test pass ratio) doesn't need to special-case problem_type."""
    dispatch = {
        "coding": grade_coding,
        "aptitude": grade_aptitude,
        "debug": grade_debug,
        "logic": lambda **kw: [],  # no deterministic check - AI judge only
    }
    return dispatch[problem_type](**kwargs)


def pass_ratio(results: list[dict]) -> float:
    """0.0-1.0 fraction of test cases passed."""
    if not results:
        return 0.0
    return sum(1 for r in results if r.get("passed")) / len(results)