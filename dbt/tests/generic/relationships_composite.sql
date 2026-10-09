{#-
    Every row of the model must find a parent row in `to` with the same values on all key
    columns: a relationships test for composite keys, e.g. facts (filing_id, context_ref) ->
    contexts (filing_id, context_id). Filter child rows with dbt's standard `config: where:`.
-#}
{% test relationships_composite(model, columns, to, to_columns) %}


select child.*
from (select * from {{ model }}) as child
left join {{ to }} as parent
    on
{%- for col in columns %}
        child.{{ col }} = parent.{{ to_columns[loop.index0] }}{% if not loop.last %} and{% endif %}
    {%- endfor %}
where parent.{{ to_columns[0] }} is null

{% endtest %}
