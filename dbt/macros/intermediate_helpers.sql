{#- Shared intermediate-layer helpers. Rules are documented in docs/business_rules.md. -#}

{% macro iso_duration_days(expr) -%}
    {#- ISO 8601 day duration -> number of days: 'P59D' -> 59. Anything else -> null. -#}
    try_cast(regexp_extract(trim({{ expr }}), '^P([0-9]+(\.[0-9]+)?)D$', 1) as double)
{%- endmacro %}


{% macro number_from_text(expr) -%}
    {#- Number filed as text (old taxonomies): drop thousands separators, spaces and no-break
        spaces, e.g. '20,23,072' -> 2023072. Non-numbers -> null. -#}
    try_cast(regexp_replace({{ expr }}, '[,\s\x{00A0}]', '', 'g') as double)
{%- endmacro %}


{% macro normalise_unit_text(expr) -%}
    {#- Free-text unit -> lookup key: lower case, whitespace (incl. line breaks) collapsed. -#}
    trim(regexp_replace(lower({{ expr }}), '\s+', ' ', 'g'))
{%- endmacro %}


{% macro dimension_axes(dimension_key) -%}
    {#- 'AxisA=M1|AxisB=M2' -> ['AxisA', 'AxisB']; '' -> []. -#}
    case
        when {{ dimension_key }} = '' then []
        else list_transform(string_split({{ dimension_key }}, '|'), lambda d: split_part(d, '=', 1))
    end
{%- endmacro %}


{% macro default_unit_for(unit_std) -%}
    {#- Unit assumed for old-taxonomy 'pure' quantities when neither the next filing nor a text
        unit says otherwise (the BRSR format's own units). -#}
    case {{ unit_std }}
        when 'tCO2e' then 'tCO2e'
        when 'GJ' then 'GJ'
        when 'kl' then 'kl'
        when 't' then 't'
        when 'tCO2e/INR cr' then 'tCO2e/INR'
        when 'GJ/INR cr' then 'GJ/INR'
        when 'kl/INR cr' then 'kl/INR'
    end
{%- endmacro %}


{% macro round_sig(expr, digits=15) -%}
    {#- Round to `digits` significant digits. Filed values have at most 15 (DOUBLE precision), so
        this removes float noise from unit multipliers: 8.88e-8 x 1e7 -> 0.888, not 0.8880000000000001. -#}
    case
        when {{ expr }} is null or {{ expr }} = 0 then {{ expr }}
        else round({{ expr }}, {{ digits }} - 1 - cast(floor(log10(abs({{ expr }}))) as integer))
    end
{%- endmacro %}
