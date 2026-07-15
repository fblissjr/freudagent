-- Source schema for the relational extract in this folder.
-- Fictional OLTP database `acmedb` behind Acme Analytics' billing service.
-- The CSVs are straight SELECT * exports of these tables.

CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    account_id    VARCHAR(16) NOT NULL,        -- CRM foreign identity (ACCT-*)
    company_name  VARCHAR(120) NOT NULL,
    billing_email VARCHAR(200) NOT NULL,
    country       CHAR(2) NOT NULL,
    created_at    TIMESTAMP NOT NULL
);

CREATE TABLE subscriptions (
    subscription_id INTEGER PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    plan            VARCHAR(20) NOT NULL,      -- starter|growth|scale|enterprise
    mrr_usd         DECIMAL(10,2) NOT NULL,
    seats           INTEGER NOT NULL,
    started_at      DATE NOT NULL,
    canceled_at     DATE,                      -- NULL = active
    billing_cycle   VARCHAR(10) NOT NULL       -- monthly|annual
);

CREATE TABLE invoices (
    invoice_id      VARCHAR(20) PRIMARY KEY,   -- INV-YYYYMM-NNNN
    subscription_id INTEGER NOT NULL REFERENCES subscriptions(subscription_id),
    period_start    DATE NOT NULL,
    period_end      DATE NOT NULL,
    amount_usd      DECIMAL(10,2) NOT NULL,
    status          VARCHAR(12) NOT NULL,      -- paid|open|past_due|void
    issued_at       DATE NOT NULL,
    paid_at         DATE
);

CREATE TABLE usage_daily (
    customer_id   INTEGER NOT NULL REFERENCES customers(customer_id),
    usage_date    DATE NOT NULL,
    api_calls     BIGINT NOT NULL,
    events_ingested BIGINT NOT NULL,
    dashboards_viewed INTEGER NOT NULL,
    PRIMARY KEY (customer_id, usage_date)
);
