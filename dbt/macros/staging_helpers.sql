{#- Shared staging helpers. Pure SQL expressions: no business logic, only cleaning and flags. -#}

{% macro strip_ns_prefix(expr) -%}
    {#- Drop an XBRL namespace prefix: 'iso4217:INR' -> 'INR', 'Non-SI:tCO2e' -> 'tCO2e'. -#}
    regexp_replace({{ expr }}, '^[^:]+:', '')
{%- endmacro %}


{% macro na_text_patterns() -%}
    {#-
        Values that mean "not applicable / not available" in BRSR filings. Matched against the
        lower-cased, trimmed raw value; each entry is a full-match regular expression.

        Deliberately NOT included: 'nil', 'none', 'no', 'zero'. In BRSR answers these mean
        "zero" or "no" (e.g. "Nil" complaints), which is information, not a missing value.
    -#}
    {{ return([
        '^n\.?\s?a\.?$',
        '^n/a$',
        '^not applicable\.?$',
        '^not available\.?$',
        '^-+$',
    ]) }}
{%- endmacro %}


{% macro is_na_text(expr) -%}
    {#- True when the value matches one of na_text_patterns() (case-insensitive, trimmed). -#}
    coalesce(regexp_full_match(lower(trim({{ expr }})), '{{ na_text_patterns() | join("|") }}'), false)
{%- endmacro %}


{% macro fiscal_year_start(date_expr) -%}
    {#- Indian financial year (April-March) that contains the date: 2026-03-31 -> 2025. -#}
    (year({{ date_expr }}) - case when month({{ date_expr }}) <= 3 then 1 else 0 end)
{%- endmacro %}


{% macro fiscal_year_label(date_expr) -%}
    {#- 'FY2025-26' for any date between 2025-04-01 and 2026-03-31. -#}
    'FY' || cast({{ fiscal_year_start(date_expr) }} as varchar) || '-'
    || lpad(cast(({{ fiscal_year_start(date_expr) }} + 1) % 100 as varchar), 2, '0')
{%- endmacro %}
