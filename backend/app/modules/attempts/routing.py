
from decimal import Decimal, ROUND_HALF_UP

# Defaults. Each test can override these per-module in the DB later.
DEFAULT_THRESHOLD     = Decimal("0.65")
DEFAULT_WEIGHT_EASY   = 1
DEFAULT_WEIGHT_MEDIUM = 2
DEFAULT_WEIGHT_HARD   = 3

ALGORITHM_VERSION = "weighted_v1"


def compute_weighted_score(
    correct_easy, correct_medium, correct_hard,
    total_easy,   total_medium,   total_hard,
    weight_easy   = DEFAULT_WEIGHT_EASY,
    weight_medium = DEFAULT_WEIGHT_MEDIUM,
    weight_hard   = DEFAULT_WEIGHT_HARD,
):
   
    numerator = (
        correct_easy   * weight_easy +
        correct_medium * weight_medium +
        correct_hard   * weight_hard
    )
    denominator = (
        total_easy     * weight_easy +
        total_medium   * weight_medium +
        total_hard     * weight_hard
    )

    if denominator == 0:
        return Decimal("0.0000")

    return (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP
    )


def decide_level(weighted_score, threshold=DEFAULT_THRESHOLD):
    """
    Hard if score >= threshold, else easy.
    """
    return "hard" if weighted_score >= threshold else "easy"


def route(correct_easy, correct_medium, correct_hard,
          total_easy,   total_medium,   total_hard,
          threshold    = DEFAULT_THRESHOLD,
          weight_easy  = DEFAULT_WEIGHT_EASY,
          weight_medium= DEFAULT_WEIGHT_MEDIUM,
          weight_hard  = DEFAULT_WEIGHT_HARD):
   
    score = compute_weighted_score(
        correct_easy, correct_medium, correct_hard,
        total_easy,   total_medium,   total_hard,
        weight_easy, weight_medium, weight_hard,
    )
    return {
        "weighted_score": score,
        "threshold": threshold,
        "chosen_level": decide_level(score, threshold),
        "algorithm_version": ALGORITHM_VERSION,
    }