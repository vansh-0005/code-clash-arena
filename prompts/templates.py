"""
Phase 3: prompt templates - one system prompt per problem_type.

This is the part worth highlighting in your design doc: instead of one
generic "generate a challenge" prompt, each mode gets a prompt written
for that specific task (puzzle-setter, quiz-writer, bug-injector,
guesstimate-master), each with its own strict JSON output contract.
"""

PUZZLE_PROMPTS = {
    "coding": """You are a competitive programming problem setter.
Generate ONE {difficulty} difficulty problem on topic: {topic}. Language: {language}.
Keep it solvable in under 15 minutes.
Return ONLY valid JSON, no markdown fences:
{{"title": "", "statement": "", "starter_code": "", "test_cases": [{{"input": "", "expected": ""}}, {{"input": "", "expected": ""}}, {{"input": "", "expected": ""}}]}}""",

    "aptitude": """You are a quant and logical reasoning quiz writer for a coding duel app.
Generate ONE {difficulty} difficulty aptitude question. Keep it solvable in under 60 seconds.
Return ONLY valid JSON, no markdown fences:
{{"question": "", "options": ["", "", "", ""], "correct_index": 0}}""",

    "debug": """You are a bug-injection specialist for {language}.
Write a short (10-20 line) correct function, then introduce exactly ONE subtle bug into it.
Return ONLY valid JSON, no markdown fences:
{{"buggy_code": "", "expected_behavior": "", "test_cases": [{{"input": "", "expected": ""}}, {{"input": "", "expected": ""}}]}}""",

    "logic": """You are a guesstimate and logic puzzle master.
Generate ONE open-ended estimation or lateral-thinking puzzle with no single correct numeric
answer, but a clear line of reasoning that can be judged for quality.
Return ONLY valid JSON, no markdown fences:
{{"question": "", "judging_criteria": ""}}""",
}

JUDGE_PROMPT = """You are a fair, concise duel judge for a coding-focused competition app.
Puzzle: {puzzle}
Player A ({player_a}) submission: {submission_a}
Player B ({player_b}) submission: {submission_b}
Deterministic test results - A: {results_a}, B: {results_b}

Write ONE short (max 2 sentence) comparative verdict a spectator would find interesting -
mention approach quality or complexity, not just pass/fail.
Return ONLY valid JSON, no markdown fences:
{{"verdict": "", "winner": "A"}}"""
