"""How much data BKT fitting needs: parameter recovery and held-out prediction, by sample size.

Simulated learners follow known parameters; EM (`engine.bkt_fit.fit`) estimates them back. For each
sample size and seed we record the absolute error per parameter and held-out log loss for the fitted
parameters, the literature defaults and the true parameters (the floor).

Usage, from apps/api:
    uv run python -m app.evalkit.bkt_fit_report --out ../../docs/v2/bkt-fit-eval.json
"""

import argparse
import json
import random
import statistics
import sys
from collections.abc import Sequence
from pathlib import Path

from app.engine.bkt import DEFAULT_PARAMS, BKTParams
from app.engine.bkt_fit import fit, score, simulate

TRUE = BKTParams(p_init=0.3, p_transit=0.15, p_slip=0.08, p_guess=0.2)
FIELDS = ("p_init", "p_transit", "p_slip", "p_guess")


def report(sizes: Sequence[int], seeds: int, length: int) -> dict[str, object]:
    held = simulate(TRUE, 2000, length, random.Random(10_000))
    floor = score(TRUE, held).log_loss
    default = score(DEFAULT_PARAMS["mcq"], held).log_loss
    rows = []
    for n in sizes:
        errors: dict[str, list[float]] = {f: [] for f in FIELDS}
        losses = []
        for seed in range(seeds):
            got = fit(simulate(TRUE, n, length, random.Random(seed)), starts=3, seed=seed).params
            for f in FIELDS:
                errors[f].append(abs(getattr(got, f) - getattr(TRUE, f)))
            losses.append(score(got, held).log_loss)
        rows.append(
            {
                "learners": n,
                "answers": n * length,
                "mean_abs_error": {f: round(statistics.mean(v), 4) for f, v in errors.items()},
                "max_abs_error": {f: round(max(v), 4) for f, v in errors.items()},
                "held_out_log_loss_mean": round(statistics.mean(losses), 4),
                "held_out_log_loss_worst": round(max(losses), 4),
            }
        )
    return {
        "true_params": {f: getattr(TRUE, f) for f in FIELDS},
        "default_params": {f: getattr(DEFAULT_PARAMS["mcq"], f) for f in FIELDS},
        "answers_per_learner": length,
        "seeds_per_size": seeds,
        "held_out_learners": 2000,
        "held_out_log_loss_true_params": round(floor, 4),
        "held_out_log_loss_default_params": round(default, 4),
        "rows": rows,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[20, 50, 100, 200, 500, 1000])
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--length", type=int, default=10)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    text = json.dumps(report(args.sizes, args.seeds, args.length), indent=1) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
