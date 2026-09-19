{% macro generate_tenant_code_timezone_list() %}
    {{ return([
        (1, 'CET'),
        (2, 'WAT'),
        (3, 'EAT')
    ]) }}
{% endmacro %}

{% macro generate_tenant_cte(source_name, source_table, tenant_key, tenant_code, timezone) %}
    SELECT
        toUInt64(UserId) AS user_id,
        coalesce(nullIf(trim(Username), ''), 'NO_VALUE') AS username,
        toUInt8(TenantId) AS source_tenant_code,
        coalesce(nullIf(trim(Phone), ''), 'NO_VALUE') AS phone,
        coalesce(nullIf(trim(CompanyEmail), ''), 'NO_VALUE') AS company_email,
        coalesce(nullIf(trim(Name), ''), 'NO_VALUE') AS name,
        toString(NationalId) AS national_id,
        coalesce(nullIf(trim(Address), ''), 'NO_VALUE') AS address,
        toDateOrZero(toString(DateOfBirth)) AS date_of_birth,
        toUInt8OrZero(toString(Age)) AS age,
        toFloat64OrZero(toString(Salary)) AS salary,
        toLowCardinality('{{ tenant_key }}') AS tenant_key,
        toUInt8({{ tenant_code }}) AS tenant_code,
        toLowCardinality('{{ timezone }}') AS timezone,
        now() AS loaded_at
    FROM {{ source(source_name, source_table) }}
{% endmacro %}
