"""Study 2. Is GHG intensity falling?

Wilcoxon signed-rank test on each company's change in log GHG intensity between two years,
for all companies and per sector group. Effect: the median change in percent with a bootstrap
interval. Pre-registered in docs/stats_hypotheses.md.
"""

from __future__ import annotations

import math
import warnings

import duckdb
import numpy as np
import pandas as pd
from scipy.stats import rankdata, wilcoxon

from analysis.stats import common, data
from analysis.stats.common import Outcome

STUDY = "s2"
PRACTICAL_PCT = 5.0


def to_percent(log_change: float) -> float:
    return 100 * (math.exp(log_change) - 1)


def signed_rank(changes: np.ndarray) -> tuple[float, float]:
    """(statistic, two-sided p) of the Wilcoxon signed-rank test; exact where scipy can."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        result = wilcoxon(changes, zero_method="wilcox", alternative="two-sided", method="auto")
    return float(result.statistic), float(result.pvalue)


def bootstrap_median(changes: np.ndarray, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    picks = rng.integers(0, len(changes), size=(n_boot, len(changes)))
    return np.median(changes[picks], axis=1)


def signed_rank_p_many(samples: np.ndarray) -> np.ndarray:
    """Two-sided p of the signed-rank test for every row of `samples`. The same values as
    `signed_rank` row by row (a test checks that), but fast enough for the power simulation:
    up to 13 companies the exact distribution is counted over all sign patterns, which is
    what scipy does when values are tied; above that scipy's own vectorised call is quick."""
    n = samples.shape[1]
    if n > 13 or np.any(samples == 0):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return wilcoxon(samples, axis=1, zero_method="wilcox", method="auto").pvalue
    ranks = rankdata(np.abs(samples), axis=1)
    observed = (ranks * (samples > 0)).sum(axis=1)[:, None]
    signs = ((np.arange(2**n)[:, None] >> np.arange(n)) & 1).astype(float)
    every = ranks @ signs.T  # rank sum of the positives under each sign pattern
    lower = (every <= observed + 1e-9).mean(axis=1)
    upper = (every >= observed - 1e-9).mean(axis=1)
    return np.minimum(1.0, 2 * np.minimum(lower, upper))


def simulated_power(
    changes: np.ndarray, shift: float, rng: np.random.Generator, n_sims: int
) -> float:
    """Power against a median change of `shift` (log terms): the observed changes are centred
    on 0, shifted and resampled."""
    centred = changes - np.median(changes)
    samples = rng.choice(centred, size=(n_sims, len(centred)), replace=True) + shift
    rejected = 0
    for start in range(0, n_sims, 500):
        rejected += int((signed_rank_p_many(samples[start : start + 500]) < common.ALPHA).sum())
    return rejected / n_sims


def minimum_detectable_fall(
    changes: np.ndarray, rng: np.random.Generator, n_sims: int = 2000
) -> tuple[float, float]:
    """Smallest fall, in percent (a negative number), found with 80% power."""
    grid = [round(0.01 * step, 2) for step in range(1, 301)]
    shift, power = common.first_with_power(
        grid, lambda value: simulated_power(changes, -value, rng, n_sims)
    )
    return (-math.inf if math.isinf(shift) else to_percent(-shift)), power


def analyse(
    changes: np.ndarray,
    test_id: str,
    label: str,
    role: str,
    *,
    n_boot: int = common.N_BOOTSTRAP,
    with_mde: bool = True,
) -> Outcome:
    changes = np.asarray(changes, dtype=float)
    if len(changes) < common.MIN_COMPANIES or np.all(changes == 0):
        return common.not_enough(
            STUDY, test_id, label, role, len(changes), "fewer than 5 companies"
        )
    statistic, p_raw = signed_rank(changes)
    low, high = common.percentile_interval(
        bootstrap_median(changes, n_boot, common.generator(2, 1))
    )
    outcome = Outcome(
        STUDY,
        test_id,
        label,
        role,
        n=len(changes),
        n_note="companies",
        statistic_name="Wilcoxon W",
        statistic=statistic,
        p_raw=p_raw,
        effect_name="median change, %",
        effect=to_percent(float(np.median(changes))),
        ci_low=to_percent(low),
        ci_high=to_percent(high),
        practical_effect=PRACTICAL_PCT,
        note=f"{int((changes < 0).sum())} of {len(changes)} companies fell",
    )
    if with_mde:
        outcome.mde, power = minimum_detectable_fall(changes, common.generator(2, 2))
        outcome.mde_note = (
            "no fall can reach p < 0.05 with this many companies"
            if math.isinf(outcome.mde)
            else f"median fall in %, simulated power {power:.2f}"
        )
    return outcome


def by_sector(
    frame: pd.DataFrame, prefix: str, label: str, role: str, *, with_mde: bool = True
) -> list[Outcome]:
    """The test on all companies and on each sector group. `frame`: sector_group, log_change."""
    outcomes = [
        analyse(
            frame["log_change"].to_numpy(float),
            f"{prefix}_all",
            f"{label}, all companies",
            role,
            with_mde=with_mde,
        )  # fmt: skip
    ]
    for sector, rows in sorted(frame.groupby("sector_group"), key=lambda item: str(item[0])):
        slug = str(sector).lower().replace("-", "_").replace(" ", "_")
        outcomes.append(
            analyse(
                rows["log_change"].to_numpy(float),
                f"{prefix}_{slug}",
                f"{label}, {sector}",
                role,
                with_mde=with_mde,
            )  # fmt: skip
        )
    return outcomes


def pair_changes(status: pd.DataFrame, from_year: str, to_year: str) -> pd.DataFrame:
    """One row per company with an intensity in both years and no comparability break in the
    later one: the change in log intensity and whether both years are confirmed."""
    first = status[status["fiscal_year_label"] == from_year]
    second = status[status["fiscal_year_label"] == to_year]
    pairs = first.merge(second, on="isin", suffixes=("_from", "_to"))
    pairs = pairs[~pairs["has_comparability_break_to"].astype(bool)]
    return pd.DataFrame(
        {
            "isin": pairs["isin"],
            "sector_group": pairs["sector_group_to"],
            "log_change": np.log(pairs["intensity_to"].astype(float))
            - np.log(pairs["intensity_from"].astype(float)),
            "is_confirmed": pairs["is_confirmed_from"] & pairs["is_confirmed_to"],
        }
    )


def run(con: duckdb.DuckDBPyConnection, *, with_mde: bool = True) -> list[Outcome]:
    status = data.ghg_status(con)
    panel = data.panel(con)
    confirmed_years = sorted(status.loc[status["is_confirmed"], "fiscal_year_label"].unique())
    all_years = data.years(con)
    label = "change in log GHG intensity"
    if len(confirmed_years) == 0 or all_years.index(confirmed_years[-1]) == 0:
        return [common.not_enough(STUDY, "s2_all", label, common.PRIMARY, 0, "no confirmed pair")]
    to_year = confirmed_years[-1]
    from_year = all_years[all_years.index(to_year) - 1]
    pairs = pair_changes(status, from_year, to_year).merge(
        panel[["isin", "needs_review"]], on="isin", how="left"
    )
    in_panel = pairs["needs_review"].notna()
    flagged = pairs["needs_review"].fillna(False).astype(bool)

    primary = pairs[pairs["is_confirmed"] & in_panel & ~flagged]
    outcomes = by_sector(
        primary, "s2", f"{from_year} to {to_year}, confirmed", common.PRIMARY, with_mde=with_mde
    )
    outcomes += by_sector(
        pairs[pairs["is_confirmed"]], "s2_sens_all_confirmed",
        f"{from_year} to {to_year}, every confirmed pair", common.SENSITIVITY, with_mde=False,
    )  # fmt: skip

    long_view = panel.assign(
        log_change=np.log(panel["intensity_latest"].astype(float))
        - np.log(panel["intensity_first"].astype(float))
    )
    long_view = long_view[np.isfinite(long_view["log_change"])]
    outcomes += by_sector(
        long_view, "s2_sens_long", f"{all_years[0]} to {all_years[-1]}, unconfirmed included",
        common.SENSITIVITY, with_mde=False,
    )  # fmt: skip
    return outcomes
