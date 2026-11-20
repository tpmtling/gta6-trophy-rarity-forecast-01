# gta6-trophy-rarity-forecast-01

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/tpmtling/gta6-trophy-rarity-forecast-01/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/tpmtling/gta6-trophy-rarity-forecast-01/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

A data-based forecast of GTA VI week-one trophy rarity. `main.py` (Python 3, standard library only) reads a case file of Exophase trophy-page reads and writes, for each of the game's 55 PS5 trophies, five quantiles (5/25/50/75/95%) of its earn rate at the case's target time. The model compresses each trophy's history to its change points (identical re-reads of a stale page are not new evidence), fits a recency-weighted line to the logit of the earn rate against ln(1 + hours since release), and extrapolates with damping that shrinks as the target moves further past the observed span. Medians are capped per trophy category — platinum, 100%-completion and grind trophies mostly dilute as the tracked-player denominator grows, while story trophies may climb as the launch cohort progresses — and the spread is a per-trophy logit random walk whose volatility is estimated from that trophy's own detrended change-point jumps, shrunk toward 0.55 logit per root-day. The shapes are anchored on earlier Rockstar launches: in GTA V only about 29% of players ever unlock the final-mission trophy and its platinum sits between 0.1% of all PSN players and roughly 5% of PSNProfiles' hunter-skewed owners years later, and RDR2's platinum is around 0.1–0.6% while its first bronze sits above 75% — so in week one the ending sits far below its long-run level and the platinum stays near zero. Output is deterministic: two runs on the same case are byte-identical.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=fpwjs2j2&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
