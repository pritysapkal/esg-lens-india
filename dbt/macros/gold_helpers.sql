{#- Shared gold-layer helpers. Rules are documented in docs/restatement_method.md and
    docs/kpi_definitions.md. -#}

{% macro unit_resolution_method(flag) -%}
    {#- How the unit of a value was decided, read from its normalisation_flag. -#}
    case
        when contains({{ flag }}, 'unit_bridged_from_next_filing') then 'bridged-from-next-filing'
        when contains({{ flag }}, 'unit_from_text') then 'text-unit'
        when contains({{ flag }}, 'unit_format_default') then 'default'
        else 'as-filed'
    end
{%- endmacro %}


{% macro is_scale_error(ratio, is_pct) -%}
    {#- A later comparative more than 100 times, or less than a hundredth of, the value first
        filed: almost certainly a unit / scale mistake in one of the two, not a restatement.
        Percent metrics use 10 times / a tenth: a percentage cannot plausibly move tenfold, and
        the usual slip is a fraction filed where a percent is meant (0.5 vs 8.8). -#}
    coalesce(
        case
            when {{ is_pct }} then {{ ratio }} >= 10 or {{ ratio }} <= 0.1
            else {{ ratio }} > 100 or {{ ratio }} < 0.01
        end,
        false
    )
{%- endmacro %}


{% macro intensity_basis(ratio) -%}
    {#- The filed intensity is normalised as if it were "per rupee" (x 1e7 to per Rs crore), so
        filed / computed equals the denominator the company really used, in rupees. Classified
        to the nearest power of ten within +-25%. -#}
    case
        when {{ ratio }} is null or {{ ratio }} <= 0 then null
        when {{ ratio }} between 0.75 and 1.25 then 'per rupee (as required)'
        when {{ ratio }} between 0.75e5 and 1.25e5 then 'per lakh'
        when {{ ratio }} between 0.75e6 and 1.25e6 then 'per million'
        when {{ ratio }} between 0.75e7 and 1.25e7 then 'per crore'
        else 'other/unclear'
    end
{%- endmacro %}


{% macro dqs_weighted_total(w_completeness, w_internal, w_temporal, w_assurance) -%}
    {#- Disclosure Quality Score, 0-100: the weighted average of the components of
        int_dqs_components that are not empty, with the weights re-normalised over those
        components. Empty when fewer than two components can be scored. Not rounded here.
        Rule: docs/disclosure_quality_score.md. -#}
    case
        when
            cast(completeness is not null as integer)
            + cast(internal_consistency is not null as integer)
            + cast(temporal_consistency is not null as integer)
            + cast(assurance is not null as integer) >= 2
            then
                100 * (
                    coalesce({{ w_completeness }} * completeness, 0)
                    + coalesce({{ w_internal }} * internal_consistency, 0)
                    + coalesce({{ w_temporal }} * temporal_consistency, 0)
                    + coalesce({{ w_assurance }} * assurance, 0)
                ) / (
                    case when completeness is not null then {{ w_completeness }} else 0 end
                    + case when internal_consistency is not null then {{ w_internal }} else 0 end
                    + case when temporal_consistency is not null then {{ w_temporal }} else 0 end
                    + case when assurance is not null then {{ w_assurance }} else 0 end
                )
    end
{%- endmacro %}
