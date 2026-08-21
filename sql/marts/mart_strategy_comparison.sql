CREATE OR REPLACE VIEW mart_strategy_comparison_sql AS
SELECT
    strategy_version,
    COUNT(DISTINCT account_id) AS eligible_accounts,
    COUNT(*) AS assignment_observations,
    SUM(chargeoff_amount) - SUM(recovery_amount) AS net_credit_loss,
    (SUM(chargeoff_amount) - SUM(recovery_amount))
        / NULLIF(SUM(average_daily_balance), 0) AS monthly_net_loss_rate,
    SUM(confirmed_fraud_loss)
        / NULLIF(SUM(transaction_value), 0) * 10000 AS fraud_bps,
    SUM(manual_review_count)
        / NULLIF(SUM(transaction_count), 0) AS manual_review_rate,
    SUM(false_positive_count)
        / NULLIF(SUM(fraud_alert_count), 0) AS false_positive_rate
FROM stg_account_month
WHERE strategy_assignment_type <> 'Recovery-only'
GROUP BY strategy_version;

