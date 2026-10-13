"""Study 5. Ownership and disclosure quality.

Government-owned against private Indian companies on the Disclosure Quality Score. Scores are
only compared within a financial year; the yearly Mann-Whitney comparisons are combined into
one stratified Cliff's delta. The test shuffles the ownership label among companies (a company
keeps all its years), and the interval resamples companies within ownership type.
Pre-registered in docs/stats_hypotheses.md.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

from analysis.stats import common, data
from analysis.stats.common import Outcome

STUDY = "s5"
PRACTICAL_DELTA = 0.33
PRIVATE = "Private Indian"
COMPARISONS = {"Government": "psu", "MNC subsidiary": "mnc"}


def pair_matrices(scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """`scores`: companies x years, NaN where a company has no score. Returns two company x
    company matrices summed over the years: wins[i, j] = years in which i scores above j minus
    years in which it scores below, and pairs[i, j] = years in which both have a score."""
    present = ~np.isnan(scores)
    filled = np.where(present, scores, 0.0)
    both = present[:, None, :] & present[None, :, :]
    sign = np.sign(filled[:, None, :] - filled[None, :, :]) * both
    return sign.sum(axis=2), both.sum(axis=2).astype(float)


def stratified_delta(wins: np.ndarray, pairs: np.ndarray, first: np.ndarray) -> np.ndarray:
    """Cliff's delta of the companies marked in `first` (0/1 or resampling weights, one row
    per replicate) against the others, counted within years. `first` holds the weights of the
    first group; the second group is given by `1 - first` for 0/1 labels."""
    first = np.atleast_2d(first).astype(float)
    second = 1.0 - first
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.einsum("bi,ij,bj->b", first, wins, second) / np.einsum(
            "bi,ij,bj->b", first, pairs, second
        )


def shuffled_labels(
    labels: np.ndarray, strata: np.ndarray, n_perm: int, rng: np.random.Generator
) -> np.ndarray:
    """`n_perm` shuffles of the 0/1 company labels, within `strata`."""
    shuffled = np.empty((n_perm, len(labels)))
    for stratum in np.unique(strata):
        members = np.flatnonzero(strata == stratum)
        shuffled[:, members] = rng.permuted(np.tile(labels[members], (n_perm, 1)), axis=1)
    return shuffled


def permutation_test(
    scores: np.ndarray,
    labels: np.ndarray,
    n_perm: int,
    rng: np.random.Generator,
    strata: np.ndarray | None = None,
) -> tuple[float, float]:
    """(stratified Cliff's delta, two-sided p). The label is shuffled among companies."""
    wins, pairs = pair_matrices(scores)
    observed = float(stratified_delta(wins, pairs, labels)[0])
    strata = np.zeros(len(labels)) if strata is None else strata
    permuted = stratified_delta(wins, pairs, shuffled_labels(labels, strata, n_perm, rng))
    return observed, common.permutation_p(observed, permuted[~np.isnan(permuted)])


def bootstrap_delta(
    scores: np.ndarray, labels: np.ndarray, n_boot: int, rng: np.random.Generator
) -> np.ndarray:
    """Delta of `n_boot` resamples: companies drawn with replacement within ownership type."""
    wins, pairs = pair_matrices(scores)
    first, second = np.flatnonzero(labels == 1), np.flatnonzero(labels == 0)
    drawn_first = rng.multinomial(len(first), np.full(len(first), 1 / len(first)), size=n_boot)
    drawn_second = rng.multinomial(len(second), np.full(len(second), 1 / len(second)), size=n_boot)
    block = np.ix_(first, second)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.einsum("bi,ij,bj->b", drawn_first, wins[block], drawn_second) / np.einsum(
            "bi,ij,bj->b", drawn_first, pairs[block], drawn_second
        )


def simulated_power(
    scores: np.ndarray,
    labels: np.ndarray,
    points: float,
    rng: np.random.Generator,
    n_sims: int,
    n_perm: int,
) -> tuple[float, float]:
    """Power against `points` added to the scores of the first group, on data in which the
    labels were shuffled first (so there is no other difference). Returns (power, mean delta
    produced by the shift)."""
    rejected, deltas = 0, []
    for _ in range(n_sims):
        fake = rng.permutation(labels)
        shifted = scores + points * fake[:, None]
        delta, p_value = permutation_test(shifted, fake, n_perm, rng)
        rejected += p_value < common.ALPHA
        deltas.append(delta)
    return rejected / n_sims, float(np.nanmean(deltas))


def minimum_detectable_shift(
    scores: np.ndarray,
    labels: np.ndarray,
    rng: np.random.Generator,
    n_sims: int = 500,
    n_perm: int = 499,
) -> tuple[float, float]:
    """Smallest shift in score points found with 80% power, and the delta it produces."""
    produced: dict[float, float] = {}

    def power_at(points: float) -> float:
        power, produced[points] = simulated_power(scores, labels, points, rng, n_sims, n_perm)
        return power

    grid = [0.5 * step for step in range(1, 61)]
    points, _ = common.first_with_power(grid, power_at)
    return (math.inf, math.inf) if math.isinf(points) else (points, produced[points])


def to_matrix(frame: pd.DataFrame, first_type: str) -> tuple[np.ndarray, np.ndarray, pd.Index]:
    """Scores as companies x years, and the 0/1 label (1 = `first_type`, 0 = private)."""
    rows = frame[frame["ownership_type"].isin([first_type, PRIVATE])]
    wide = rows.pivot(index="isin", columns="fiscal_year_label", values="dqs_total")
    owner = rows.drop_duplicates("isin").set_index("isin")["ownership_type"].reindex(wide.index)
    return wide.to_numpy(float), (owner == first_type).to_numpy(float), wide.index


def analyse(
    scores: np.ndarray,
    labels: np.ndarray,
    test_id: str,
    label: str,
    role: str,
    *,
    strata: np.ndarray | None = None,
    n_perm: int = common.N_PERMUTATIONS,
    n_boot: int = common.N_BOOTSTRAP,
    with_mde: bool = True,
) -> Outcome:
    n_first, n_second = int((labels == 1).sum()), int((labels == 0).sum())
    if min(n_first, n_second) < common.MIN_COMPANIES:
        return common.not_enough(
            STUDY, test_id, label, role, n_first + n_second,
            f"a group with fewer than 5 companies ({n_first} against {n_second})",
        )  # fmt: skip
    delta, p_raw = permutation_test(scores, labels, n_perm, common.generator(5, 1), strata)
    low, high = common.percentile_interval(
        bootstrap_delta(scores, labels, n_boot, common.generator(5, 2))
    )
    outcome = Outcome(
        STUDY,
        test_id,
        label,
        role,
        n=n_first + n_second,
        n_note=(
            f"companies: {n_first} against {n_second}; "
            f"{int((~np.isnan(scores)).sum())} yearly scores in {scores.shape[1]} years"
        ),
        statistic_name="stratified Cliff's delta",
        statistic=delta,
        p_raw=p_raw,
        effect_name="stratified Cliff's delta",
        effect=delta,
        ci_low=low,
        ci_high=high,
        practical_effect=PRACTICAL_DELTA,
        note=f"{n_perm} permutations of the company label",
    )
    if with_mde:
        points, produced = minimum_detectable_shift(scores, labels, common.generator(5, 3))
        outcome.mde = produced
        outcome.mde_note = (
            "no shift up to 30 points is found"
            if math.isinf(points)
            else f"absolute delta, produced by a shift of {points:.1f} score points"
        )
    return outcome


def per_year(frame: pd.DataFrame, first_type: str, slug: str) -> list[Outcome]:
    """Mann-Whitney U per financial year (descriptive, raw p-values)."""
    outcomes = []
    for year, rows in frame.groupby("fiscal_year_label"):
        first = rows.loc[rows["ownership_type"] == first_type, "dqs_total"].to_numpy(float)
        second = rows.loc[rows["ownership_type"] == PRIVATE, "dqs_total"].to_numpy(float)
        test_id = f"s5_{slug}_{str(year).lower().replace('-', '_')}"
        if min(len(first), len(second)) < common.MIN_COMPANIES:
            outcomes.append(
                common.not_enough(
                    STUDY,
                    test_id,
                    str(year),
                    common.DESCRIPTIVE,
                    len(first) + len(second),
                    "a group with fewer than 5 companies",
                )  # fmt: skip
            )
            continue
        result = mannwhitneyu(first, second, alternative="two-sided")
        outcomes.append(
            Outcome(
                STUDY,
                test_id,
                f"{first_type} against {PRIVATE}, {year}",
                common.DESCRIPTIVE,
                n=len(first) + len(second),
                n_note=f"companies: {len(first)} against {len(second)}",
                statistic_name="Mann-Whitney U",
                statistic=float(result.statistic),
                p_raw=float(result.pvalue),
                effect_name="Cliff's delta",
                effect=float(2 * result.statistic / (len(first) * len(second)) - 1),
            )
        )
    return outcomes


def run(con: duckdb.DuckDBPyConnection, *, with_mde: bool = True) -> list[Outcome]:
    frame = data.disclosure_quality(con)
    frame = frame[frame["dqs_components_used"] >= 3]
    final = frame[~frame["is_provisional"].astype(bool)]
    outcomes: list[Outcome] = []
    for first_type, slug in COMPARISONS.items():
        label = f"DQS of {first_type} against {PRIVATE} companies"
        scores, labels, companies = to_matrix(final, first_type)
        primary = analyse(
            scores, labels, f"s5_{slug}", f"{label}, final years", common.PRIMARY,
            with_mde=with_mde,
        )  # fmt: skip
        outcomes.append(primary)
        if primary.status != common.OK:
            continue
        outcomes += per_year(final, first_type, slug)
        sector = final.drop_duplicates("isin").set_index("isin")["sector_group"].reindex(companies)
        outcomes.append(
            analyse(
                scores,
                labels,
                f"s5_{slug}_sens_within_sector",
                f"{label}, label shuffled within sector group",
                common.SENSITIVITY,
                strata=sector.to_numpy(),
                with_mde=False,
            )  # fmt: skip
        )
        scores, labels, _ = to_matrix(frame, first_type)
        outcomes.append(
            analyse(
                scores,
                labels,
                f"s5_{slug}_sens_with_provisional",
                f"{label}, provisional year included",
                common.SENSITIVITY,
                with_mde=False,
            )  # fmt: skip
        )
    return outcomes
