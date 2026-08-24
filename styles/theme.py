"""
Phase 1 (+ UI/UX pass): design system CSS.
Flat diagonal fight-card theme - no gradients/glow, hard color blocks.
Injected once at the top of app.py via st.markdown(unsafe_allow_html=True).

This pass extends the original fight-card language (diagonal split panels,
JetBrains Mono for data/labels, Inter for prose, hard edges, no
border-radius, no gradients) to the rest of the app - forms, buttons,
verdict screen, leaderboard, and the "waiting/judging" busy states -
so the whole app reads as one designed surface instead of a styled hero
sitting on top of default Streamlit chrome everywhere else.

Two button "kinds" now carry real meaning, matching how Streamlit renders
them (data-testid="baseButton-primary" / "baseButton-secondary"):
  - primary   -> the one committing action per screen (CREATE MATCH,
                 JOIN MATCH, SUBMIT FINAL, CONTINUE) - solid amber block.
  - secondary -> everything else (pill buttons, RUN SAMPLE TESTS, LEAVE)
                 - quiet outline/ghost style, doesn't compete for attention.
To use this, pass type="primary" on the handful of commit buttons in
app.py - see the notes sent alongside this file.
"""


def get_theme_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Inter:wght@400;500;600&display=swap');

    #MainMenu, footer, header {visibility: hidden;}

    .stApp {
        background-color: #141312;
        font-family: 'Inter', sans-serif;
        color: #E8ECF1;
    }

    h3, .cc-h3 {
        font-family: 'JetBrains Mono', monospace !important;
        letter-spacing: 0.5px;
        text-transform: uppercase;
        font-size: 15px !important;
    }

    /* ===================================================================
       Buttons - two kinds. "Pill" (secondary / inside columns, e.g. the
       type/language selectors) stays as-is. "Primary" is the one
       committing action on a screen and now reads as a real CTA block,
       matching the amber used in the VS badge.
       =================================================================== */

    div[data-testid="column"] button[data-testid="baseButton-secondary"],
    button[data-testid="baseButton-secondary"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
        font-weight: 500 !important;
        border-radius: 0 !important;
        border: 1px solid #3A3936 !important;
        background: #2C2C2A !important;
        color: #B4B2A9 !important;
        padding: 8px 14px !important;
        letter-spacing: 0.5px;
        transition: background 0.12s ease, color 0.12s ease, border-color 0.12s ease;
    }
    div[data-testid="column"] button[data-testid="baseButton-secondary"]:hover,
    button[data-testid="baseButton-secondary"]:hover {
        background: #444441 !important;
        color: #E8ECF1 !important;
        border-color: #5A5954 !important;
    }

    button[data-testid="baseButton-primary"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 13px !important;
        font-weight: 700 !important;
        border-radius: 0 !important;
        border: none !important;
        background: #FAC775 !important;
        color: #412402 !important;
        padding: 12px 20px !important;
        letter-spacing: 1px;
        text-transform: uppercase;
        transition: background 0.12s ease, transform 0.05s ease;
    }
    button[data-testid="baseButton-primary"]:hover {
        background: #FFD98F !important;
    }
    button[data-testid="baseButton-primary"]:active {
        transform: translateY(1px);
    }

    /* ===================================================================
       Fight card (unchanged from Phase 1)
       =================================================================== */

    .cc-card {
        position: relative;
        height: 240px;
        margin: 20px 0;
    }
    .cc-panel-a {
        position: absolute; inset: 0;
        background: #085041;
        clip-path: polygon(0 0, 58% 0, 42% 100%, 0 100%);
        padding: 20px; box-sizing: border-box; color: #E1F5EE;
    }
    .cc-panel-b {
        position: absolute; inset: 0;
        background: #791F1F;
        clip-path: polygon(58% 0, 100% 0, 100% 100%, 42% 100%);
        padding: 20px; box-sizing: border-box; color: #FCEBEB; text-align: right;
    }
    .cc-vs {
        position: absolute; top: 50%; left: 50%;
        transform: translate(-50%, -50%);
        background: #FAC775; color: #412402;
        font-weight: 500; font-size: 14px;
        padding: 8px 14px; letter-spacing: 1px;
        font-family: 'JetBrains Mono', monospace;
    }
    .cc-vs.cc-pulse {
        animation: cc-badge-pulse 1.6s ease-in-out infinite;
    }
    .cc-name {
        font-size: 22px; font-weight: 500; text-transform: uppercase;
        letter-spacing: 0.5px; line-height: 1.1;
    }
    .cc-rating {
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px; margin: 2px 0 14px;
    }
    .cc-testbar {
        display: flex; gap: 3px; margin-bottom: 14px;
    }
    .cc-testbar-b { flex-direction: row-reverse; }
    .cc-seg {
        height: 8px; flex: 1;
    }
    .cc-code {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px; line-height: 1.6;
    }
    .cc-judge {
        margin-top: 14px; background: #1E1D1B;
        padding: 12px 16px; border-left: 3px solid #FAC775;
    }
    .cc-judge-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: #888780; letter-spacing: 1px; margin-bottom: 4px;
    }

    /* ===================================================================
       Round progress rail - segmented bar for "Round N of M", same flat
       block language as the testbar segments in the fight card.
       =================================================================== */

    .cc-rail-wrap {
        display: flex; align-items: center; gap: 10px;
        margin: 4px 0 18px;
    }
    .cc-rail-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 11px; color: #888780; letter-spacing: 1px;
        white-space: nowrap;
    }
    .cc-rail {
        display: flex; gap: 3px; flex: 1;
    }
    .cc-rail-seg {
        height: 6px; flex: 1; background: #2C2C2A;
    }
    .cc-rail-seg.cc-rail-done { background: #FAC775; }
    .cc-rail-seg.cc-rail-current { background: #5A5954; animation: cc-badge-pulse 1.6s ease-in-out infinite; }

    /* ===================================================================
       Connecting animation - waiting-for-opponent screen. Blinking
       terminal cursor + a scanning row of blocks that pulse amber in
       sequence (staggered animation-delay per segment set inline).
       =================================================================== */

    .cc-connecting {
        margin: 28px 0 8px;
    }
    .cc-connecting-row {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 12px;
    }
    .cc-connecting-label {
        font-family: 'JetBrains Mono', monospace;
        font-size: 13px;
        color: #FAC775;
        letter-spacing: 1.5px;
        text-transform: uppercase;
    }
    .cc-connecting-cursor {
        display: inline-block;
        width: 8px;
        height: 14px;
        background: #FAC775;
        animation: cc-cursor-blink 0.9s steps(1) infinite;
    }
    .cc-scan {
        display: flex;
        gap: 3px;
        max-width: 340px;
    }
    .cc-scan-seg {
        height: 5px;
        flex: 1;
        background: #2C2C2A;
        animation: cc-scan-light 1.8s ease-in-out infinite;
    }

    @keyframes cc-cursor-blink {
        0%, 49% { opacity: 1; }
        50%, 100% { opacity: 0; }
    }
    @keyframes cc-scan-light {
        0%, 100% { background: #2C2C2A; }
        50% { background: #FAC775; }
    }

    /* ===================================================================
       Busy / waiting states - a quiet breathing glow instead of a
       generic spinner, used behind "waiting for opponent / generating /
       judging" info boxes so the app still feels alive while it waits.
       =================================================================== */

    div[data-testid="stAlert"] {
        border-radius: 0 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 12px !important;
        letter-spacing: 0.3px;
        border: 1px solid #3A3936 !important;
        background: #1E1D1B !important;
    }
    div[data-testid="stAlert"]:has(svg) {
        animation: cc-alert-breathe 2s ease-in-out infinite;
    }

    @keyframes cc-badge-pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.55; }
    }
    @keyframes cc-alert-breathe {
        0%, 100% { border-color: #3A3936; }
        50% { border-color: #FAC775; }
    }
    @keyframes cc-slide-in {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* ===================================================================
       Verdict / round-result screen - same diagonal-split DNA as the
       fight card, so winning a round visually rhymes with the matchup
       card instead of dropping into a plain white Streamlit box.
       =================================================================== */

    .cc-verdict {
        animation: cc-slide-in 0.25s ease-out;
        margin: 10px 0 4px;
    }
    .cc-verdict-line {
        font-family: 'Inter', sans-serif;
        font-size: 14px; color: #C9C7BE;
        padding: 14px 16px; background: #1E1D1B;
        border-left: 3px solid #FAC775;
        margin-bottom: 14px;
    }
    .cc-verdict-grid {
        display: flex; gap: 3px;
    }
    .cc-verdict-side {
        flex: 1; padding: 16px; box-sizing: border-box;
    }
    .cc-verdict-a { background: #085041; color: #E1F5EE; }
    .cc-verdict-b { background: #791F1F; color: #FCEBEB; text-align: right; }
    .cc-verdict-name {
        font-family: 'JetBrains Mono', monospace;
        font-size: 12px; letter-spacing: 1px; text-transform: uppercase;
        opacity: 0.85; margin-bottom: 6px;
    }
    .cc-verdict-score {
        font-family: 'JetBrains Mono', monospace;
        font-size: 30px; font-weight: 700; line-height: 1;
    }
    .cc-verdict-meta {
        font-family: 'JetBrains Mono', monospace;
        font-size: 10px; color: currentColor; opacity: 0.7; margin-top: 8px;
    }

    /* ===================================================================
       Leaderboard - monospace ranked list instead of the default grey
       dataframe grid, rank 1 gets the amber treatment.
       =================================================================== */

    div[data-testid="stDataFrame"] {
        border: 1px solid #3A3936 !important;
    }
    div[data-testid="stDataFrame"] * {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 12px !important;
    }

    /* ===================================================================
       Inputs - text fields / textareas (code editor) get the same flat,
       hard-edged, dark-panel treatment as everything else.
       =================================================================== */

    div[data-testid="stTextInput"] input,
    div[data-testid="stTextArea"] textarea {
        background: #1E1D1B !important;
        color: #E8ECF1 !important;
        border: 1px solid #3A3936 !important;
        border-radius: 0 !important;
        font-family: 'JetBrains Mono', monospace !important;
    }
    div[data-testid="stTextArea"] textarea {
        font-size: 13px !important;
        line-height: 1.6 !important;
    }
    div[data-testid="stTextInput"] input:focus,
    div[data-testid="stTextArea"] textarea:focus {
        border-color: #FAC775 !important;
        box-shadow: none !important;
    }

    /* radio (aptitude answers) */
    div[data-testid="stRadio"] label {
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
    }

    /* tabs (CREATE / JOIN / LEADERBOARD) */
    button[data-baseweb="tab"] {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 12px !important;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }

    /* match code chip on the match screen */
    code {
        background: #1E1D1B !important;
        color: #FAC775 !important;
        border: 1px solid #3A3936;
        font-family: 'JetBrains Mono', monospace !important;
    }

    hr { border-color: #2C2C2A !important; }
    </style>
    """