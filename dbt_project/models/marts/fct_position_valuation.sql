SELECT
    position_id,
    currency,
    amount,
    business_date,
    rate,
    rate_date,
    ROUND(eur_value, 2) AS eur_value
FROM {{ ref('int_position_valuations') }}
