-- DuckDB-compatible governed staging view.
-- Grain: one synthetic account per reporting month.
CREATE OR REPLACE VIEW stg_account_month AS
SELECT
    p.*,
    a.product_type,
    a.acquisition_channel,
    a.geography,
    a.customer_segment,
    a.original_risk_band,
    a.origination_date,
    a.partner_id,
    a.vendor_id,
    a.membership_tier_id,
    p.chargeoff_amount - p.recovery_amount AS net_credit_loss,
    CASE
        WHEN p.inactive_flag = 0 AND p.chargeoff_flag = 0 THEN 1
        ELSE 0
    END AS active_account_flag
FROM monthly_account_performance AS p
INNER JOIN customer_account_master AS a
    ON p.account_id = a.account_id;

