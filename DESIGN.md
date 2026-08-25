# Technical Design Document — Code Clash Arena

## 1. Problem statement

Build a live 1v1 coding duel platform in Streamlit — a framework with no
native concept of shared, real-time, multi-user state. Two people load the
same app independently; the platform has to make them feel like they're in
the same room.

## 2. Data flow

```
create/join → both players present → puzzle generation (batched, once)
  → both submit → deterministic grading (JDoodle/exact-match)
  → AI judging (Gemini, skipped for aptitude) → verdict shown
  → CONTINUE → next round (instant, pre-generated) → ... → match_over
  → Elo applied once → complete
```

Every arrow above is a state transition written to a single Firebase
Realtime Database row (`/matches/{match_id}`), and every transition is
driven by whichever browser tab's poll happens to observe the precondition
first. There is no server process coordinating this — the "server" is
Firebase itself, and coordination happens entirely through atomic
transactions on that shared row.

## 3. API integration strategy

### 3.1 Gemini (puzzle generation, judging, voice transcription)

One system prompt per problem type (`prompts/templates.py`) rather than a
single generic prompt — a puzzle-setter voice for coding, a quiz-writer
voice for aptitude, a bug-injector voice for debug, a guesstimate-master
voice for logic. Each returns a strict JSON contract, parsed directly (no
regex scraping of free text).

**Aptitude is deliberately NOT AI-judged.** There's nothing qualitative to
judge in a multiple-choice answer — it's either right or wrong. Routing it
through Gemini anyway would waste a call and risk the model returning an
out-of-range "quality score" for a format it was never meant to score.

**Duplicate-question defense**: rather than trust a "please don't repeat
yourself" instruction (LLMs are unreliable at honoring that, especially in
narrow domains like aptitude math where there are only so many classic
templates), generated questions are checked with `difflib` text similarity
against every prior question in the same match. A detected duplicate
triggers a retry with an explicit forcing constraint ("base it on a sports
scenario"), up to 3 attempts before falling back to the pre-baked pool.

**Model selection**: hardcoded in `utils/gemini.py` (`MODEL_NAME`). Free-tier
model availability on Gemini has been volatile — `list_models.py` is
included specifically so this can be re-verified against your own API key
rather than assumed from documentation that may be stale.

### 3.2 JDoodle (code execution)

Originally speced against Judge0 (RapidAPI). Switched to JDoodle after
discovering Judge0's RapidAPI "Basic" plan is pay-per-use ($0.0017/call),
not a genuine free tier — JDoodle's daily free credit allocation is
actually $0. This is documented here specifically because it's the kind
of infrastructure decision that's easy to get wrong by trusting a
provider's marketing rather than their actual pricing page.

Real execution (not `exec()`) across 4 languages, returning real
`cpuTime`/`memory` per run — this is what makes "Run sample tests" /
"Submit" feel like an actual judge rather than a toy string-compare.

### 3.3 Hybrid grading formula

- **Coding / Debug**: binary marks. `1` if 100% of test cases pass, else
  `0`. If both players score identically (both solved, or both failed),
  Gemini's quality/complexity read on the actual code breaks the tie for
  round-winner purposes — but the displayed *marks* are always clean
  integers, never a blended fraction.
- **Aptitude**: `1`/`0` exact match against `correct_index`. No AI
  involvement at all.
- **Logic**: 100% AI-judged (0–10 quality score, normalized to 0–1) —
  there's no ground truth to check against for an open-ended estimation
  question.

## 4. Concurrency & race-condition handling

Three operations must happen exactly once per match/round despite two
independent browser sessions polling the same state:

1. Puzzle generation (all rounds, batched, at match start)
2. Judging (once both players submit a round)
3. Rating application (once, after the final round)

All three use the same pattern: a Firebase `.transaction()` on a
`{operation}_claimed_by` field, where the transaction function returns the
existing value if already claimed (no-op) or the caller's name if free.
Exactly one of two concurrent callers gets back their own name; that's the
winner. A parallel `{operation}_claimed_at` timestamp lets any session
detect and release a stale claim (crashed mid-call) so a single dropped
connection can't permanently deadlock a match.

A second, distinct concurrency issue: `st_autorefresh`'s timer runs on
wall-clock time, independent of what the Python script is doing. A slow
Gemini/JDoodle call can get interrupted mid-flight by the next poll tick,
which Streamlit treats as a script cancellation — not a catchable
exception — silently dropping the result write. The fix is a two-phase
pattern used for every slow call: phase 1 sets a `st.session_state` busy
flag and reruns immediately (no slow work yet); phase 2, on the next run,
sees the flag, has already benefited from the slowed poll interval that
flag triggers, and only now performs the actual slow call.

## 5. Known limitations (see README.md for the full list)

- Name-based identity only, no authentication.
- Firebase's whole-tree reads for analytics (`get_all_matches`) are fine
  at classroom scale; a production version would need pagination or a
  secondary index.
- Hardcoded model names for both Gemini and JDoodle's language versions —
  external providers changing their lineup requires a manual update.

## 6. Why this rubric-maps the way it does

| Category | Where to look |
|---|---|
| Technical Implementation | `utils/db.py` (claim/transaction patterns), `app.py` two-phase busy-flag pattern |
| AI Integration | `prompts/templates.py` (per-type prompts), `utils/gemini.py` (duplicate defense, voice transcription) |
| UI/UX & Data Viz | `app.py` analytics tab (Pandas + `st.data_editor`/`st.map`/`st.metric`), sidebar dashboard shell |
| Deployment | `requirements.txt` (pure-Python, no system deps), Streamlit Community Cloud |
| Open-Source Branding | this repo's `README.md` |
| System Design | this document + `ARCHITECTURE.md` |
