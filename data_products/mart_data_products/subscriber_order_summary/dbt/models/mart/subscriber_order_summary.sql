WITH order_aggregates AS (
    SELECT
        tenant_code,
        user_id,
        count() AS total_orders,
        countIf(order_status = 'completed') AS completed_orders,
        countIf(order_status = 'cancelled') AS cancelled_orders,
        sum(quantity) AS total_units,
        sum(total_amount) AS gross_order_value,
        avg(total_amount) AS average_order_value,
        min(order_date) AS first_order_date,
        max(order_date) AS last_order_date,
        argMax(order_status, order_date) AS latest_order_status
    FROM {{ source('staging', 'stg_orders') }}
    GROUP BY
        tenant_code,
        user_id
)

SELECT
    aggregates.tenant_code,
    aggregates.user_id,
    subscribers.tenant_key,
    subscribers.username,
    subscribers.name,
    subscribers.company_email,
    subscribers.timezone,
    aggregates.total_orders,
    aggregates.completed_orders,
    aggregates.cancelled_orders,
    aggregates.total_units,
    aggregates.gross_order_value,
    aggregates.average_order_value,
    aggregates.first_order_date,
    aggregates.last_order_date,
    toLowCardinality(aggregates.latest_order_status) AS latest_order_status,
    now() AS loaded_at
FROM order_aggregates AS aggregates
INNER JOIN {{ source('staging', 'stg_subscribers') }} AS subscribers
    ON aggregates.tenant_code = subscribers.tenant_code
    AND aggregates.user_id = subscribers.user_id
