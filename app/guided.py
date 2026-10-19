"""Guided questions: a question builder with fixed choices, no language model.

Each question type turns the reader's choices into ONE call of a validated AI-analyst tool
(app/ai_analyst/tools.py, through `tools.call`) and turns the result into a sentence, a table
with reader-facing column names, and the notes the tool attached (withheld, provisional, ...).
There is no other query path: this module never reads a table itself. tests/test_guided.py
checks that every question type goes through `tools.call` and nothing else.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from app import labels
from app.ai_analyst import tools

ALL_YEARS = "All years"
ALL_KPIS = "All KPIs"
GUIDED_RESTATEMENT_LEVELS = {
    "overall": "All figures",
    "peer_group": "By peer group",
    "metric": "By metric",
}


@dataclass(frozen=True)
class QuestionType:
    key: str
    label: str  # the question as the reader sees it
    tool: str


QUESTION_TYPES = [
    QuestionType("group", "How does a group of companies compare on a figure?", "group_metric"),
    QuestionType("card", "What does one company's report card say?", "company_card"),
    QuestionType("peers", "Where does a company rank among its peers?", "company_percentiles"),
    QuestionType("concentration", "How concentrated are emissions?", "concentration"),
    QuestionType("movers", "Who changed most on carbon intensity (confirmed changes only)?", "top_movers_confirmed"),
    QuestionType("restatements", "How often are figures restated in the next report?", "restatement_summary"),
]  # fmt: skip
BY_KEY = {q.key: q for q in QUESTION_TYPES}


@dataclass
class GuidedAnswer:
    tool: str
    arguments: dict
    sentence: str
    table: pd.DataFrame
    notes: list[str]
    source: str

    @property
    def call_text(self) -> str:
        """The tool call as code, shown under the answer."""
        args = ", ".join(f"{k}={v!r}" for k, v in self.arguments.items())
        return f"{self.tool}({args})"


# ------------------------------------------------------------------ choices for the dropdowns


def choices() -> dict[str, list]:
    """The values the dropdowns offer: exactly the values the tools accept."""
    a = tools.allowed()
    return {
        "years": a["years"],
        "companies": a["companies"],
        "metrics": a["metrics"],
        "group_types": a["group_types"],
        "ranking_groups": a["ranking_groups"],
        "kpis": sorted(a["kpis"], key=lambda k: (labels.PILLARS.index(labels.KPI_INFO[k][1]), labels.KPI_INFO[k][0])),
        "restatement_levels": [lvl for lvl in GUIDED_RESTATEMENT_LEVELS if lvl in a["restatement_levels"]],
    }  # fmt: skip


def group_values(group_type: str) -> list[str]:
    """Groups of one type, read from a tool result (no direct table read)."""
    result = tools.call("group_metric", {"metric": "companies_reporting", "group_type": group_type})
    return sorted({row["group"] for row in result["rows"]})


# ------------------------------------------------------------------ building the call


def arguments(key: str, picks: dict) -> tuple[str, dict]:
    """(tool name, arguments) for one question type and the reader's picks."""
    q = BY_KEY[key]
    if key == "group":
        args = {
            "metric": picks["metric"],
            "group_type": picks["group_type"],
            "group_value": picks["group_value"],
        }
        if picks.get("year") and picks["year"] != ALL_YEARS:
            args["year"] = picks["year"]
    elif key == "card":
        args = {"company": picks["company"], "year": picks["year"]}
    elif key == "peers":
        args = {"company": picks["company"], "year": picks["year"]}
        if picks.get("kpi") and picks["kpi"] != ALL_KPIS:
            args["kpi"] = picks["kpi"]
    elif key == "concentration":
        args = {"year": picks["year"], "top_n": int(picks.get("top_n", 10))}
    elif key == "movers":
        args = {"direction": picks["direction"], "limit": int(picks.get("limit", 5))}
        if picks.get("ranking_group") and picks["ranking_group"] != "All ranking groups":
            args["ranking_group"] = picks["ranking_group"]
    elif key == "restatements":
        args = {"level": picks["level"]}
    else:  # pragma: no cover - BY_KEY lookup above already failed
        raise KeyError(key)
    return q.tool, args


def ask(key: str, picks: dict) -> GuidedAnswer:
    """Run the question through the validated tool and describe the result."""
    name, args = arguments(key, picks)
    result = tools.call(name, args)
    sentence, table = DESCRIBE[name](args, result)
    return GuidedAnswer(
        name,
        args,
        sentence,
        labels.friendly(table),
        list(result.get("notes", [])),
        result.get("source", ""),
    )


# ------------------------------------------------------------------ describing the result


def _num(value, digits: int = 1) -> str:
    return labels.fmt(value, digits)


def _describe_group(args: dict, result: dict) -> tuple[str, pd.DataFrame]:
    rows = pd.DataFrame(result["rows"])
    label, unit = result["label"], result["unit"]
    digits = 1 if unit in ("%", "points (0-100)", "companies", "restated values") else 2
    if rows.empty:
        return f"No published figure for {args['group_value']}.", rows
    table = rows.assign(
        value=[
            _num(v, digits) if s == "shown" else s
            for v, s in zip(rows["value"], rows["status"], strict=True)
        ]
    )
    table = table[["group", "year", "value", "companies_behind_it"]].rename(
        columns={"value": f"{label}, {unit}"}
    )
    if len(rows) == 1:
        r = rows.iloc[0]
        lead = f"**{label}** of {r['group']}, {r['year']}"
        if r["status"] == "shown":
            sentence = f"{lead}: **{_num(r['value'], digits)} {unit}** ({int(r['companies_behind_it'])} companies)."
        elif r["status"].startswith("n<5"):
            sentence = (f"{lead}: **withheld** - only {int(r['companies_behind_it'])} companies stand behind it, "
                        "and a group figure needs 5.")  # fmt: skip
        else:
            sentence = f"{lead}: **{r['status']}**."
    else:
        shown = rows[rows["status"] == "shown"]
        sentence = f"**{label}** of {args['group_value']}, year by year ({unit})"
        if len(shown) >= 2:
            first, last = shown.iloc[0], shown.iloc[-1]
            sentence += (f": **{_num(first['value'], digits)}** in {first['year']} and "
                         f"**{_num(last['value'], digits)}** in {last['year']}.")  # fmt: skip
        else:
            sentence += "."
    return sentence, table


def _describe_card(args: dict, result: dict) -> tuple[str, pd.DataFrame]:
    c = result["card"]
    sentence = f"In {c['year']}, **{c['company']}** has no Disclosure Quality Score."
    if c.get("dqs_total") is not None:
        sentence = (f"In {c['year']}, **{c['company']}** scored **{_num(c['dqs_total'])} of 100** on the "
                    f"Disclosure Quality Score (grade {c.get('dqs_grade') or '-'})")  # fmt: skip
        if c.get("dqs_rank_in_group") is not None:
            sentence += f", rank {int(c['dqs_rank_in_group'])} of {int(c['dqs_group_n'])} in {c['ranking_group']}"
        sentence += "."
    facts = [
        ("Disclosure Quality Score (0-100)", _num(c.get("dqs_total"))),
        ("Grade", c.get("dqs_grade") or "-"),
        ("Rank in ranking group (1 = best)", "-" if c.get("dqs_rank_in_group") is None else f"{int(c['dqs_rank_in_group'])} of {int(c['dqs_group_n'])}"),
        ("Percentile in ranking group (100 = best)", _num(c.get("dqs_percentile_in_group"), 0)),
        ("Status", "Provisional" if c.get("is_provisional") else "Final"),
        ("Assurance", " / ".join(str(v) for v in (c.get("assurance_level"), c.get("assurance_scope")) if v) or "not stated"),
        ("GHG intensity (tCO2e per Rs crore)", _num(c.get("ghg_intensity_tco2e_per_cr"), 2)),
        ("Energy intensity (GJ per Rs crore)", _num(c.get("energy_intensity_gj_per_cr"), 1)),
        ("Water intensity (kl per Rs crore)", _num(c.get("water_intensity_kl_per_cr"), 1)),
        ("Renewable share of energy (%)", _num(c.get("renewable_share_pct"))),
        ("Women in workforce (%)", _num(c.get("female_workforce_pct"))),
        ("Where points were lost", "; ".join(c.get("reasons_points_were_lost") or []) or "-"),
    ]  # fmt: skip
    return sentence, pd.DataFrame(facts, columns=["Item", "Value"])


def _describe_peers(args: dict, result: dict) -> tuple[str, pd.DataFrame]:
    rows = pd.DataFrame(result["rows"])
    if rows.empty:
        return f"No peer positions for {result['company']} in {result['year']}.", rows
    rows["pillar"] = rows["kpi"].map(lambda k: labels.KPI_INFO.get(k, ("", ""))[1])
    table = rows[
        [
            "pillar",
            "kpi_label",
            "percentile_in_group",
            "rank_in_group",
            "companies_in_group",
            "ranking_status",
        ]
    ]
    table = table.rename(columns={"pillar": "Pillar"})
    if len(rows) == 1:
        r = rows.iloc[0]
        if r["ranking_status"] == "ranked":
            sentence = (f"In {result['year']}, {result['company']} is at **percentile {_num(r['percentile_in_group'])}** "
                        f"(rank {int(r['rank_in_group'])} of {int(r['companies_in_group'])}) in {r['ranking_group']} "
                        f"on {r['kpi_label']}; 100 is the best in the group.")  # fmt: skip
        else:
            sentence = f"In {result['year']}, {result['company']} is **{r['ranking_status']}** on {r['kpi_label']}."
    else:
        ranked = rows[rows["ranking_status"] == "ranked"]
        sentence = (f"In {result['year']}, {result['company']} is ranked on {len(ranked)} of {len(rows)} KPIs in "
                    f"{rows['ranking_group'].iloc[0]}; the others say why they are not ranked.")  # fmt: skip
    return sentence, table


def _describe_concentration(args: dict, result: dict) -> tuple[str, pd.DataFrame]:
    s = result["summary"]
    sentence = (f"In {s['year']}, the five largest emitters held **{_num(s['top_5_share_pct'])}%** of the Scope 1+2 "
                f"emissions of all {s['companies_with_emissions']} companies covered, and the largest alone "
                f"{_num(s['top_1_share_pct'])}%; {s['companies_for_80_pct']} companies make up 80%.")  # fmt: skip
    table = pd.DataFrame(result["largest_emitters"])[
        [
            "emitter_rank",
            "display_name",
            "sector_group",
            "share_of_total_pct",
            "cumulative_share_pct",
        ]
    ]
    return sentence, table


def _describe_movers(args: dict, result: dict) -> tuple[str, pd.DataFrame]:
    movers = pd.DataFrame(result["movers"])
    word = "improvement" if args["direction"] == "improvement" else "deterioration"
    where = f" in {args['ranking_group']}" if args.get("ranking_group") else ""
    if movers.empty:
        sentence = f"No confirmed {word}{where}."
    else:
        m = movers.iloc[0]
        sentence = (f"The largest confirmed {word} in GHG intensity{where} was **{m['display_name']}**, "
                    f"**{m['change_pct']:+.1f}%** from {m['from_year']} to {m['to_year']}. "
                    f"{result['ranked_pairs']} changes are confirmed and ranked; the others are set aside "
                    f"(see the notes).")  # fmt: skip
    columns = [
        "ranking_group",
        "display_name",
        "from_year",
        "to_year",
        "intensity_from",
        "intensity_to",
        "change_pct",
    ]
    return sentence, movers[columns] if not movers.empty else movers


def _describe_restatements(args: dict, result: dict) -> tuple[str, pd.DataFrame]:
    rows = pd.DataFrame(result["rows"])
    if rows.empty:
        return "No restatement figures.", rows
    # the table withholds the shares of a group of fewer than 5 companies; the tool says which
    small = rows["status"] != "shown"
    for column in ("pct_material", "pct_material_flattering"):
        rows[column] = [
            ("n<5 (withheld)" if s else _num(v)) for v, s in zip(rows[column], small, strict=True)
        ]
    if args["level"] == "overall":
        r = rows.iloc[0]
        sentence = (f"Of the {int(r['n_pairs']):,} figures that could be checked against the next report, "
                    f"**{r['pct_material']}%** were restated materially ({int(r['n_material'])}); "
                    f"{int(r['n_material_flattering'])} of those ({r['pct_material_flattering']}%) make the trend look better.")  # fmt: skip
    else:
        sentence = (f"Figures restated materially in the next report, {GUIDED_RESTATEMENT_LEVELS[args['level']].lower()}. "
                    "A restatement is a correction between two filings, not a finding of wrongdoing.")  # fmt: skip
    columns = [
        "group_key",
        "n_pairs",
        "n_material",
        "pct_material",
        "n_material_flattering",
        "pct_material_flattering",
        "n_companies",
    ]
    return sentence, rows[columns]


DESCRIBE = {
    "group_metric": _describe_group,
    "company_card": _describe_card,
    "company_percentiles": _describe_peers,
    "concentration": _describe_concentration,
    "top_movers_confirmed": _describe_movers,
    "restatement_summary": _describe_restatements,
}
