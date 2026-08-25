```
   _____          _        _____ _           _        ___
  / ____|        | |      / ____| |         | |      / _ \
 | |     ___   __| | ___ | |    | | __ _ ___| |__   | |_| |_ __ ___ _ __   __ _
 | |    / _ \ / _` |/ _ \| |    | |/ _` / __| '_ \  |  _  | '__/ _ \ '_ \ / _` |
 | |___| (_) | (_| |  __/| |____| | (_| \__ \ | | | | | | | | |  __/ | | | (_| |
  \_____\___/ \__,_|\___(_)_____|_|\__,_|___/_| |_| |_| |_|_|  \___|_| |_|\__,_|

  a live 1v1 coding duel platform  //  built for MirAI School of Technology
```

$ `cat about.txt`

Code Clash Arena is a real-time, two-player coding duel app. Two people open
the same URL, get matched into a live session, and battle through AI-generated
puzzles — coding, aptitude, debugging, or open-ended logic — with hybrid
grading (real code execution + AI judgment) and an Elo rating system.

This is not a LeetCode clone with rated contests, and not another
single-form single-AI-call wrapper app. It's real shared state across two
independent, stateless Streamlit sessions — which is the hard part most
similar projects skip.

---

$ `cat features.txt`

- **4 problem types**, one prompt engineered per type (not one generic
  prompt): Coding, Aptitude (B.Tech placement-OA level — TCS NQT / Infosys /
  AMCAT difficulty, not school arithmetic), Debug, and open-ended Logic.
- **Best-of-N matches** (1–5 rounds), all puzzles for the whole match
  generated upfront in a single batch — no wait between rounds.
- **Hybrid grading**: real code execution via JDoodle (actual compile/run,
  not `exec()`), blended with Gemini's qualitative code-quality judgment.
  Coding/debug marks are clean `+1`/`0` (fully solved or not); quality only
  breaks a tie.
- **Multimodal input**: the Logic mode accepts typed answers *or* a mic
  recording, transcribed live via Gemini.
- **Persistent player profiles + Elo leaderboard**, with a rating-history
  chart per player.
- **Live analytics dashboard**: mode popularity, completion rate, recent
  matches — all via a real Pandas pipeline, not hand-rolled loops.
- **"Battle Origins" map** (`st.map`) — live players plotted by city.
- **Persistent sidebar** during a match: match code, fight card, and round
  progress always visible, main column stays focused on the puzzle.
- Toast notifications for live events (opponent joined, round result in).

---

$ `cat architecture.txt`

See `ARCHITECTURE.md` for the full diagram. Short version:

```
Browser Tab A ─┐                                    ┌─ Gemini API
               ├─→  Streamlit (app.py)  ─────────────┤  (puzzle gen + judging)
Browser Tab B ─┘         │                           └─ JDoodle API
                          │                              (code execution)
                          ▼
                 Firebase Realtime DB
              (the only way the two tabs
               "know" about each other)
```

Streamlit has no websockets and no cross-session memory — every browser tab
is a fully isolated script rerun. The two players only ever communicate by
reading and writing the same Firebase row, polled every few seconds.

---

$ `cat setup.sh`

```bash
git clone https://github.com/vansh-0005/code-clash-arena.git
cd code-clash-arena
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill
in three things (all free-tier, no credit card required for any of them):

| Service  | What you need                          | Where to get it |
|----------|-----------------------------------------|------------------|
| Firebase | Service account JSON + Realtime DB URL  | Firebase Console → Project Settings → Service Accounts |
| Gemini   | API key                                 | Google AI Studio |
| JDoodle  | Client ID + Client Secret               | jdoodle.com → Dashboard → API |

Run it:

```bash
streamlit run app.py
```

Open the URL in two separate browser tabs (or two devices) to actually play
a match — one tab alone will just sit on "Waiting for opponent."

---

$ `cat live.txt`

Live app: **https://code-clash-arena.streamlit.app**

---

$ `cat known_limitations.txt`

- **No authentication** — player identity is name-based only. Typing the
  same name pulls your real rating back; two different people using the
  same name share a profile. Fine for a classroom demo, not for production.
- **Judge0/RapidAPI is NOT used** — its "Basic" plan is pay-per-use, not
  actually free, so grading runs on JDoodle's free-credit tier instead.
- **Model names for Gemini/JDoodle are hardcoded** — if either provider
  changes their free-tier model lineup, `utils/gemini.py`'s `MODEL_NAME`
  may need updating (see `list_models.py` to check what's currently
  available to your API key).

---

$ `cat credits.txt`

Built by Vansh Sharma for the MirAI School of Technology B.Tech Capstone.
Stack: Streamlit, Firebase Realtime Database, Google Gemini API, JDoodle
Compiler API, Pandas.
