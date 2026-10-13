"""Check the statistical methods themselves on made-up data (no warehouse needed).

    python -m analysis.stats.validate

For every test of the five studies: with a planted effect the test must find it (power), and
with no effect it must raise a false alarm in about 5% of 500 data sets (false-positive rate).
The data sets are simulated with the sample sizes the real studies have roughly. Used by
tests/test_stats.py; the figures are quoted in docs/stats_findings.md.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd

from analysis.stats import (
    common,
    s1_dqs_ghg,
    s2_decarbonisation,
    s3_restatements,
    s4_assurance,
    s5_ownership,
)

NULL_RUNS = 500
PLANTED_RUNS = 200
N_RESAMPLES = 999  # permutations / bootstrap resamples inside one simulated data set
YEARS = ["FY2023-24", "FY2024-25"]
Simulation = Callable[[np.random.Generator, bool], float]  # (rng, planted) -> p-value


@dataclass(frozen=True)
class Check:
    name: str
    description: str
    planted_effect: str
    p_value: Simulation
    exact: bool = False  # exact tests on counts are conservative: false alarms below 5%


def _s1(rng: np.random.Generator, planted: bool) -> float:
    r = 0.6 if planted else 0.0
    groups = []
    for n in (11, 8, 6, 5, 5):
        x = rng.standard_normal(n)
        y = r * x + np.sqrt(1 - r * r) * rng.standard_normal(n) + rng.normal(0, 3)  # group level
        groups.append((x, y))
    return s1_dqs_ghg.permutation_test(groups, N_RESAMPLES, rng)[1]


def _s2(rng: np.random.Generator, planted: bool) -> float:
    changes = rng.standard_t(4, size=20) * 0.12 + (-0.12 if planted else 0.0)
    return s2_decarbonisation.signed_rank(changes)[1]


def _restatements(rng: np.random.Generator, share: float, spread: float) -> np.ndarray:
    """Per company: (flattering, with a direction). `spread` > 0 makes companies differ in
    how often they flatter, around the same overall share (clustering)."""
    total = rng.geometric(1 / 6, size=40)
    if spread > 0:
        company_share = np.clip(share + rng.choice([-spread, spread], size=40), 0, 1)
    else:
        company_share = np.full(40, share)
    return np.stack([rng.binomial(total, company_share), total])


def _s3_binomial(rng: np.random.Generator, planted: bool) -> float:
    flattering, total = _restatements(rng, 0.62 if planted else 0.5, 0.0)
    return s3_restatements.binomial_p(int(flattering.sum()), int(total.sum()))


def _s3_binomial_clustered(rng: np.random.Generator, planted: bool) -> float:
    flattering, total = _restatements(rng, 0.62 if planted else 0.5, 0.35)
    return s3_restatements.binomial_p(int(flattering.sum()), int(total.sum()))


def _s3_cluster(rng: np.random.Generator, planted: bool) -> float:
    flattering, total = _restatements(rng, 0.75 if planted else 0.5, 0.35)
    shares = s3_restatements.cluster_bootstrap_share(
        flattering.astype(float), total.astype(float), N_RESAMPLES, rng
    )
    return s3_restatements.bootstrap_p(shares)


def _assurance(rng: np.random.Generator, planted: bool, clustered: bool) -> pd.DataFrame:
    """48 companies in two years; a third have whole-report assurance (mostly in both years).
    `clustered`: a company prone to restating is prone in both years."""
    rows = []
    for company in range(48):
        whole = rng.random() < 0.3
        prone = rng.normal(0, 1.5) if clustered else 0.0
        for year in YEARS:
            scope_whole = whole if rng.random() < 0.9 else not whole
            logit = 0.4 + prone - (2.0 if planted and scope_whole else 0.0)
            rate = 1 / (1 + np.exp(-logit))
            n_compared = int(rng.integers(15, 30))
            restated = rng.random() < rate
            n_material = int(rng.integers(1, 4)) if restated else 0
            rows.append(
                {
                    "isin": f"C{company:02d}",
                    "fiscal_year_label": year,
                    "assurance_scope": s4_assurance.WHOLE if scope_whole else s4_assurance.CORE,
                    "restated": restated,
                    "n_material": n_material,
                    "n_compared": n_compared,
                }
            )
    return pd.DataFrame(rows)


def _s4_fisher(rng: np.random.Generator, planted: bool) -> float:
    return s4_assurance.fisher_p(s4_assurance.two_by_two(_assurance(rng, planted, False)))


def _s4_fisher_clustered(rng: np.random.Generator, planted: bool) -> float:
    return s4_assurance.fisher_p(s4_assurance.two_by_two(_assurance(rng, planted, True)))


def _s4_cluster(rng: np.random.Generator, planted: bool) -> float:
    frame = _assurance(rng, planted, True)
    return s4_assurance.cluster_permutation(frame, N_RESAMPLES, rng)["restated_share"][1]


def _s5(rng: np.random.Generator, planted: bool) -> float:
    labels = np.array([1.0] * 7 + [0.0] * 41)
    company = rng.normal(0, 5, size=48)  # a company scores alike in every year
    scores = 85 + company[:, None] + rng.normal(0, 3, size=(48, 3))
    scores[rng.random((48, 3)) < 0.05] = np.nan  # a few missing years
    scores += (8.0 if planted else 0.0) * labels[:, None]
    return s5_ownership.permutation_test(scores, labels, N_RESAMPLES, rng)[1]


CHECKS = [
    Check(
        "s1_stratified_permutation",
        "Study 1: pooled Spearman, stratified permutation, 35 companies in 5 groups",
        "correlation 0.6 within groups",
        _s1,
    ),
    Check(
        "s2_wilcoxon",
        "Study 2: Wilcoxon signed-rank, 20 companies",
        "median change of -11% (-0.12 in logs)",
        _s2,
        exact=True,
    ),
    Check(
        "s3_binomial",
        "Study 3: exact binomial, about 240 independent restatements",
        "62% flattering",
        _s3_binomial,
        exact=True,
    ),
    Check(
        "s3_cluster_bootstrap",
        "Study 3: company-cluster bootstrap, restatements clustered in 40 companies",
        "75% flattering",
        _s3_cluster,
    ),
    Check(
        "s4_fisher",
        "Study 4: Fisher's exact test, 96 independent company-years",
        "odds ratio about 0.14",
        _s4_fisher,
        exact=True,
    ),
    Check(
        "s4_cluster_permutation",
        "Study 4: company-cluster permutation, restatement-prone companies",
        "odds ratio about 0.14",
        _s4_cluster,
    ),
    Check(
        "s5_company_permutation",
        "Study 5: stratified Cliff's delta, company permutation, 7 against 41 companies",
        "8 score points",
        _s5,
    ),
]

# Not methods we rely on, but the reason for the clustering checks: what the simple tests do
# when the observations of one company hang together.
NAIVE_UNDER_CLUSTERING = [
    Check(
        "s3_binomial_on_clustered_data",
        "Study 3: exact binomial on clustered restatements",
        "-",
        _s3_binomial_clustered,
    ),
    Check(
        "s4_fisher_on_clustered_data",
        "Study 4: Fisher's exact test on restatement-prone companies",
        "-",
        _s4_fisher_clustered,
    ),
]


def rejection_rate(check: Check, planted: bool, runs: int) -> float:
    """Share of `runs` simulated data sets in which the test gives p < alpha."""
    rng = common.generator(9, int(planted), sum(map(ord, check.name)))
    rejected = sum(check.p_value(rng, planted) < common.ALPHA for _ in range(runs))
    return rejected / runs


def false_positive_rate(check: Check, runs: int = NULL_RUNS) -> float:
    return rejection_rate(check, False, runs)


def power(check: Check, runs: int = PLANTED_RUNS) -> float:
    return rejection_rate(check, True, runs)


def main() -> int:
    print(f"{'check':<34} {'power':>7} {'false alarms':>13}   planted effect")
    for check in CHECKS:
        print(
            f"{check.name:<34} {power(check):>7.3f} {false_positive_rate(check):>13.3f}   "
            f"{check.planted_effect}"
        )
    print("\nsimple tests on clustered data with no effect (why the clustering checks exist):")
    for check in NAIVE_UNDER_CLUSTERING:
        print(f"{check.name:<34} {'':>7} {false_positive_rate(check):>13.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
