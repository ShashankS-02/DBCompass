CREATE OR REPLACE PACKAGE BODY pkg_ledger_sync AS

  PROCEDURE push_daily_totals(p_day IN DATE) IS
  BEGIN
    MERGE INTO daily_totals@finance_dw d
    USING (SELECT TRUNC(invoice_date) AS day, SUM(total_amount) AS total
             FROM invoices
            WHERE TRUNC(invoice_date) = TRUNC(p_day)
            GROUP BY TRUNC(invoice_date)) s
       ON (d.day = s.day)
     WHEN MATCHED THEN UPDATE SET d.total = s.total
     WHEN NOT MATCHED THEN INSERT (day, total) VALUES (s.day, s.total);
  END push_daily_totals;

  PROCEDURE export_statement(p_customer_id IN NUMBER) IS
    l_file UTL_FILE.FILE_TYPE;
  BEGIN
    l_file := UTL_FILE.FOPEN('STATEMENTS_DIR', 'stmt_' || p_customer_id || '.csv', 'w');
    FOR r IN (SELECT id, invoice_date, total_amount FROM invoices WHERE customer_id = p_customer_id) LOOP
      UTL_FILE.PUT_LINE(l_file, r.id || ',' || TO_CHAR(r.invoice_date, 'YYYY-MM-DD') || ',' || r.total_amount);
    END LOOP;
    UTL_FILE.FCLOSE(l_file);
  END export_statement;

END pkg_ledger_sync;
/
