"""Study 1. Disclosure quality and carbon intensity.

Within ranking groups: Spearman correlation between the Disclosure Quality Score and log GHG
intensity. Pooled over the groups with a stratified permutation test (the score is shuffled
within each group) and a bootstrap interval (companies resampled within their group).
Pre-registered in docs/stats_hypotheses.md.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import rankdata

from analysis.stats import common, data
from analysis.stats.common import Outcome

STUDY = "s1"
PRACTICAL_RHO = 0.3
Groups = list[tuple[np.ndarray, np.ndarray]]  # per ranking group: (score, log intensity)


def _row_correlation(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Pearson correlation of each row of `a` with the matching row of `b` (NaN if flat)."""
    a = a - a.mean(axis=-1, keepdims=True)
    b = b - b.mean(axis=-1, keepdims=True)
    denominator = np.sqrt((a * a).sum(axis=-1) * (b * b).sum(axis=-1))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(denominator > 0, (a * b).sum(axis=-1) / denominator, np.nan)


def spearman(x: np.ndarray, y: np.ndarray) -> float:
    return float(_row_correlation(rankdata(x), rankdata(y)))


def usable_groups(groups: Groups, min_n: int) -> Groups:
    """Groups with enough companies and some variation in both variables."""
    return [(x, y) for x, y in groups if len(x) >= min_n and np.ptp(x) > 0 and np.ptp(y) > 0]


def pooled_rho(groups: Groups) -> float:
    """Weighted mean of the group correlations, weight = companies in the group minus 1."""
    weights = np.array([len(x) - 1 for x, _ in groups], dtype=float)
    rhos = np.array([spearman(x, y) for x, y in groups])
    return float((weights * rhos).sum() / weights.sum())


def permuted_pooled_rho(groups: Groups, n_perm: int, rng: np.random.Generator) -> np.ndarray:
    """Pooled rho after shuffling the score within each group, `n_perm` times."""
    total = np.zeros(n_perm)
    weight = 0.0
    for x, y in groups:
        shuffled = rng.permuted(np.tile(rankdata(x), (n_perm, 1)), axis=1)
        total += (len(x) - 1) * _row_correlation(shuffled, rankdata(y)[None, :])
        weight += len(x) - 1
    return total / weight


def permutation_test(groups: Groups, n_perm: int, rng: np.random.Generator) -> tuple[float, float]:
    """(pooled rho, two-sided p) of the stratified permutation test."""
    observed = pooled_rho(groups)
    return observed, common.permutation_p(observed, permuted_pooled_rho(groups, n_perm, rng))


def bootstrap_pooled_rho(
    groups: Groups, n_boot: int, rng: np.random.Generator
) -> tuple[np.ndarray, int]:
    """Pooled rho of `n_boot` resamples (companies drawn within their group), and how many
    group resamples had to be drawn again because they had no variation."""
    total = np.zeros(n_boot)
    weight = 0.0
    redraws = 0
    for x, y in groups:
        n = len(x)
        rho = np.full(n_boot, np.nan)
        for _ in range(200):
            todo = np.flatnonzero(np.isnan(rho))
            if len(todo) == 0:
                break
            picks = rng.integers(0, n, size=(len(todo), n))
            rho[todo] = _row_correlation(rankdata(x[picks], axis=1), rankdata(y[picks], axis=1))
            redraws += int(np.isnan(rho[todo]).sum())
        total += (n - 1) * rho
        weight += n - 1
    return total / weight, redraws


def simulated_power(
    sizes: list[int], r: float, rng: np.random.Generator, n_sims: int, n_perm: int
) -> float:
    """Share of simulated data sets (normal pairs with correlation r in every group) in which
    the stratified permutation test rejects at alpha."""
    weight = float(sum(n - 1 for n in sizes))
    rejected = 0
    chunk = 100
    for start in range(0, n_sims, chunk):
        size = min(chunk, n_sims - start)
        observed = np.zeros(size)
        permuted = np.zeros((size, n_perm))
        for n in sizes:
            x = rng.standard_normal((size, n))
            y = r * x + math.sqrt(1 - r * r) * rng.standard_normal((size, n))
            rank_x, rank_y = rankdata(x, axis=1), rankdata(y, axis=1)
            observed += (n - 1) * _row_correlation(rank_x, rank_y)
            shuffled = rng.permuted(np.repeat(rank_x[:, None, :], n_perm, axis=1), axis=2)
            permuted += (n - 1) * _row_correlation(shuffled, rank_y[:, None, :])
        observed /= weight
        permuted /= weight
        extreme = (np.abs(permuted) >= np.abs(observed)[:, None] - 1e-12).sum(axis=1)
        rejected += int(((1 + extreme) / (1 + n_perm) < common.ALPHA).sum())
    return rejected / n_sims


def minimum_detectable_rho(
    sizes: list[int], rng: np.random.Generator, n_sims: int = 1000, n_perm: int = 999
) -> tuple[float, float]:
    """Smallest Spearman rho found with 80% power, on a grid of 0.05 in the underlying
    Pearson correlation. Returns (rho, power)."""
    grid = [round(0.05 * step, 2) for step in range(1, 20)]
    r, power = common.first_with_power(
        grid, lambda value: simulated_power(sizes, value, rng, n_sims, n_perm)
    )
    if math.isinf(r):
        return math.inf, power
    return 6 / math.pi * math.asin(r / 2), power  # Spearman rho of a normal pair


def analyse(
    groups: Groups,
    test_id: str,
    label: str,
    role: str,
    *,
    min_n: int = common.MIN_COMPANIES,
    n_perm: int = common.N_PERMUTATIONS,
    n_boot: int = common.N_BOOTSTRAP,
    with_mde: bool = True,
) -> Outcome:
    """The pooled test on one set of groups."""
    kept = usable_groups(groups, min_n)
    n = sum(len(x) for x, _ in kept)
    if not kept or n < common.MIN_COMPANIES:
        return common.not_enough(
            STUDY, test_id, label, role, n, f"no ranking group with {min_n} or more companies"
        )
    rho, p_raw = permutation_test(kept, n_perm, common.generator(1, 1))
    resampled, redraws = bootstrap_pooled_rho(kept, n_boot, common.generator(1, 2))
    low, high = common.percentile_interval(resampled)
    outcome = Outcome(
        STUDY,
        test_id,
        label,
        role,
        n=n,
        n_note=f"companies in {len(kept)} ranking groups",
        statistic_name="pooled Spearman rho",
        statistic=rho,
        p_raw=p_raw,
        effect_name="pooled Spearman rho",
        effect=rho,
        ci_low=low,
        ci_high=high,
        practical_effect=PRACTICAL_RHO,
        note=f"{n_perm} stratified permutations; {redraws} bootstrap redraws",
    )
    if with_mde:
        sizes = [len(x) for x, _ in kept]
        outcome.mde, power = minimum_detectable_rho(sizes, common.generator(1, 3))
        outcome.mde_note = f"absolute rho, simulated power {power:.2f}"
    return outcome


def per_group(frame: pd.DataFrame) -> list[Outcome]:
    """Spearman correlation inside each ranking group (descriptive)."""
    outcomes = []
    for group, rows in frame.groupby("ranking_group"):
        x, y = rows["dqs_total"].to_numpy(float), rows["log_intensity"].to_numpy(float)
        test_id = (
            f"s1_group_{str(group).lower().replace(' ', '_').replace('-', '_').replace('&', 'and')}"
        )
        if len(rows) < common.MIN_COMPANIES or np.ptp(x) == 0 or np.ptp(y) == 0:
            outcomes.append(
                common.not_enough(
                    STUDY, test_id, str(group), common.DESCRIPTIVE, len(rows), "fewer than 5"
                )
            )
            continue
        rho = spearman(x, y)
        outcomes.append(
            Outcome(
                STUDY,
                test_id,
                str(group),
                common.DESCRIPTIVE,
                n=len(rows),
                n_note="companies",
                effect_name="Spearman rho",
                effect=rho,
            )
        )
    return outcomes


def to_groups(frame: pd.DataFrame) -> Groups:
    return [
        (rows["dqs_total"].to_numpy(float), rows["log_intensity"].to_numpy(float))
        for _, rows in frame.groupby("ranking_group")
    ]


def load(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Company-years of ranking groups where GHG intensity is ranked, with score and flags."""
    status = data.ghg_status(con)
    scores = data.disclosure_quality(con)
    review = data.panel(con)[["isin", "needs_review"]]
    frame = status.merge(
        scores[["isin", "fiscal_year_label", "dqs_total", "dqs_components_used"]],
        on=["isin", "fiscal_year_label"],
    ).merge(review, on="isin", how="left")
    frame["needs_review"] = frame["needs_review"].fillna(False).astype(bool)
    frame = frame[frame["is_ghg_material"] & (frame["dqs_components_used"] >= 3)].copy()
    frame["log_intensity"] = np.log(frame["intensity"].astype(float))
    return frame


def run(con: duckdb.DuckDBPyConnection, *, with_mde: bool = True) -> list[Outcome]:
    frame = load(con)
    all_years = data.years(con)
    confirmed_years = sorted(frame.loc[frame["is_confirmed"], "fiscal_year_label"].unique())
    label = "DQS and log GHG intensity within ranking groups"
    if not confirmed_years:
        return [common.not_enough(STUDY, "s1_pooled", label, common.PRIMARY, 0, "no data")]
    year = confirmed_years[-1]
    in_year = frame[frame["fiscal_year_label"] == year]
    clean = in_year[in_year["is_confirmed"] & ~in_year["needs_review"]]

    primary = analyse(
        to_groups(clean), "s1_pooled", f"{label}, {year}, confirmed", common.PRIMARY,
        with_mde=with_mde,
    )  # fmt: skip
    outcomes = [primary, *per_group(clean)]
    outcomes.append(
        analyse(
            to_groups(clean),
            "s1_sens_groups_of_3",
            f"{year}, confirmed, groups of 3 or more",
            common.SENSITIVITY,
            min_n=3,
            with_mde=False,
        )  # fmt: skip
    )
    outcomes.append(
        analyse(
            to_groups(in_year),
            "s1_sens_unconfirmed",
            f"{year}, unconfirmed values included",
            common.SENSITIVITY,
            with_mde=False,
        )  # fmt: skip
    )
    if all_years.index(year) > 0:
        other = all_years[all_years.index(year) - 1]
        rows = frame[(frame["fiscal_year_label"] == other) & frame["is_confirmed"]]
        outcomes.append(
            analyse(
                to_groups(rows[~rows["needs_review"]]),
                "s1_sens_previous_year",
                f"{other}, confirmed",
                common.SENSITIVITY,
                with_mde=False,
            )  # fmt: skip
        )
    if all_years[-1] > year:
        outcomes.append(
            analyse(
                to_groups(frame[frame["fiscal_year_label"] == all_years[-1]]),
                "s1_sens_provisional",
                f"{all_years[-1]}, provisional",
                common.SENSITIVITY,
                with_mde=False,
            )  # fmt: skip
        )
    return outcomes
