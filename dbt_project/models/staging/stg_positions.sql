SELECT
    position_id,
    currency,
    amount,
    business_date
FROM {{ source('raw', 'positions') }}
