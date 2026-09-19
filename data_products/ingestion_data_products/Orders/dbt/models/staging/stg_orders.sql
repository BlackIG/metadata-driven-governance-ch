WITH
{% set tenant_code_timezone_list = generate_tenant_code_timezone_list() %}
{% for tenant_code, timezone in tenant_code_timezone_list %}
    {% set tenant_key = 'tenant_' ~ tenant_code %}
    {% set source_table = 'raw_tenant_' ~ tenant_code ~ '_orders' %}
    {% set cte_name = tenant_key ~ '_cte' %}
    {{ cte_name }} AS (
        {{ generate_tenant_cte('raw_tenants', source_table, tenant_key, tenant_code, timezone) }}
    )
    {% if not loop.last %},
    {% endif %}
{% endfor %}

SELECT * FROM
{% for tenant_code, timezone in tenant_code_timezone_list %}
    {% set tenant_key = 'tenant_' ~ tenant_code %}
    {% set cte_name = tenant_key ~ '_cte' %}
    (SELECT * FROM {{ cte_name }})
    {% if not loop.last %}
        UNION ALL
    {% endif %}
{% endfor %}
