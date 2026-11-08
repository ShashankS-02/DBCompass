CREATE OR REPLACE PACKAGE pkg_billing AS
  g_last_run_id NUMBER;
  PROCEDURE rate_invoice(p_invoice_id IN NUMBER);
  PROCEDURE allocate_payment(p_payment_id IN NUMBER);
  PROCEDURE run_month_end;
  PROCEDURE log_event(p_event IN VARCHAR2);
  FUNCTION customer_balance(p_customer_id IN NUMBER) RETURN NUMBER;
END pkg_billing;
/
