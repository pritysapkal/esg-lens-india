"""Study 4. Assurance of the whole report and later restatement.

Company-years with assurance of the whole BRSR ("all") against Core only ("partial"): was at
least one compared metric restated materially in the next report? Fisher's exact test and a
conditional odds ratio; a company-cluster permutation as the clustering check.
Pre-registered in docs/stats_hypotheses.md.
"""

from __future__ import annotations

import math

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import binom, fisher_exact
from scipy.stats.contingency import odds_ratio

from analysis.stats import common, data
from analysis.stats.common import Outcome

STUDY = "s4"
PRACTICAL_DIFFERENCE = 20.0  # percentage points
WHOLE, CORE = "all", "partial"


def fisher_p(table: np.ndarray) -> float:
    return float(fisher_exact(table, alternative="two-sided")[1])


def two_by_two(frame: pd.DataFrame) -> np.ndarray:
    """Rows: whole report, Core only. Columns: restated, not restated."""
    whole = frame[frame["assurance_scope"] == WHOLE]["restated"].astype(bool)
    core = frame[frame["assurance_scope"] == CORE]["restated"].astype(bool)
    return np.array(
        [[whole.sum(), (~whole).sum()], [core.sum(), (~core).sum()]],
        dtype=int,
    )


def minimum_detectable_difference(
    n_whole: int, n_core: int, core_rate: float
) -> tuple[float, float]:
    """Smallest difference in the restated share (percentage points) that Fisher's test finds
    with 80% power, by exact enumeration: (lower, higher) rate in the whole-report group
    against `core_rate` in the Core-only group. inf = not even 0% (or 100%) would be found."""
    whole_counts, core_counts = np.arange(n_whole + 1), np.arange(n_core + 1)
    rejects = np.array(
        [
            [
                fisher_p(np.array([[a, n_whole - a], [b, n_core - b]])) < common.ALPHA
                for b in core_counts
            ]
            for a in whole_counts
        ]
    )
    core_pmf = binom.pmf(core_counts, n_core, core_rate)

    def power(rate: float) -> float:
        return float(binom.pmf(whole_counts, n_whole, rate) @ rejects @ core_pmf)

    def smallest(direction: int) -> float:
        for step in range(1, 101):
            rate = core_rate + direction * step / 100
            if not -1e-9 <= rate <= 1 + 1e-9:
                break
            if power(min(max(rate, 0.0), 1.0)) >= common.POWER:
                return float(step)
        return math.inf

    return smallest(-1), smallest(+1)


def cluster_permutation(
    frame: pd.DataFrame, n_perm: int, rng: np.random.Generator
) -> dict[str, tuple[float, float]]:
    """Each company's assurance scopes (all its years together) are passed to another company
    with the same years present. Returns, per statistic, (observed, two-sided p):
    `restated_share` = difference (whole - Core) in the share of company-years restated,
    `metric_share` = difference in the pooled share of compared metrics restated."""
    sums = {key: np.zeros(n_perm) for key in ("w_n", "w_restated", "w_material", "w_compared")}
    totals = {"n": 0.0, "restated": 0.0, "material": 0.0, "compared": 0.0}
    observed_sums = dict.fromkeys(sums, 0.0)
    wide = frame.pivot(index="isin", columns="fiscal_year_label")
    pattern = wide["assurance_scope"].notna().apply(tuple, axis=1)
    for _, block in wide.groupby(pattern):
        present = block["assurance_scope"].notna().iloc[0].to_numpy()
        whole = (block["assurance_scope"].to_numpy()[:, present] == WHOLE).astype(float)
        restated = block["restated"].to_numpy()[:, present].astype(float)
        material = block["n_material"].to_numpy()[:, present].astype(float)
        compared = block["n_compared"].to_numpy()[:, present].astype(float)
        order = rng.permuted(np.tile(np.arange(len(block)), (n_perm, 1)), axis=1)
        shuffled = whole[order]  # (n_perm, companies, years)
        for key, values in (
            ("w_n", np.ones_like(restated)),
            ("w_restated", restated),
            ("w_material", material),
            ("w_compared", compared),
        ):
            sums[key] += (shuffled * values[None, :, :]).sum(axis=(1, 2))
            observed_sums[key] += float((whole * values).sum())
        totals["n"] += restated.size
        totals["restated"] += restated.sum()
        totals["material"] += material.sum()
        totals["compared"] += compared.sum()

    def differences(part):
        with np.errstate(invalid="ignore", divide="ignore"):
            restated_share = part["w_restated"] / part["w_n"] - (
                totals["restated"] - part["w_restated"]
            ) / (totals["n"] - part["w_n"])
            metric_share = part["w_material"] / part["w_compared"] - (
                totals["material"] - part["w_material"]
            ) / (totals["compared"] - part["w_compared"])
        return restated_share, metric_share

    observed, permuted = differences(observed_sums), differences(sums)
    return {
        name: (float(observed[index]), common.permutation_p(observed[index], permuted[index]))
        for index, name in enumerate(("restated_share", "metric_share"))
    }


def analyse(
    frame: pd.DataFrame,
    test_id: str,
    label: str,
    role: str,
    *,
    n_perm: int = common.N_PERMUTATIONS,
    with_mde: bool = True,
) -> list[Outcome]:
    """`frame`: one row per company-year (isin, fiscal_year_label, assurance_scope, restated,
    n_material, n_compared)."""
    frame = frame[frame["assurance_scope"].isin([WHOLE, CORE])]
    table = two_by_two(frame)
    n_whole, n_core = int(table[0].sum()), int(table[1].sum())
    companies = frame.groupby("assurance_scope")["isin"].nunique()
    if min(companies.get(WHOLE, 0), companies.get(CORE, 0)) < common.MIN_COMPANIES:
        return [
            common.not_enough(
                STUDY, test_id, label, role, len(frame), "a group with fewer than 5 companies"
            )
        ]
    result = odds_ratio(table, kind="conditional")
    interval = result.confidence_interval(confidence_level=1 - common.ALPHA)
    rate_whole, rate_core = table[0, 0] / n_whole, table[1, 0] / n_core
    outcome = Outcome(
        STUDY,
        test_id,
        label,
        role,
        n=len(frame),
        n_note=(
            f"company-years at {frame['isin'].nunique()} companies: {n_whole} whole report, "
            f"{n_core} Core only"
        ),
        statistic_name="restated share, whole report vs Core only (%)",
        statistic=100 * (rate_whole - rate_core),
        p_raw=fisher_p(table),
        effect_name="odds ratio",
        effect=float(result.statistic),
        ci_low=float(interval.low),
        ci_high=float(interval.high),
        practical_effect=PRACTICAL_DIFFERENCE,
        note=(
            f"at least one material restatement: {table[0, 0]} of {n_whole} whole report "
            f"({100 * rate_whole:.1f}%), {table[1, 0]} of {n_core} Core only "
            f"({100 * rate_core:.1f}%)"
        ),
    )
    if not with_mde:
        return [outcome]

    lower, higher = minimum_detectable_difference(n_whole, n_core, rate_core)
    outcome.mde = min(lower, higher)
    outcome.mde_note = (
        "difference in percentage points: "
        + ("no lower rate can be found" if math.isinf(lower) else f"{lower:.0f} lower")
        + ", "
        + ("no higher rate can be found" if math.isinf(higher) else f"{higher:.0f} higher")
    )
    outcomes = [outcome]
    by_scope = frame.groupby("assurance_scope")
    pooled = 100 * by_scope["n_material"].sum() / by_scope["n_compared"].sum()
    typical = (
        100 * (frame["n_material"] / frame["n_compared"]).groupby(frame["assurance_scope"]).median()
    )
    checks = cluster_permutation(frame, n_perm, common.generator(4, 1))
    for key, name, detail in (
        ("restated_share", "share of company-years restated", ""),
        (
            "metric_share",
            "pooled share of compared metrics restated",
            f"whole report {pooled[WHOLE]:.1f}% (median company-year {typical[WHOLE]:.1f}%), "
            f"Core only {pooled[CORE]:.1f}% (median {typical[CORE]:.1f}%)",
        ),
    ):
        difference, p_value = checks[key]
        outcomes.append(
            Outcome(
                STUDY,
                f"{test_id}_cluster_{key}",
                f"{label}: company-cluster permutation, {name}",
                common.SENSITIVITY,
                n=int(frame["isin"].nunique()),
                n_note="companies",
                statistic_name="difference, whole report minus Core only (points)",
                statistic=100 * difference,
                p_raw=p_value,
                effect_name="difference in percentage points",
                effect=100 * difference,
                note=detail,
            )
        )
    return outcomes


def load(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Company-years with an assurance scope and at least one compared metric."""
    scores = data.disclosure_quality(con)
    restated = data.restatements_by_company_year(con)
    frame = scores[["isin", "fiscal_year_label", "assurance_level", "assurance_scope"]].merge(
        restated, on=["isin", "fiscal_year_label"]
    )
    frame = frame[frame["assurance_scope"].isin([WHOLE, CORE])].copy()
    frame["restated"] = frame["n_material"] > 0
    return frame


def run(con: duckdb.DuckDBPyConnection, *, with_mde: bool = True) -> list[Outcome]:
    frame = load(con)
    label = "whole-report assurance and a later material restatement"
    outcomes = analyse(
        frame[frame["assurance_level"] == "reasonable"], "s4_assurance", label, common.PRIMARY,
        with_mde=with_mde,
    )  # fmt: skip
    outcomes += analyse(
        frame, "s4_sens_with_assessment", f"{label}, assessments included", common.SENSITIVITY,
        with_mde=False,
    )  # fmt: skip
    return outcomes
