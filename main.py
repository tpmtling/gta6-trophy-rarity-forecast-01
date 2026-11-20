"""GTA VI week-one trophy rarity forecast (make.fun gta6-trophy-rarity-forecast-01).

Model, in one paragraph: the case history is Exophase's trophy page read on a
clock, so long runs of identical reads are one stale page, not new evidence.
We first compress each trophy's series to its change points (the reads where
the page actually moved), then fit a recency-weighted straight line to the
logit of the earn rate against ln(1 + hours since release) -- the same clock
the house curve baseline uses, but on change points only and with the
extrapolation damped and capped per trophy category. The median is the last
rate moved by that damped trend plus a small category drift (platinum, 100%
completion and grind trophies dilute as the tracked-player denominator keeps
growing; story trophies are allowed to climb as the launch cohort progresses).
The spread is a per-trophy random walk on the logit scale whose daily
volatility is estimated from the trophy's own change-point jumps, shrunk
toward the house baseline's 0.5 logit per root-day, and widened when the
fitted trend is large. Everything is deterministic: no randomness, no clock,
no network, standard library only.

Why these shapes (checked against earlier Rockstar launches): in GTA V only
about 29% of players ever unlock the final-mission trophy and the platinum
sits between 0.1% (all PSN players) and about 5% (PSNProfiles' hunter-skewed
owners) even years later; RDR2's platinum is around 0.1-0.6% while its first
bronze sits above 75%. So in week one: early story trophies can be high, the
ending is far below its long-run level, and platinum / 100% / grind trophies
stay near zero and mostly dilute as new players are tracked.
"""

import calendar
import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))

LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# 2026-11-19T00:00:00Z, the release-day anchor the trend clock runs from.
RELEASE_EPOCH = calendar.timegm((2026, 11, 19, 0, 0, 0, 0, 0, 0))

# Fallback medians (percent) for a trophy no read has ever listed a rate for.
TIER_PRIOR = {"platinum": 0.05, "gold": 0.8, "silver": 1.5, "bronze": 4.0}

GRIND_WORDS = (
    "250", "every ", "all ", "100 locations", "100 vehicles",
    "50 challenges", "20 different", "collectible", "purchase all",
    "explore all", "$250,000", "$100,000", "10 vehicles", "gold medal",
)


def clamp_pct(x):
    return min(99.99, max(0.01, x))


def logit(pct):
    p = clamp_pct(pct)
    return math.log(p / (100.0 - p))


def pct_from_logit(lg):
    if lg >= 0:
        return 100.0 / (1.0 + math.exp(-lg))
    e = math.exp(lg)
    return 100.0 * e / (1.0 + e)


def round4(x):
    scaled = x * 10000
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 10000
    return int(value) if float(value).is_integer() else value


def parse_hours(text):
    # "2026-11-19T03:00:00Z" (fractional seconds allowed) -> hours since
    # the release anchor.
    date, _, time = text.partition("T")
    year, month, day = (int(part) for part in date.split("-"))
    time = time.rstrip("Z").split(".")[0]
    hour, minute, second = (int(part) for part in time.split(":"))
    epoch = calendar.timegm((year, month, day, hour, minute, second, 0, 0, 0))
    return (epoch - RELEASE_EPOCH) / 3600.0


def classify(trophy):
    desc = trophy["description"].lower()
    if trophy["tier"] == "platinum":
        return "platinum"
    if "100% completion" in desc:
        return "hundred"
    if desc.startswith("complete chapter"):
        return "chapter"
    if desc == "complete the final mission.":
        return "story_final"
    if "final mission for" in desc:
        return "side_final"
    if any(word in desc for word in GRIND_WORDS):
        return "grind"
    if trophy.get("secret") and desc.startswith("complete "):
        return "story"
    return "activity"


# Per-category guardrails: how far the damped trend may move the median on
# the logit scale, and a small drift per forecast day (denominator dilution
# for the grind categories, progression for story ones).
CATEGORY_RULES = {
    "platinum": (-1.6, 0.35, -0.050),
    "hundred": (-1.6, 0.35, -0.045),
    "grind": (-1.5, 0.45, -0.030),
    "chapter": (-1.4, 1.10, 0.010),
    "story": (-1.5, 0.90, 0.005),
    "story_final": (-1.5, 0.90, 0.005),
    "side_final": (-1.5, 0.70, 0.0),
    "activity": (-1.5, 0.70, 0.0),
}


def change_points(history, idx):
    """(hours, players, rate) rows where this trophy's page actually moved."""
    points = []
    for read in history:
        rate = read["rates"][idx]
        if rate is None:
            continue
        row = (parse_hours(read["at"]), read.get("players_tracked"), rate)
        if points and points[-1][1] == row[1] and points[-1][2] == row[2]:
            points[-1] = row  # same page, later read: keep the fresher stamp
            continue
        points.append(row)
    return points


def weighted_fit(xs, ys, ws):
    """Least-squares y = a + b*x with weights; returns (a, b)."""
    total = sum(ws)
    mx = sum(w * x for x, w in zip(xs, ws)) / total
    my = sum(w * y for y, w in zip(ys, ws)) / total
    sxx = sum(w * (x - mx) ** 2 for x, w in zip(xs, ws))
    if sxx <= 1e-12:
        return my, 0.0
    sxy = sum(w * (x - mx) * (y - my) for x, y, w in zip(xs, ys, ws))
    b = sxy / sxx
    return my - b * mx, b


def daily_volatility(points, slope_per_x=0.0):
    """Logit random-walk volatility per root-day from change-point jumps.

    Jumps are detrended by the fitted slope first: a trophy climbing a
    steady trend is predictable, not volatile, and should not pay for a
    wide band twice (once in the moved median, once in the spread).
    """
    jumps = []
    for (t0, _, r0), (t1, _, r1) in zip(points, points[1:]):
        dt_days = (t1 - t0) / 24.0
        if dt_days < 0.02:
            continue
        expected = slope_per_x * (math.log1p(max(0.0, t1)) - math.log1p(max(0.0, t0)))
        jumps.append((logit(r1) - logit(r0) - expected) ** 2 / dt_days)
    if not jumps:
        return 0.55
    jumps.sort()
    median_var = jumps[len(jumps) // 2]
    # Shrink the trophy's own estimate toward the 0.55 prior (4 pseudo-jumps).
    var = (len(jumps) * median_var + 4 * 0.55 ** 2) / (len(jumps) + 4)
    return min(1.35, max(0.30, math.sqrt(var)))


def forecast_trophy(trophy, history, idx, horizon_days, target_hours):
    category = classify(trophy)
    fall_cap, rise_cap, drift_per_day = CATEGORY_RULES[category]
    points = change_points(history, idx)
    if not points:
        median = TIER_PRIOR.get(trophy["tier"], 1.0)
        sigma = 0.62 * math.sqrt(horizon_days) + 0.35
        return [round4(pct_from_logit(logit(median) + z * sigma)) for z in Z]

    last_hours, _, last_rate = points[-1]
    last_logit = logit(last_rate)

    # Damped trend: recency-weighted fit of logit(rate) on ln(1 + hours).
    # The damping trusts the fit less the further past the observed span the
    # target sits: extrapolating 4.5 days from 2 days of refreshes is not the
    # same bet as extrapolating 90 minutes from 3 hours of them.
    delta = 0.0
    slope_per_x = 0.0
    if len(points) >= 3:
        xs = [math.log1p(max(0.0, t)) for t, _, _ in points]
        ys = [logit(r) for _, _, r in points]
        ws = [0.5 ** ((last_hours - t) / 36.0) for t, _, _ in points]
        a, b = weighted_fit(xs, ys, ws)
        slope_per_x = b
        x_target = math.log1p(max(0.0, target_hours))
        trend_at_target = a + b * x_target
        span = max(0.05, xs[-1] - xs[0])
        extra = max(0.0, x_target - xs[-1])
        damp = 0.30 + 0.55 * span / (span + extra)
        delta = damp * (trend_at_target - last_logit)
        delta = min(rise_cap, max(fall_cap, delta))

    median_logit = last_logit + delta + drift_per_day * horizon_days
    # A rate hugging the ceiling can only be diluted by new tracked players.
    if last_rate > 90.0:
        median_logit -= 0.08 * horizon_days * (last_rate - 90.0) / 10.0
    median_logit = min(logit(99.5), max(logit(0.01), median_logit))

    vol = daily_volatility(points, slope_per_x)
    sigma = vol * math.sqrt(horizon_days)
    sigma += 0.22 * abs(delta)  # a big fitted trend is an uncertain one
    sigma = min(1.95, max(0.45 * math.sqrt(horizon_days) + 0.15, sigma))
    return [round4(pct_from_logit(median_logit + z * sigma)) for z in Z]


def forecast_case(case, name):
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    history = case["history"]
    horizon_days = case["horizon_minutes"] / 1440.0
    target_hours = parse_hours(case["target"])
    rows = []
    for idx, trophy in enumerate(case["trophies"]):
        q = forecast_trophy(trophy, history, idx, horizon_days, target_hours)
        rows.append({"id": trophy["id"], "q": q})
    return {"trophies": rows}


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(INPUT_DIR.glob("*.in")):
        case = json.loads(path.read_text(encoding="utf-8"))
        forecast = forecast_case(case, path.name)
        text = json.dumps(forecast, separators=(",", ":")) + "\n"
        (OUTPUT_DIR / f"{path.stem}.out").write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
