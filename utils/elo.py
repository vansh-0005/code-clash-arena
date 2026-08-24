"""
Phase 5: Elo rating update after each match, plus a leaderboard read helper.
"""

K = 32


def expected_score(rating_a: int, rating_b: int) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(rating_a: int, rating_b: int, score_a: float) -> tuple[int, int]:
    """score_a: 1 = A won, 0.5 = tie, 0 = A lost."""
    exp_a = expected_score(rating_a, rating_b)
    exp_b = 1 - exp_a
    new_a = round(rating_a + K * (score_a - exp_a))
    new_b = round(rating_b + K * ((1 - score_a) - exp_b))
    return new_a, new_b


def get_leaderboard(db_module) -> list[dict]:
    """Pulls all players from Firebase (utils/db.py's /players node),
    sorted by rating desc. db_module is the utils.db module itself, passed
    in so this file doesn't need its own Firebase import - matches the
    pattern of the rest of the app treating db.py as the only Firebase
    touchpoint."""
    players = db_module.list_players()
    return sorted(players, key=lambda p: p.get("rating", 1000), reverse=True)