-- Billing schema (Oracle 19c)
CREATE SEQUENCE customer_seq START WITH 1 INCREMENT BY 1 CACHE 100;
CREATE SEQUENCE invoice_seq START WITH 1 INCREMENT BY 1 CACHE 500;
CREATE SEQUENCE payment_seq START WITH 1 INCREMENT BY 1 CACHE 500;

CREATE TABLE customers (
  id         NUMBER(19) PRIMARY KEY,
  parent_id  NUMBER(19) REFERENCES customers(id),
  name       VARCHAR2(200) NOT NULL,
  segment    VARCHAR2(30)
);

CREATE TABLE invoices (
  id            NUMBER(19) PRIMARY KEY,
  customer_id   NUMBER(19) NOT NULL REFERENCES customers(id),
  invoice_date  DATE NOT NULL,
  total_amount  NUMBER(14,2),
  status        VARCHAR2(20)
)
PARTITION BY RANGE (invoice_date) INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(PARTITION p_initial VALUES LESS THAN (DATE '2024-01-01'));

CREATE TABLE invoice_lines (
  id           NUMBER(19) PRIMARY KEY,
  invoice_id   NUMBER(19) NOT NULL REFERENCES invoices(id),
  charge_code  VARCHAR2(30),
  quantity     NUMBER(14,4),
  amount       NUMBER(14,2)
);

CREATE TABLE payments (
  id              NUMBER(19) PRIMARY KEY,
  invoice_id      NUMBER(19) REFERENCES invoices(id),
  amount          NUMBER(14,2),
  card_reference  VARCHAR2(64)
);

CREATE TABLE billing_audit (
  id         NUMBER(19) PRIMARY KEY,
  event      VARCHAR2(200),
  logged_at  TIMESTAMP DEFAULT SYSTIMESTAMP
);

CREATE OR REPLACE TRIGGER trg_invoice_status
  BEFORE UPDATE OF status ON invoices
  FOR EACH ROW
BEGIN
  IF :NEW.status = 'PAID' AND :OLD.status <> 'ISSUED' THEN
    RAISE_APPLICATION_ERROR(-20010, 'Only issued invoices can be marked paid');
  END IF;
END;
/

CREATE MATERIALIZED VIEW mv_monthly_revenue
  REFRESH COMPLETE ON DEMAND AS
  SELECT TRUNC(invoice_date, 'MM') AS month, SUM(total_amount) AS revenue
  FROM invoices
  GROUP BY TRUNC(invoice_date, 'MM');
