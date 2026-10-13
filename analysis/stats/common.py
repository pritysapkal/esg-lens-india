"""Shared pieces of the Week 11 statistics studies: the fixed choices of the pre-registration
(docs/stats_hypotheses.md), the result record, and the Benjamini-Hochberg adjustment."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
from statsmodels.stats.multitest import multipletests

SEED = 20261013
ALPHA = 0.05
POWER = 0.80
N_PERMUTATIONS = 10_000
N_BOOTSTRAP = 10_000
MIN_COMPANIES = 5

PRIMARY = "primary"
SENSITIVITY = "sensitivity"
DESCRIPTIVE = "descriptive"
OK = "ok"
NOT_ENOUGH_DATA = "not_enough_data"


@dataclass
class Outcome:
    """One test (or one descriptive row) of a study."""

    study: str  # s1 ... s5
    test_id: str  # unique, e.g. s2_asset_heavy
    label: str  # plain-English name
    role: str  # primary | sensitivity | descriptive
    status: str = OK  # ok | not_enough_data
    n: int | None = None  # units of analysis
    n_note: str = ""  # what the units are, clusters, groups
    statistic_name: str = ""
    statistic: float | None = None
    p_raw: float | None = None
    p_bh: float | None = None  # filled by the runner, primary tests only
    effect_name: str = ""
    effect: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    mde: float | None = None  # same unit as the effect; inf = cannot be detected at this n
    mde_note: str = ""
    practical_effect: float | None = None  # effect of practical interest (pre-registered)
    note: str = ""

    def as_row(self) -> dict[str, object]:
        return asdict(self)

    @property
    def rejects_h0(self) -> bool | None:
        """Decision rule of the pre-registration; only primary tests get a decision."""
        if self.role != PRIMARY or self.status != OK or self.p_bh is None:
            return None
        return self.p_bh < ALPHA

    @property
    def likely_underpowered(self) -> bool | None:
        """A null result whose minimum detectable effect is above the effect of interest."""
        if self.rejects_h0 is not False or self.mde is None or self.practical_effect is None:
            return None
        return abs(self.mde) > self.practical_effect


def not_enough(study: str, test_id: str, label: str, role: str, n: int, note: str) -> Outcome:
    return Outcome(study, test_id, label, role, status=NOT_ENOUGH_DATA, n=n, note=note)


def generator(*stream: int) -> np.random.Generator:
    """A random generator from the one project seed. `stream` keeps the steps of a study
    (permutation, bootstrap, power simulation) independent of each other."""
    return np.random.default_rng([SEED, *stream])


def adjust_primary(outcomes: list[Outcome]) -> None:
    """Benjamini-Hochberg over all primary tests that were run (in place)."""
    family = [o for o in outcomes if o.role == PRIMARY and o.status == OK and o.p_raw is not None]
    if not family:
        return
    adjusted = multipletests([o.p_raw for o in family], alpha=ALPHA, method="fdr_bh")[1]
    for outcome, p_bh in zip(family, adjusted, strict=True):
        outcome.p_bh = float(p_bh)


def permutation_p(observed: float, permuted: np.ndarray) -> float:
    """Two-sided permutation p-value with the +1 correction (never exactly 0)."""
    extreme = np.sum(np.abs(permuted) >= abs(observed) - 1e-12)
    return float((1 + extreme) / (1 + len(permuted)))


def percentile_interval(values: np.ndarray) -> tuple[float, float]:
    low, high = np.nanpercentile(values, [2.5, 97.5])
    return float(low), float(high)


def first_with_power(grid: list[float], power_at) -> tuple[float, float]:
    """Smallest effect on `grid` (ascending in size) whose power reaches 80%, by bisection
    (power grows with the effect). Returns (effect, power), or (inf, power at the largest)."""
    top = power_at(grid[-1])
    if top < POWER:
        return math.inf, top
    low, high, best = 0, len(grid) - 1, (grid[-1], top)
    while low < high:
        middle = (low + high) // 2
        power = power_at(grid[middle])
        if power >= POWER:
            high, best = middle, (grid[middle], power)
        else:
            low = middle + 1
    return best
