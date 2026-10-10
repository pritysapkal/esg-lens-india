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


{% macro is_scale_error(ratio) -%}
    {#- A later comparative more than 100 times, or less than a hundredth of, the value first
        filed: almost certainly a unit / scale mistake in one of the two, not a restatement. -#}
    coalesce({{ ratio }} > 100 or {{ ratio }} < 0.01, false)
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
