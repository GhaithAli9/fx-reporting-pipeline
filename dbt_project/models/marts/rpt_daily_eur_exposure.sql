SELECT
    business_date,
    COUNT(*) AS position_count,
    ROUND(SUM(eur_value), 2) AS total_eur_exposure
FROM {{ ref('fct_position_valuation') }}
GROUP BY business_date
ORDER BY business_date
