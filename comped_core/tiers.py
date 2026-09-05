"""The comp score, as a thing you can say out loud.

A multiplier is a number; a tier is a boast. The bands are fixed and the copy is the same on
the card, in the share text and on the site, so a score means the same thing wherever it is
quoted. Below 1x is the only band that is not a compliment.
"""
from decimal import Decimal
from typing import Optional

# (upper bound exclusive, name, one line). Order matters.
TIERS = [
    (Decimal("1"), "Paying customer", "The API would have been cheaper. Either you barely used it, or you should be on pay-as-you-go."),
    (Decimal("2"), "Break-even", "You're paying roughly what the tokens are worth."),
    (Decimal("5"), "Comped", "Comfortably ahead. The plan is doing its job."),
    (Decimal("12"), "Properly comped", "This is the part where you tell your team."),
    (Decimal("30"), "All-you-can-eat", "The subscription is less a purchase than a hostage situation, and you are not the hostage."),
    (Decimal("80"), "Hostage situation", "Someone in a pricing meeting is going to see this and go very quiet."),
    (None, "Please stop", "There is nothing left to comp."),
]


def tier(multiplier: Optional[Decimal]) -> Optional[dict]:
    """The band a multiplier falls in, or None when there is no multiplier to grade."""
    if multiplier is None:
        return None
    for i, (upper, name, line) in enumerate(TIERS):
        if upper is None or multiplier < upper:
            return {"name": name, "line": line, "rank": i + 1, "of": len(TIERS)}
    return None


def score(multiplier: Optional[Decimal]) -> str:
    if multiplier is None:
        return "—"
    return "{0:.1f}×".format(multiplier) if multiplier < Decimal("10") else "{0:.0f}×".format(multiplier)
