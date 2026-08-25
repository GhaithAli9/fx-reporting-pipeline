-- Singular test: fails if it returns ANY rows.
-- A negative or zero EUR valuation is never valid for a position.
SELECT *
FROM {{ ref('fct_position_valuation') }}
WHERE eur_value <= 0
