SELECT
    p.position_id,
    p.currency,
    p.amount,
    p.business_date,
    f.rate,
    f.rate_date,
    p.amount / f.rate AS eur_value
FROM {{ ref('stg_positions') }} p
LEFT JOIN {{ ref('stg_fx_rates') }} f
    ON p.currency = f.currency
    AND p.business_date = f.date
