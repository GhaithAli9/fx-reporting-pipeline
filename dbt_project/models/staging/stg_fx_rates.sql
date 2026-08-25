SELECT
    date,
    rate_date,
    'USD' AS currency,
    rates.usd AS rate
FROM {{ source('raw', 'fx_rates') }}

UNION ALL

SELECT
    date,
    rate_date,
    'GBP' AS currency,
    rates.gbp AS rate
FROM {{ source('raw', 'fx_rates') }}

UNION ALL

SELECT
    date,
    rate_date,
    'JPY' AS currency,
    rates.jpy AS rate
FROM {{ source('raw', 'fx_rates') }}

UNION ALL

SELECT
    date,
    rate_date,
    'CHF' AS currency,
    rates.chf AS rate
FROM {{ source('raw', 'fx_rates') }}
