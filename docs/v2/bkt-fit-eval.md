# BKT parameter fitting: how much data is enough (2026-11-11)

Measured by `apps/api/app/evalkit/bkt_fit_report.py` (seeded, simulated, no database). Raw numbers:
`bkt-fit-eval.json`. Fitting: `apps/api/app/engine/bkt_fit.py` (EM / Baum-Welch, best of 3 starts, bounded
slip ≤ 0.3 and guess ≤ 0.5).

Setup: simulated learners answer 10 questions on one concept with true parameters
p_init 0.3, p_transit 0.15, p_slip 0.08,
p_guess 0.2. EM estimates them back from N learners; 10 seeds per N.
Prediction quality is log loss on 2000 held-out learners, predicting each answer from the
earlier answers only. Lower is better. On those learners the true parameters give
**0.4981** (the floor) and the literature defaults
(p_init 0.2, p_transit 0.1, p_slip 0.1,
p_guess 0.25) give **0.5066**.

| Learners (answers) | Mean abs. error p_init / p_transit / p_slip / p_guess | Worst abs. error | Held-out log loss, mean (worst seed) | Better than defaults? |
|---|---|---|---|---|
| 20 (200) | 0.096 / 0.046 / 0.015 / 0.059 | 0.216 / 0.126 / 0.036 / 0.130 | 0.5085 (0.5269) | no |
| 50 (500) | 0.075 / 0.027 / 0.011 / 0.040 | 0.165 / 0.053 / 0.025 / 0.097 | 0.5036 (0.5181) | on average only |
| 100 (1000) | 0.059 / 0.017 / 0.007 / 0.031 | 0.109 / 0.052 / 0.019 / 0.065 | 0.5007 (0.5042) | yes, every seed |
| 200 (2000) | 0.024 / 0.011 / 0.007 / 0.016 | 0.053 / 0.027 / 0.012 / 0.037 | 0.4989 (0.5005) | yes, every seed |
| 500 (5000) | 0.018 / 0.008 / 0.004 / 0.008 | 0.040 / 0.013 / 0.009 / 0.017 | 0.4985 (0.4988) | yes, every seed |
| 1000 (10000) | 0.015 / 0.004 / 0.004 / 0.005 | 0.030 / 0.009 / 0.005 / 0.013 | 0.4983 (0.4985) | yes, every seed |

## What it says
- **EM recovers the parameters** when the model is right: with 1,000 learners every parameter is within about
  0.03 in the worst seed.
- **Small samples hurt.** With 20 learners a fitted model predicts *worse* than the defaults on average; with 50 it is
  better on average but some seeds are worse. From **100 learners** (about 1000 answers per
  concept) every seed beat the defaults in this setup.
- **Practical consequence:** a pilot with 10–20 people cannot fit per-concept parameters. Pool answers across
  concepts of one course (one parameter set per course or item kind), and use a fit only after it beats the defaults
  on held-out learners.
- **Gains are modest here** because the true parameters are close to the defaults (log loss 0.4981 vs 0.5066). The
  fit matters more when real learners differ from the literature values, which is exactly what is unknown.

## Limits
Simulated learners follow the BKT model exactly (no forgetting, one skill per question, identical learners). Real
data breaks these assumptions; the held-out comparison is the safeguard, not the recovery numbers. Fitted parameters
are not yet stored or used by the services: that needs per-course parameter storage (a migration) and real answers.
