"""
Phase 1: design system CSS.
Flat diagonal fight-card theme - no gradients/glow, hard color blocks.
Injected once at the top of app.py via st.markdown(unsafe_allow_html=True).
"""


def get_theme_css() -> str:
    return """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500&family=Inter:wght@400;500&display=swap');

    #MainMenu, footer, header {visibility: hidden;}

    .stApp {
        background-color: #141312;
        font-family: 'Inter', sans-serif;
        color: #E8ECF1;
    }

    /* language / problem-type pill buttons */
    div[data-testid="column"] button {
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 11px !important;
        font-weight: 500 !important;
        border-radius: 0 !important;
        border: none !important;
        background: #2C2C2A !important;
        color: #B4B2A9 !important;
        padding: 4px 10px !important;
    }
    div[data-testid="column"] button:hover {
        background: #444441 !important;
        color: #E8ECF1 !important;
    }

    /* fight card */
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
    </style>
    """
