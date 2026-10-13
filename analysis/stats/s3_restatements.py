"""Study 3. Do restatements flatter the trend?

Exact binomial test of the share of material restatements that make the company's trend look
better, against 0.5, with a Wilson interval; and a company-cluster bootstrap, because the
restatements of one company are not independent. Pre-registered in docs/stats_hypotheses.md.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import binom, binomtest
from statsmodels.stats.proportion import proportion_confint

from analysis.stats import common, data
from analysis.stats.common import Outcome

STUDY = "s3"
PRACTICAL_SHARE = 0.10  # distance from 0.5


def binomial_p(k: int, n: int) -> float:
    return float(binomtest(k, n, 0.5, alternative="two-sided").pvalue)


def minimum_detectable_distance(n: int) -> float:
    """Smallest distance from 0.5 that the exact binomial test finds with 80% power (exact)."""
    if n < 1:
        return math.inf
    counts = np.arange(n + 1)
    rejects = np.array([binomial_p(int(k), n) < common.ALPHA for k in counts])
    if not rejects.any():
        return math.inf
    for step in range(1, 500):
        distance = step / 1000
        if binom.pmf(counts, n, 0.5 + distance)[rejects].sum() >= common.POWER:
            return distance
    return math.inf


def cluster_bootstrap_share(
    flattering: np.ndarray, total: np.ndarray, n_boot: int, rng: np.random.Generator
) -> np.ndarray:
    """Share of flattering restatements when whole companies are resampled. Inputs: per
    company, the number of flattering restatements and the number with a direction."""
    n_companies = len(total)
    times_drawn = rng.multinomial(n_companies, np.full(n_companies, 1 / n_companies), size=n_boot)
    return (times_drawn @ flattering) / (times_drawn @ total)


def bootstrap_p(shares: np.ndarray) -> float:
    """Two-sided p against 0.5: twice the smaller share of resamples on either side of it."""
    return min(1.0, 2 * min(float((shares <= 0.5).mean()), float((shares >= 0.5).mean())))


def analyse(
    frame: pd.DataFrame,
    test_id: str,
    label: str,
    role: str,
    *,
    n_boot: int = common.N_BOOTSTRAP,
    with_mde: bool = True,
) -> list[Outcome]:
    """`frame`: one row per material restatement with a direction (isin, flatters_trend).
    Returns the binomial test and, when it can be run, the clustering check."""
    n = len(frame)
    n_companies = frame["isin"].nunique() if n else 0
    if n_companies < common.MIN_COMPANIES:
        return [common.not_enough(STUDY, test_id, label, role, n, "fewer than 5 companies")]
    k = int(frame["flatters_trend"].astype(bool).sum())
    share = k / n
    low, high = proportion_confint(k, n, alpha=common.ALPHA, method="wilson")
    outcome = Outcome(
        STUDY,
        test_id,
        label,
        role,
        n=n,
        n_note=f"material restatements with a direction, at {n_companies} companies",
        statistic_name="flattering restatements",
        statistic=float(k),
        p_raw=binomial_p(k, n),
        effect_name="share flattering",
        effect=share,
        ci_low=float(low),
        ci_high=float(high),
        practical_effect=PRACTICAL_SHARE,
    )
    if not with_mde:
        return [outcome]

    per_company = frame.groupby("isin")["flatters_trend"].agg(["sum", "count"])
    shares = cluster_bootstrap_share(
        per_company["sum"].to_numpy(float),
        per_company["count"].to_numpy(float),
        n_boot,
        common.generator(3, 1),
    )
    cluster_low, cluster_high = common.percentile_interval(shares)
    cluster_p = bootstrap_p(shares)
    design_effect = float(shares.var() / (share * (1 - share) / n)) if 0 < share < 1 else 1.0
    n_effective = max(1, round(n / max(design_effect, 1.0)))
    mde = minimum_detectable_distance(n)
    mde_effective = minimum_detectable_distance(n_effective)
    outcome.mde = mde_effective
    outcome.mde_note = (
        f"distance from 0.5 at the effective number of {n_effective} independent restatements"
        f" ({mde:.3f} if all {n} were independent)"
    )
    outcome.note = f"design effect {design_effect:.2f}"
    cluster = Outcome(
        STUDY,
        f"{test_id}_cluster",
        f"{label}: companies resampled",
        common.SENSITIVITY,
        n=n_companies,
        n_note=f"companies ({n} restatements)",
        statistic_name="design effect",
        statistic=design_effect,
        p_raw=cluster_p,
        effect_name="share flattering",
        effect=share,
        ci_low=cluster_low,
        ci_high=cluster_high,
        note=f"effective number of independent restatements {n_effective}",
    )
    return [outcome, cluster]


def run(con: duckdb.DuckDBPyConnection, *, with_mde: bool = True) -> list[Outcome]:
    frame = data.restatement_directions(con)
    outcomes = analyse(
        frame, "s3_flattering", "share of material restatements that flatter the trend",
        common.PRIMARY, with_mde=with_mde,
    )  # fmt: skip
    for year, rows in frame.groupby("fiscal_year_label"):
        outcomes += analyse(
            rows, f"s3_sens_{str(year).lower().replace('-', '_')}", f"values of {year}",
            common.SENSITIVITY, with_mde=False,
        )  # fmt: skip
    return outcomes
