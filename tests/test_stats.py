"""The statistics studies (Week 11): the methods find a planted effect and keep their
false-positive rate on made-up data, every study runs on synthetic gold tables and on a
one-company warehouse, the data rules agree with the Week 10 analysis, and the published
findings follow the pre-registration and the publication policy."""

from __future__ import annotations

import math
import re
import warnings

import duckdb
import numpy as np
import pandas as pd
import pytest
from scipy.stats import mannwhitneyu, wilcoxon
from test_analysis import (
    MONEY,
    RAW_VALUE,
    ROOT,
    WAREHOUSE,
    YEARS,
    build_synthetic_gold,
    synthetic_frames,
)

from analysis.stats import (
    common,
    data,
    run,
    s1_dqs_ghg,
    s2_decarbonisation,
    s3_restatements,
    s4_assurance,
    s5_ownership,
    validate,
)

HYPOTHESES = ROOT / "docs" / "stats_hypotheses.md"
FINDINGS = ROOT / "docs" / "stats_findings.md"
STUDY_NAMES = sorted(run.STUDIES)

# ------------------------------------------------------------------ method validation


@pytest.mark.parametrize("check", validate.CHECKS, ids=lambda check: check.name)
def test_method_finds_a_planted_effect(check):
    assert validate.power(check) >= 0.70, check.description


@pytest.mark.parametrize("check", validate.CHECKS, ids=lambda check: check.name)
def test_method_keeps_its_false_positive_rate(check):
    """500 data sets with no effect: about 5% false alarms. An exact test on counts may stay
    below 5% (it is conservative by construction) but never above."""
    rate = validate.false_positive_rate(check)
    lowest = 0.0 if check.exact else 0.025
    assert lowest <= rate <= 0.085, f"{check.description}: {rate:.3f}"


def test_binomial_test_alone_is_not_enough_when_restatements_cluster():
    """Why Study 3 has a clustering check: on clustered data with no effect the plain binomial
    test raises far too many false alarms, the cluster bootstrap does not."""
    naive = next(c for c in validate.NAIVE_UNDER_CLUSTERING if c.name.startswith("s3"))
    assert validate.false_positive_rate(naive, runs=300) > 0.15


# ------------------------------------------------------------------ the pieces


def test_benjamini_hochberg_over_the_primary_tests_only():
    def outcome(test_id: str, role: str, p_raw: float, status: str = common.OK):
        return common.Outcome("s", test_id, test_id, role, status=status, p_raw=p_raw)

    outcomes = [
        outcome("a", common.PRIMARY, 0.01),
        outcome("b", common.PRIMARY, 0.04),
        outcome("c", common.PRIMARY, 0.03),
        outcome("d", common.SENSITIVITY, 0.001),
        outcome("e", common.PRIMARY, 0.5, status=common.NOT_ENOUGH_DATA),
    ]
    common.adjust_primary(outcomes)
    assert [o.p_bh for o in outcomes[:3]] == pytest.approx([0.03, 0.04, 0.04])
    assert outcomes[3].p_bh is None and outcomes[4].p_bh is None
    assert [o.rejects_h0 for o in outcomes] == [True, True, True, None, None]


def test_likely_underpowered_needs_a_null_result_and_a_large_mde():
    base = {"study": "s", "test_id": "t", "label": "t", "role": common.PRIMARY, "p_raw": 0.5}
    weak = common.Outcome(**base, p_bh=0.5, mde=0.6, practical_effect=0.3)
    strong = common.Outcome(**base, p_bh=0.5, mde=0.2, practical_effect=0.3)
    found = common.Outcome(**base, p_bh=0.01, mde=0.6, practical_effect=0.3)
    assert weak.likely_underpowered is True
    assert strong.likely_underpowered is False
    assert found.likely_underpowered is None


def test_first_with_power_returns_the_smallest_effect_that_reaches_80_percent():
    grid = [0.1, 0.2, 0.3, 0.4, 0.5]
    assert common.first_with_power(grid, lambda effect: 2 * effect) == (0.4, 0.8)
    assert math.isinf(common.first_with_power(grid, lambda effect: effect)[0])


def test_pooled_rho_weights_groups_by_size():
    up = (np.arange(6.0), np.arange(6.0))  # rho = +1, weight 5
    down = (np.arange(3.0), -np.arange(3.0))  # rho = -1, weight 2
    assert s1_dqs_ghg.pooled_rho([up]) == pytest.approx(1.0)
    assert s1_dqs_ghg.pooled_rho([up, down]) == pytest.approx((5 - 2) / 7)
    flat = (np.ones(6), np.arange(6.0))
    assert s1_dqs_ghg.usable_groups([up, down, flat], min_n=5) == [up]


def test_stratified_permutation_keeps_group_levels_out_of_the_test():
    """Two groups at very different levels, no association inside them: a naive pooled
    correlation would be large, the stratified one is not."""
    rng = np.random.default_rng(3)
    low = (rng.normal(60, 1, 12), rng.normal(0, 1, 12))
    high = (rng.normal(90, 1, 12), rng.normal(8, 1, 12))
    naive = s1_dqs_ghg.spearman(
        np.concatenate([low[0], high[0]]), np.concatenate([low[1], high[1]])
    )
    rho, p_value = s1_dqs_ghg.permutation_test([low, high], 999, rng)
    assert naive > 0.6 and abs(rho) < 0.5 and p_value > 0.05


def test_fast_signed_rank_equals_scipy():
    rng = np.random.default_rng(5)
    for n in (5, 8, 12, 20):
        base = rng.standard_normal(n) * 0.1
        samples = rng.choice(base, size=(40, n)) - 0.04  # resampled, so with ties
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            expected = [
                wilcoxon(row, zero_method="wilcox", method="auto").pvalue for row in samples
            ]
        assert s2_decarbonisation.signed_rank_p_many(samples) == pytest.approx(expected, abs=1e-12)


def test_five_companies_can_never_reach_significance_with_the_signed_rank_test():
    """Said plainly in the findings: with 5 companies the smallest possible p is 0.0625."""
    outcome = s2_decarbonisation.analyse(
        np.array([-0.5, -0.4, -0.3, -0.2, -0.1]), "t", "t", common.PRIMARY, n_boot=200
    )
    assert outcome.p_raw == pytest.approx(0.0625)
    assert outcome.mde == -math.inf


def test_minimum_detectable_share_shrinks_with_more_restatements():
    small = s3_restatements.minimum_detectable_distance(50)
    large = s3_restatements.minimum_detectable_distance(240)
    assert 0 < large < small < 0.5
    assert large == pytest.approx(0.09, abs=0.01)  # 1.4 / sqrt(240), the textbook value


def test_fisher_table_and_odds_ratio_direction():
    frame = pd.DataFrame(
        {
            "isin": [f"C{i}" for i in range(40)],
            "fiscal_year_label": "FY2024-25",
            "assurance_scope": ["all"] * 20 + ["partial"] * 20,
            "restated": [True] * 4 + [False] * 16 + [True] * 14 + [False] * 6,
            "n_material": [1] * 4 + [0] * 16 + [1] * 14 + [0] * 6,
            "n_compared": 20,
        }
    )
    assert s4_assurance.two_by_two(frame).tolist() == [[4, 16], [14, 6]]
    (outcome,) = s4_assurance.analyse(frame, "t", "t", common.PRIMARY, with_mde=False)
    assert outcome.effect < 1 and outcome.ci_high < 1 and outcome.p_raw < 0.01
    assert outcome.statistic == pytest.approx(-50.0)


def test_stratified_cliffs_delta_equals_mann_whitney_within_a_year():
    rng = np.random.default_rng(7)
    scores = rng.normal(85, 5, size=(30, 1))
    labels = np.array([1.0] * 8 + [0.0] * 22)
    wins, pairs = s5_ownership.pair_matrices(scores)
    delta = s5_ownership.stratified_delta(wins, pairs, labels)[0]
    u = mannwhitneyu(scores[:8, 0], scores[8:, 0]).statistic
    assert delta == pytest.approx(2 * u / (8 * 22) - 1)


def test_stratified_cliffs_delta_never_compares_across_years():
    """Every PSU is below every private company in its own year, although the PSU scores of
    the second year are above all private scores of the first."""
    scores = np.array([[50.0, 80.0], [51.0, 81.0], [60.0, 90.0], [61.0, np.nan]])
    labels = np.array([1.0, 1.0, 0.0, 0.0])
    wins, pairs = s5_ownership.pair_matrices(scores)
    assert s5_ownership.stratified_delta(wins, pairs, labels)[0] == pytest.approx(-1.0)
    assert pairs[np.ix_([0, 1], [2, 3])].sum() == 6  # 4 pairs in year one, 2 in year two


# ------------------------------------------------------------------ synthetic gold tables


def stats_frames() -> dict[str, pd.DataFrame]:
    """The synthetic gold tables of the Week 10 tests, with what the studies need on top: a
    later report that confirms most Scope 1 and 2 figures, restatements with a direction, and
    an assurance scope in the two middle years."""
    frames = synthetic_frames()
    company_years = frames["fct_company_year"].reset_index(drop=True)
    company = company_years["isin"].str[4:6].astype(int)
    year = company_years["fiscal_year_label"].map(YEARS.index)

    scores = frames["fct_disclosure_quality"].reset_index(drop=True)
    assured = year.isin([1, 2])
    scores["assurance_level"] = np.where(assured, "reasonable", None)
    scores["assurance_scope"] = np.where(
        assured, np.where(company % 2 == 0, "all", "partial"), None
    )
    frames["fct_disclosure_quality"] = scores

    rows = []
    for index, row in company_years[year < len(YEARS) - 1].iterrows():
        c, y = company[index], year[index]
        inferred = c == 1 and y == 0
        for metric in ("ghg_scope1_tco2e", "ghg_scope2_tco2e"):
            rows.append(
                (
                    row,
                    metric,
                    "unit_inferred_from_restating_filing" if inferred else "no_change",
                    None,
                )
            )
        for m, metric in enumerate(("water_consumption_kl", "waste_generated_t", "ltifr")):
            material = (index + m + c) % 3 == 0
            rows.append(
                (
                    row,
                    metric,
                    "material" if material else "no_change",
                    (index + m) % 2 == 0 if material else None,
                )
            )
    frames["fct_restatement"] = pd.DataFrame(
        [
            {
                "isin": row["isin"],
                "symbol": row["symbol"],
                "metric_id": metric,
                "dimension_key": "",
                "value_fiscal_year_label": row["fiscal_year_label"],
                "restating_filing_id": f"R{number}",
                "classification": classification,
                "is_compared": classification != "unit_inferred_from_restating_filing",
                "flatters_trend": flatters,
            }
            for number, (row, metric, classification, flatters) in enumerate(rows)
        ]
    )
    return frames


def one_company_year(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """What CI has: a warehouse with a single company in a single year."""
    isin = frames["fct_company_year"]["isin"].iloc[0]
    kept = {}
    for table, frame in frames.items():
        rows = frame[frame["isin"] == isin]
        for column in ("fiscal_year_label", "value_fiscal_year_label"):
            if column in rows.columns:
                rows = rows[rows[column] == YEARS[-1]]
        kept[table] = rows
    assert len(kept["fct_company_year"]) == 1
    return kept


@pytest.fixture(scope="module")
def synthetic_outcomes() -> list[common.Outcome]:
    con = duckdb.connect(":memory:")
    try:
        build_synthetic_gold(con, stats_frames())
        return run.run_studies(con, with_mde=False)
    finally:
        con.close()


@pytest.mark.parametrize("study", STUDY_NAMES)
def test_every_study_runs_on_synthetic_gold_tables(study, synthetic_outcomes):
    outcomes = [o for o in synthetic_outcomes if o.study == study]
    primary = [o for o in outcomes if o.role == common.PRIMARY and o.status == common.OK]
    assert primary, f"{study}: no primary test could be run on the synthetic tables"
    for outcome in primary:
        assert outcome.n >= common.MIN_COMPANIES
        assert 0 < outcome.p_raw <= 1 and 0 < outcome.p_bh <= 1
        assert outcome.p_bh >= outcome.p_raw - 1e-12
        assert outcome.effect is not None and outcome.ci_low <= outcome.ci_high
    assert len({o.test_id for o in synthetic_outcomes}) == len(synthetic_outcomes)


def test_primary_analyses_leave_unconfirmed_data_out(synthetic_outcomes):
    con = duckdb.connect(":memory:")
    try:
        build_synthetic_gold(con, stats_frames())
        status, panel = data.ghg_status(con), data.panel(con)
    finally:
        con.close()
    # the fixture's planted cases carry the right label
    assert set(status.loc[status["fiscal_year_label"] == YEARS[-1], "status"]) == {"provisional"}
    assert "inferred_unit" in set(status["status"])
    assert (
        status["is_reversal_year"].any()
        and not status.loc[status["is_reversal_year"], "is_confirmed"].any()
    )
    assert panel["needs_review"].any() and not panel["needs_review"].all()
    # so the primary tests run on fewer companies than the sensitivity ones that add them back
    by_id = {o.test_id: o for o in synthetic_outcomes}
    assert by_id["s1_pooled"].n < by_id["s1_sens_unconfirmed"].n
    assert by_id["s2_all"].n < by_id["s2_sens_long_all"].n
    assert YEARS[-1] not in by_id["s2_all"].label and YEARS[-1] in by_id["s2_sens_long_all"].label


def test_no_group_below_five_companies_is_tested(synthetic_outcomes):
    for outcome in synthetic_outcomes:
        if outcome.status == common.OK:
            assert outcome.n >= common.MIN_COMPANIES, outcome.test_id
        else:
            assert outcome.p_raw is None and outcome.effect is None, outcome.test_id
    assert any(o.status == common.NOT_ENOUGH_DATA for o in synthetic_outcomes)


def test_runner_writes_results_and_fails_without_data_unless_allowed(tmp_path, capsys):
    full, tiny = tmp_path / "full.duckdb", tmp_path / "tiny.duckdb"
    for path, frames in ((full, stats_frames()), (tiny, one_company_year(stats_frames()))):
        con = duckdb.connect(str(path))
        build_synthetic_gold(con, frames)
        con.close()

    out = tmp_path / "out"
    assert run.main(["--db", str(full), "--out", str(out), "--no-mde"]) == 0
    written = pd.read_csv(out / "stats_results.csv")
    assert set(written["study"]) == set(STUDY_NAMES)
    assert {"n", "statistic", "p_raw", "p_bh", "effect", "ci_low", "ci_high", "mde"} <= set(written)

    # the warehouse CI builds holds one company-year: every study says so, none invents a number
    assert run.main(["--db", str(tiny), "--out", str(out)]) == 1
    assert run.main(["--db", str(tiny), "--out", str(out), "--allow-empty"]) == 0
    written = pd.read_csv(out / "stats_results.csv")
    assert set(written["study"]) == set(STUDY_NAMES)
    assert (written["status"] == common.NOT_ENOUGH_DATA).all()
    assert written[["p_raw", "effect"]].isna().all().all()
    assert "not enough data" in capsys.readouterr().out


def test_same_seed_same_result():
    groups = [(np.arange(8.0), np.array([3.0, 1, 4, 1.5, 5, 9, 2, 6]))] * 2
    first = s1_dqs_ghg.analyse(
        groups, "t", "t", common.PRIMARY, n_perm=500, n_boot=500, with_mde=False
    )
    second = s1_dqs_ghg.analyse(
        groups, "t", "t", common.PRIMARY, n_perm=500, n_boot=500, with_mde=False
    )
    assert (first.p_raw, first.ci_low, first.ci_high) == (
        second.p_raw,
        second.ci_low,
        second.ci_high,
    )


# ------------------------------------------------------------------ agreement with Week 10


@pytest.fixture(scope="module")
def warehouse():
    if not WAREHOUSE.exists():
        pytest.skip("needs the real warehouse (dev.ps1 dbt-build)")
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        if not con.sql(
            "select 1 from information_schema.tables where table_name = 'fct_restatement'"
        ).fetchall():
            pytest.skip("the warehouse has no gold tables")
        if con.sql("select count(distinct isin) from fct_company_year").fetchone()[0] < 40:
            pytest.skip("not the real warehouse")
        yield con
    finally:
        con.close()


def test_confirmed_rule_is_the_one_of_q3_and_q5(warehouse):
    """The studies must not have their own idea of "confirmed" or "needs review"."""
    from test_analysis import QUERIES, RUNNER

    wanted = [q for q in QUERIES if q.file.startswith(("q03", "q05", "q09"))]
    results = RUNNER.run_queries(warehouse, wanted)

    status = data.ghg_status(warehouse)
    names = dict(warehouse.sql("select isin, display_name from fct_company_year").fetchall())
    status["display_name"] = status["isin"].map(names)
    q3 = results["q03_ghg_leaders_laggards__yoy_changes_with_confidence"]
    compared = 0
    for row in q3.to_dict("records"):
        pair = status[
            (status["display_name"] == row["display_name"])
            & status["fiscal_year_label"].isin([row["from_year"], row["to_year"]])
        ]
        assert len(pair) == 2
        assert bool(pair["is_confirmed"].all()) == (row["confidence"] == "confirmed"), row
        compared += 1
    assert compared == len(q3) > 50

    panel = data.panel(warehouse)
    q5 = results["q05_decoupling__decoupling_by_company"]
    assert len(panel) == len(q5)
    assert int(panel["needs_review"].sum()) == int((q5["decoupling_class"] == "needs_review").sum())

    q9 = results["q09_restatements__restatements_by_year"]
    total = q9[q9["year_of_the_value"] == "All years"].iloc[0]
    directions = data.restatement_directions(warehouse)
    assert len(directions) == total["n_material_with_direction"]
    assert int(directions["flatters_trend"].sum()) == total["n_flattering"]


# ------------------------------------------------------------------ the published pages

STUDY_HEADINGS = [
    "## Study 1. Disclosure quality and carbon intensity",
    "## Study 2. Is GHG intensity falling?",
    "## Study 3. Do restatements flatter the trend?",
    "## Study 4. Assurance of the whole report and later restatement",
    "## Study 5. Ownership and disclosure quality",
]
CAUSAL = re.compile(
    r"\b(causes|caused|causing|leads? to|led to|because of|due to|drives|driven by|"
    r"thanks to|brings? about)\b",
    re.IGNORECASE,
)


def test_hypotheses_fix_every_choice_for_every_study():
    text = HYPOTHESES.read_text(encoding="utf-8")
    for heading in STUDY_HEADINGS:
        section = text.split(heading, 1)[1].split("\n## ", 1)[0]
        for part in ("| H0 |", "| H1 |", "| Unit |", "| Filter |", "| Effect size |", "| MDE |"):
            assert part in section, f"{heading}: no {part}"
        assert "Primary test" in section and "Effect of practical interest" in section
    assert "Benjamini-Hochberg" in text and "alpha = 0.05" in text
    assert str(common.SEED) in text


def test_findings_report_every_study_in_full():
    text = FINDINGS.read_text(encoding="utf-8")
    for heading in STUDY_HEADINGS:
        section = text.split(heading, 1)[1].split("\n## ", 1)[0]
        for label in ("**Question.**", "**Answer.**", "**What it means.**", "**Limitations.**"):
            assert label in section, f"{heading}: no {label}"
        for column in ("| n |", "raw p", "BH p", "95% interval", "Minimum detectable"):
            assert column in section, f"{heading}: the result table has no '{column}'"
    for heading in ("## How to read p-values and intervals", "## Against pre-registration"):
        assert heading in text
    assert "stats_hypotheses.md" in text


def test_findings_follow_the_publication_policy_and_make_no_causal_claim():
    text = FINDINGS.read_text(encoding="utf-8")
    raw = [match.group(0) for match in RAW_VALUE.finditer(text)]
    assert not raw, f"raw filed quantities in the findings: {raw}"
    assert not [match.group(0) for match in MONEY.finditer(text)]
    assert "nseindia" not in text.lower() and "http" not in text.lower()
    assert "not an ESG rating" in text and "not investment advice" in text
    causal = [match.group(0) for match in CAUSAL.finditer(text)]
    assert not causal, f"causal wording in the findings: {causal}"
    assert "associated with" in text
