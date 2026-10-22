"""The fixed set of tools the AI analyst may call: parameterised, tested queries over the public
tables (app/data.py). No free-form SQL, no other data. Every argument is checked against the
allowed values before a query runs; a bad argument comes back to the model as an error.

Allowed values (companies, years, groups, metrics) are read from the public tables themselves,
so the tool schemas always match the data shipped with the app.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache

import pandas as pd

from app import data, labels


class ToolArgumentError(ValueError):
    """An argument the tool does not accept. The message is shown to the model."""


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict  # JSON Schema properties
    required: tuple[str, ...]
    run: Callable[..., dict]

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.required),
                "additionalProperties": False,
            },
            "strict": True,
        }


# ------------------------------------------------------------------ allowed values


@lru_cache(maxsize=1)
def allowed() -> dict[str, list[str]]:
    groups = data.table("rpt_public_group_metrics")
    companies = data.companies()
    percentiles = data.table("rpt_public_company_percentile")
    return {
        "years": data.years(),
        "companies": companies["display_name"].tolist(),
        "symbols": companies["symbol"].tolist(),
        "metrics": list(labels.GROUP_METRICS),
        "group_types": list(labels.GROUP_TYPES),
        "group_values": sorted(groups["group_value"].dropna().unique()),
        "ranking_groups": sorted(groups.loc[groups["group_type"] == "ranking_group", "group_value"].unique()),
        "kpis": sorted(percentiles["kpi_name"].dropna().unique()),
        "restatement_levels": sorted(data.table("rpt_public_restatement_summary")["level"].unique()),
    }  # fmt: skip


def _one_of(name: str, value, options: list[str]) -> str:
    if not isinstance(value, str) or value not in options:
        shown = ", ".join(options[:15]) + (" ..." if len(options) > 15 else "")
        raise ToolArgumentError(f"{name}={value!r} is not allowed. Allowed: {shown}")
    return value


def _company(value) -> pd.Series:
    """A company by display name or NSE symbol."""
    companies = data.companies()
    if isinstance(value, str):
        for column in ("display_name", "symbol"):
            match = companies[companies[column].str.casefold() == value.casefold()]
            if not match.empty:
                return match.iloc[0]
    raise ToolArgumentError(
        f"company={value!r} is not one of the {len(companies)} companies covered "
        "(NIFTY 50 plus Wipro). Use the display name, for example 'HDFC Bank'."
    )


def _integer(name: str, value, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ToolArgumentError(f"{name} must be a whole number from {low} to {high}")
    return value


def _clean(value):
    if labels.is_missing(value):
        return None
    if isinstance(value, float):
        return round(value, 4) if math.isfinite(value) else None
    if hasattr(value, "item"):
        return _clean(value.item())
    return value


def _records(frame: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in frame.to_dict("records")]


def _year_notes(years) -> list[str]:
    return [data.provisional_note(year) for year in sorted(set(years)) if data.is_provisional(year)]


# ------------------------------------------------------------------ the tools


def _group_types_of(value) -> list[str]:
    """Every group type that has a group with this value."""
    groups = data.table("rpt_public_group_metrics")
    if not isinstance(value, str):
        return []
    return sorted(groups.loc[groups["group_value"] == value, "group_type"].unique())


def resolve_group(group_type, group_value) -> tuple[str, str | None]:
    """The (group_type, group_value) to query. The type may be left out or be wrong: it is then
    taken from the value when only one group type has that value. Otherwise a clear error."""
    types = allowed()["group_types"]
    if group_value is None:
        if group_type is None:
            raise ToolArgumentError(
                "give group_type (to list all its groups) or group_value. "
                f"Group types: {', '.join(types)}"
            )
        _one_of("group_type", group_type, types)
        return group_type, None
    matching = _group_types_of(group_value)
    if not matching:
        _one_of("group_value", group_value, allowed()["group_values"])
    if group_type in matching:
        return group_type, group_value
    if group_type is not None and group_type not in types:
        _one_of("group_type", group_type, types)
    if len(matching) == 1:
        return matching[0], group_value
    listed = ", ".join(matching)
    wrong = f"'{group_value}' is not a {group_type}; it is" if group_type else f"'{group_value}' is"
    raise ToolArgumentError(
        f"{wrong} a group in several group types ({listed}). Say which with group_type."
    )


def _other_type_hint(name: str, value, own_types: list[str], found_in: list[str]) -> str:
    """'X' is a peer_group, not a ranking_group - for an argument that holds a group of the wrong kind."""
    if found_in:
        return f" '{value}' is a {' / '.join(found_in)}, not a {' / '.join(own_types)}."
    return ""


def group_metric(
    metric: str,
    group_type: str | None = None,
    group_value: str | None = None,
    year: str | None = None,
) -> dict:
    a = allowed()
    _one_of("metric", metric, a["metrics"])
    asked_type = group_type
    group_type, group_value = resolve_group(group_type, group_value)
    groups = data.table("rpt_public_group_metrics")
    rows = groups[groups["group_type"] == group_type]
    if group_value is not None:
        rows = rows[rows["group_value"] == group_value]
    if year is not None:
        _one_of("year", year, a["years"])
        rows = rows[rows["fiscal_year_label"] == year]
    label, unit, gate, _restatement = labels.GROUP_METRICS[metric]
    out = []
    for _, row in rows.sort_values(["group_value", "fiscal_year_label"]).iterrows():
        shown = labels.group_cell(row, metric)
        out.append(
            {
                "group": row["group_value"],
                "year": row["fiscal_year_label"],
                "value": _clean(shown) if not isinstance(shown, str) else None,
                "status": "shown" if not isinstance(shown, str) else shown,
                "companies_behind_it": _clean(row[gate]) if gate else _clean(row[metric]),
            }
        )
    notes = _year_notes(r["year"] for r in out)
    if asked_type is not None and asked_type != group_type:
        notes.append(f"'{group_value}' is a {group_type}, not a {asked_type}: {group_type} used.")
    if any(r["status"].startswith("n<5") for r in out):
        notes.append(
            "n<5 (withheld): fewer than 5 companies stand behind the figure, so it is not published."
        )
    if any(r["status"] == "not yet observable" for r in out):
        notes.append(
            "not yet observable: restatements of the latest year appear only in the next report."
        )
    if metric.endswith("_agg"):
        notes.append(
            "Whole group = sum over sum of the companies that have both figures (large companies weigh more)."
        )
    if metric.endswith("_median"):
        notes.append("Typical company = the median company of the group.")
    return {
        "metric": metric,
        "label": label,
        "unit": unit,
        "group_type": group_type,
        "rows": out,
        "notes": notes,
        "source": "rpt_public_group_metrics",
    }


def company_card(company: str, year: str) -> dict:
    row = _company(company)
    _one_of("year", year, allowed()["years"])
    dqs = data.table("rpt_public_disclosure_quality")
    dq = dqs[(dqs["isin"] == row["isin"]) & (dqs["fiscal_year_label"] == year)]
    cy = data.table("rpt_public_company_year")
    kpis = cy[(cy["isin"] == row["isin"]) & (cy["fiscal_year_label"] == year)]
    if dq.empty and kpis.empty:
        raise ToolArgumentError(f"{row['display_name']} has no report for {year} in the data")
    card = {"company": row["display_name"], "symbol": row["symbol"], "year": year,
            "ranking_group": row["ranking_group"], "sector_group": row["sector_group"]}  # fmt: skip
    if not dq.empty:
        d = dq.iloc[0]
        card |= {
            "dqs_total": _clean(d["dqs_total"]),
            "dqs_grade": _clean(d["dqs_grade"]),
            "dqs_rank_in_group": _clean(d["dqs_rank_in_group"]),
            "dqs_group_n": _clean(d["dqs_group_n"]),
            "dqs_percentile_in_group": _clean(d["dqs_percentile_in_group"]),
            "is_provisional": bool(d["is_provisional"]),
            "assurance_level": _clean(d["assurance_level"]),
            "assurance_scope": _clean(d["assurance_scope"]),
            "reasons_points_were_lost": labels.reason_codes(d["dqs_reason_codes"]),
        }
    if not kpis.empty:
        k = kpis.iloc[0]
        for column in ("ghg_intensity_tco2e_per_cr", "energy_intensity_gj_per_cr", "water_intensity_kl_per_cr",
                       "waste_intensity_t_per_cr", "renewable_share_pct", "female_workforce_pct",
                       "pay_equity_gap_pp", "has_comparability_break"):  # fmt: skip
            card[column] = _clean(k[column])
    notes = _year_notes([year]) + ["The Disclosure Quality Score is not an ESG rating."]
    return {
        "card": card,
        "notes": notes,
        "source": "rpt_public_disclosure_quality, rpt_public_company_year",
    }


def company_percentiles(company: str, year: str, kpi: str | None = None) -> dict:
    row = _company(company)
    a = allowed()
    _one_of("year", year, a["years"])
    frame = data.table("rpt_public_company_percentile")
    rows = frame[(frame["isin"] == row["isin"]) & (frame["fiscal_year_label"] == year)]
    if kpi is not None:
        _one_of("kpi", kpi, a["kpis"])
        rows = rows[rows["kpi_name"] == kpi]
    out = [
        {
            "kpi": r["kpi_name"],
            "kpi_label": r["kpi_label"],
            "ranking_group": r["ranking_group"],
            "percentile_in_group": _clean(r["percentile_in_group"]),
            "rank_in_group": _clean(r["rank_in_group"]),
            "companies_in_group": _clean(r["n_in_group"]),
            "ranking_status": labels.ranking_status(r["is_ranked"], r["reason_not_ranked"]),
            "value_if_public": _clean(r["kpi_value_public"]),
        }
        for _, r in rows.sort_values("kpi_name").iterrows()
    ]
    notes = _year_notes([year]) + [
        "Percentile 100 = best in the ranking group; rank 1 = best. A filed value is never shown (its value stays empty)."
    ]
    return {
        "company": row["display_name"],
        "year": year,
        "rows": out,
        "notes": notes,
        "source": "rpt_public_company_percentile",
    }


def concentration(year: str, top_n: int = 10) -> dict:
    _one_of("year", year, allowed()["years"])
    top_n = _integer("top_n", top_n, 1, 20)
    frame = data.table("rpt_public_concentration")
    rows = frame[frame["fiscal_year_label"] == year].sort_values("emitter_rank")
    by_rank = rows.set_index("emitter_rank")["cumulative_share_pct"]
    summary = {
        "year": year,
        "companies_with_emissions": int(len(rows)),
        "top_1_share_pct": _clean(by_rank.get(1)),
        "top_5_share_pct": _clean(by_rank.get(5)),
        "top_10_share_pct": _clean(by_rank.get(10)),
        "companies_for_80_pct": int((rows["cumulative_share_pct"] < 80).sum()) + 1,
    }
    largest = _records(
        rows.head(top_n)[
            [
                "emitter_rank",
                "display_name",
                "sector_group",
                "share_of_total_pct",
                "cumulative_share_pct",
            ]
        ]
    )
    notes = _year_notes([year]) + [
        "Shares of the Scope 1+2 emissions of all companies covered that year; tonnes are not published."
    ]
    return {
        "summary": summary,
        "largest_emitters": largest,
        "notes": notes,
        "source": "rpt_public_concentration",
    }


def top_movers_confirmed(direction: str, ranking_group: str | None = None, limit: int = 3) -> dict:
    _one_of("direction", direction, ["improvement", "deterioration"])
    limit = _integer("limit", limit, 1, 10)
    frame = data.table("rpt_public_ghg_yoy")
    if ranking_group is not None:
        # every ranking group the schema offers is accepted; one without GHG year-on-year pairs
        # (e.g. Financials) simply has no movers
        if ranking_group not in allowed()["ranking_groups"]:
            hint = _other_type_hint(
                "ranking_group", ranking_group, ["ranking_group"], _group_types_of(ranking_group)
            )
            if hint:
                raise ToolArgumentError(f"ranking_group={ranking_group!r} is not allowed.{hint}")
        _one_of("ranking_group", ranking_group, allowed()["ranking_groups"])
        frame = frame[frame["ranking_group"] == ranking_group]
    ranked = frame[frame["is_ranked"].astype(bool)].sort_values(
        "change_pct", ascending=direction == "improvement"
    )
    movers = _records(
        ranked.head(limit)[
            [
                "ranking_group",
                "display_name",
                "from_year",
                "to_year",
                "intensity_from",
                "intensity_to",
                "change_pct",
            ]
        ]
    )
    unconfirmed = frame[~frame["is_ranked"].astype(bool)]["confidence"].value_counts()
    notes = [
        "Only year-on-year changes confirmed by the next report, in a group with 5 or more comparable companies, are ranked.",
        "Intensity = Scope 1+2 tCO2e per Rs crore of turnover, computed by ESG Lens India.",
    ]
    return {
        "direction": direction,
        "movers": movers,
        "ranked_pairs": int(len(ranked)),
        "pairs_not_ranked_by_reason": {
            labels.CONFIDENCE.get(k, k): int(v) for k, v in unconfirmed.items()
        },
        "notes": notes,
        "source": "rpt_public_ghg_yoy",
    }


def restatement_summary(level: str, group_key: str | None = None) -> dict:
    _one_of("level", level, allowed()["restatement_levels"])
    frame = data.table("rpt_public_restatement_summary")
    rows = frame[frame["level"] == level]
    if group_key is not None:
        keys = sorted(rows["group_key"].unique())
        if group_key not in keys:
            elsewhere = sorted(frame.loc[frame["group_key"] == group_key, "level"].unique())
            hint = _other_type_hint("group_key", group_key, [level], elsewhere)
            if hint:
                raise ToolArgumentError(
                    f"group_key={group_key!r} is not allowed for this level.{hint}"
                )
        _one_of("group_key", group_key, keys)
        rows = rows[rows["group_key"] == group_key]
    columns = ["level", "group_key", "n_pairs", "n_material", "pct_material", "n_material_flattering",
               "pct_material_flattering", "n_companies", "n_companies_with_material"]  # fmt: skip
    out = _records(rows[columns].head(60))
    # the table withholds the shares of a group of fewer than 5 companies; say so in every row
    for record, reason in zip(out, rows["suppressed_reason"].head(60), strict=True):
        record["status"] = "n<5 (withheld)" if reason == "fewer_than_5_companies" else "shown"
    notes = [
        "A restatement is a difference between two filings, not a finding of wrongdoing.",
        "The latest year has no next report yet, so its restatements are not observable.",
    ]
    if any(r["status"] != "shown" for r in out):
        notes.append(
            "n<5 (withheld): the shares of a group of fewer than 5 companies are not published; the counts are."
        )
    return {
        "rows": out,
        "notes": notes,
        "source": "rpt_public_restatement_summary",
    }


# ------------------------------------------------------------------ registry


def tools() -> list[Tool]:
    a = allowed()
    year = {"type": "string", "enum": a["years"], "description": "Financial year, e.g. FY2024-25."}
    company = {"type": "string", "enum": a["companies"], "description": "Company display name."}
    return [
        Tool("group_metric",
             "A published group figure (whole group, typical company, share or count) by group and year, "
             "from rpt_public_group_metrics. Withheld figures come back with status 'n<5 (withheld)'. "
             "group_type may be null when group_value is given: it is then found from the value (an error "
             "lists the types if several have it). The share of figures restated materially in one year "
             "is the metric material_restatement_share with that year.",
             {"metric": {"type": "string", "enum": a["metrics"]},
              "group_type": {"type": ["string", "null"], "enum": [*a["group_types"], None],
                             "description": "Kind of group; null to find it from group_value."},
              "group_value": {"type": ["string", "null"], "enum": [*a["group_values"], None],
                              "description": "One group, or null for all groups of the type. For the whole set use 'All companies'."},
              "year": {**year, "type": ["string", "null"], "enum": [*a["years"], None]}},
             ("metric", "group_type", "group_value", "year"), group_metric),
        Tool("company_card",
             "One company in one year: Disclosure Quality Score, grade, rank and percentile in its ranking group, "
             "reasons points were lost, assurance, computed intensities and the provisional flag.",
             {"company": company, "year": year}, ("company", "year"), company_card),
        Tool("company_percentiles",
             "A company's percentile (100 = best) and rank in its ranking group for each KPI in one year, with why "
             "a KPI is not ranked (for example not material for the group).",
             {"company": company, "year": year,
              "kpi": {"type": ["string", "null"], "enum": [*a["kpis"], None], "description": "One KPI, or null for all."}},
             ("company", "year", "kpi"), company_percentiles),
        Tool("concentration",
             "How concentrated Scope 1+2 emissions are in one year: top-1/5/10 shares, companies needed for 80%, "
             "and the largest emitters with their shares (no tonnes).",
             {"year": year, "top_n": {"type": "integer", "description": "How many of the largest emitters to list (1-20)."}},
             ("year", "top_n"), concentration),
        Tool("top_movers_confirmed",
             "Largest year-on-year improvements or deteriorations in GHG intensity, counting only changes a later "
             "report confirms. Also says how many changes were set aside and why.",
             {"direction": {"type": "string", "enum": ["improvement", "deterioration"]},
              "ranking_group": {"type": ["string", "null"], "enum": [*a["ranking_groups"], None]},
              "limit": {"type": "integer", "description": "How many movers (1-10)."}},
             ("direction", "ranking_group", "limit"), top_movers_confirmed),
        Tool("restatement_summary",
             "Breakdowns of how often figures were changed materially in the next year's report, and how many of "
             "those make the trend look better: overall, by metric, by peer group or by company. Not for the "
             "share in one specific year (use group_metric with material_restatement_share and the year).",
             {"level": {"type": "string", "enum": a["restatement_levels"]},
              "group_key": {"type": ["string", "null"], "description": "One group (e.g. a peer group or metric id), or null."}},
             ("level", "group_key"), restatement_summary),
    ]  # fmt: skip


def by_name() -> dict[str, Tool]:
    return {tool.name: tool for tool in tools()}


def call(name: str, arguments: dict) -> dict:
    """Run one tool after validating its arguments. Raises ToolArgumentError on anything else."""
    registry = by_name()
    if name not in registry:
        raise ToolArgumentError(f"unknown tool {name!r}; tools: {', '.join(registry)}")
    if not isinstance(arguments, dict):
        raise ToolArgumentError("arguments must be an object")
    tool = registry[name]
    unknown = set(arguments) - set(tool.parameters)
    if unknown:
        raise ToolArgumentError(f"{name} does not take {sorted(unknown)}")
    missing = [
        p
        for p in tool.required
        if p not in arguments
        and p
        not in (
            "group_type",
            "group_value",
            "year",
            "kpi",
            "ranking_group",
            "group_key",
            "top_n",
            "limit",
        )
    ]
    if missing:
        raise ToolArgumentError(f"{name} needs {missing}")
    return tool.run(**arguments)
