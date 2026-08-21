-- Ratios are deliberately calculated from sums, never averages of account rates.
CREATE OR REPLACE VIEW mart_portfolio_month_sql AS
SELECT
    month,
    SUM(active_account_flag) AS active_accounts,
    SUM(account_balance) AS ending_receivables,
    SUM(average_daily_balance) AS average_receivables,
    SUM(transaction_value) AS transaction_value,
    SUM(account_balance) / NULLIF(SUM(credit_limit), 0) AS utilization,
    SUM(CASE WHEN days_past_due >= 30 AND chargeoff_flag = 0 THEN 1 ELSE 0 END)
        / NULLIF(SUM(active_account_flag), 0) AS delinquency_30_account_rate,
    (SUM(chargeoff_amount) - SUM(recovery_amount))
        / NULLIF(SUM(average_daily_balance), 0) * 12 AS annualised_net_loss_rate,
    SUM(confirmed_fraud_loss)
        / NULLIF(SUM(transaction_value), 0) * 10000 AS fraud_bps,
    SUM(manual_review_count)
        / NULLIF(SUM(transaction_count), 0) AS manual_review_rate,
    SUM(false_positive_count)
        / NULLIF(SUM(fraud_alert_count), 0) AS false_positive_rate
FROM stg_account_month
GROUP BY month;

