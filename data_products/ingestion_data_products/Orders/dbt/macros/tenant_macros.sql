{% macro generate_tenant_code_timezone_list() %}
    {{ return([
        (1, 'CET'),
        (2, 'WAT'),
        (3, 'EAT')
    ]) }}
{% endmacro %}

{% macro generate_tenant_cte(source_name, source_table, tenant_key, tenant_code, timezone) %}
    SELECT
        toUInt64(OrderId) AS order_id,
        toUInt64(UserId) AS user_id,
        OrderDate AS order_date,
        coalesce(nullIf(trim(ProductName), ''), 'NO_VALUE') AS product_name,
        toUInt32(Quantity) AS quantity,
        toFloat64(UnitPrice) AS unit_price,
        toLowCardinality(coalesce(nullIf(trim(OrderStatus), ''), 'UNKNOWN')) AS order_status,
        toFloat64(Quantity) * toFloat64(UnitPrice) AS total_amount,
        toLowCardinality('{{ tenant_key }}') AS tenant_key,
        toUInt8({{ tenant_code }}) AS tenant_code,
        toLowCardinality('{{ timezone }}') AS timezone,
        now() AS loaded_at
    FROM {{ source(source_name, source_table) }}
{% endmacro %}
