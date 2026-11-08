CREATE OR REPLACE PACKAGE BODY pkg_billing AS
  ----------------------------------------------------------------------------
  -- Audit logging in its own transaction so failures are still recorded.
  ----------------------------------------------------------------------------
  PROCEDURE log_event(p_event IN VARCHAR2) IS
    PRAGMA AUTONOMOUS_TRANSACTION;
  BEGIN
    INSERT INTO billing_audit (id, event, logged_at)
    VALUES (invoice_seq.NEXTVAL, SUBSTR(p_event, 1, 200), SYSTIMESTAMP);
    COMMIT;
  END log_event;

  FUNCTION customer_balance(p_customer_id IN NUMBER) RETURN NUMBER IS
    l_open   NUMBER := 0;
    l_ledger NUMBER := 0;
  BEGIN
    SELECT NVL(SUM(i.total_amount), 0) - NVL(SUM(p.amount), 0)
      INTO l_open
      FROM invoices i, payments p
     WHERE i.id = p.invoice_id(+)
       AND i.customer_id = p_customer_id
       AND i.status = 'ISSUED';

    SELECT NVL(SUM(l.amount), 0)
      INTO l_ledger
      FROM ledger_entries@ledger_db l
     WHERE l.customer_id = p_customer_id;

    RETURN l_open + l_ledger;
  END customer_balance;

  ----------------------------------------------------------------------------
  -- Rating rule for VOICE_LOCAL (minutes, tiered pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_voice_local(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.012;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    IF p_quantity > 100000 THEN
      l_amount := 100000 * l_rate + (p_quantity - 100000) * l_rate * 0.6;
    ELSIF p_quantity > 10000 THEN
      l_amount := 10000 * l_rate + (p_quantity - 10000) * l_rate * 0.8;
    ELSE
      l_amount := p_quantity * l_rate;
    END IF;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'VOICE_LOCAL'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_voice_local;

  ----------------------------------------------------------------------------
  -- Rating rule for VOICE_STD (minutes, tiered pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_voice_std(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.025;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    IF p_quantity > 100000 THEN
      l_amount := 100000 * l_rate + (p_quantity - 100000) * l_rate * 0.6;
    ELSIF p_quantity > 10000 THEN
      l_amount := 10000 * l_rate + (p_quantity - 10000) * l_rate * 0.8;
    ELSE
      l_amount := p_quantity * l_rate;
    END IF;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'VOICE_STD'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_voice_std;

  ----------------------------------------------------------------------------
  -- Rating rule for VOICE_ISD (minutes, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_voice_isd(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.180;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'VOICE_ISD'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_voice_isd;

  ----------------------------------------------------------------------------
  -- Rating rule for SMS_DOM (messages, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_sms_dom(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.004;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'SMS_DOM'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_sms_dom;

  ----------------------------------------------------------------------------
  -- Rating rule for SMS_INTL (messages, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_sms_intl(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.060;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'SMS_INTL'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_sms_intl;

  ----------------------------------------------------------------------------
  -- Rating rule for DATA_4G (megabytes, tiered pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_data_4g(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.0008;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    IF p_quantity > 100000 THEN
      l_amount := 100000 * l_rate + (p_quantity - 100000) * l_rate * 0.6;
    ELSIF p_quantity > 10000 THEN
      l_amount := 10000 * l_rate + (p_quantity - 10000) * l_rate * 0.8;
    ELSE
      l_amount := p_quantity * l_rate;
    END IF;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'DATA_4G'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_data_4g;

  ----------------------------------------------------------------------------
  -- Rating rule for DATA_5G (megabytes, tiered pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_data_5g(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.0006;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    IF p_quantity > 100000 THEN
      l_amount := 100000 * l_rate + (p_quantity - 100000) * l_rate * 0.6;
    ELSIF p_quantity > 10000 THEN
      l_amount := 10000 * l_rate + (p_quantity - 10000) * l_rate * 0.8;
    ELSE
      l_amount := p_quantity * l_rate;
    END IF;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'DATA_5G'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_data_5g;

  ----------------------------------------------------------------------------
  -- Rating rule for ROAM_DATA (megabytes, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_roam_data(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.0150;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'ROAM_DATA'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_roam_data;

  ----------------------------------------------------------------------------
  -- Rating rule for ROAM_VOICE (minutes, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_roam_voice(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.400;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'ROAM_VOICE'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_roam_voice;

  ----------------------------------------------------------------------------
  -- Rating rule for VAS_MUSIC (units, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_vas_music(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.990;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'VAS_MUSIC'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_vas_music;

  ----------------------------------------------------------------------------
  -- Rating rule for VAS_VIDEO (units, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_vas_video(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 1.490;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'VAS_VIDEO'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_vas_video;

  ----------------------------------------------------------------------------
  -- Rating rule for LEASED_LINE (days, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_leased_line(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 42.000;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'LEASED_LINE'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_leased_line;

  ----------------------------------------------------------------------------
  -- Rating rule for MPLS_PORT (days, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_mpls_port(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 18.500;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'MPLS_PORT'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_mpls_port;

  ----------------------------------------------------------------------------
  -- Rating rule for CLOUD_CONNECT (gigabytes, tiered pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_cloud_connect(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.0200;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    IF p_quantity > 100000 THEN
      l_amount := 100000 * l_rate + (p_quantity - 100000) * l_rate * 0.6;
    ELSIF p_quantity > 10000 THEN
      l_amount := 10000 * l_rate + (p_quantity - 10000) * l_rate * 0.8;
    ELSE
      l_amount := p_quantity * l_rate;
    END IF;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'CLOUD_CONNECT'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_cloud_connect;

  ----------------------------------------------------------------------------
  -- Rating rule for IOT_SIM (units, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_iot_sim(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.150;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'IOT_SIM'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_iot_sim;

  ----------------------------------------------------------------------------
  -- Rating rule for IOT_DATA (megabytes, tiered pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_iot_data(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 0.0004;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    IF p_quantity > 100000 THEN
      l_amount := 100000 * l_rate + (p_quantity - 100000) * l_rate * 0.6;
    ELSIF p_quantity > 10000 THEN
      l_amount := 10000 * l_rate + (p_quantity - 10000) * l_rate * 0.8;
    ELSE
      l_amount := p_quantity * l_rate;
    END IF;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'IOT_DATA'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_iot_data;

  ----------------------------------------------------------------------------
  -- Rating rule for DEVICE_EMI (units, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_device_emi(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 12.000;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'DEVICE_EMI'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_device_emi;

  ----------------------------------------------------------------------------
  -- Rating rule for LATE_FEE (units, flat pricing)
  ----------------------------------------------------------------------------
  FUNCTION rate_late_fee(p_quantity IN NUMBER, p_segment IN VARCHAR2) RETURN NUMBER IS
    l_rate     NUMBER := 5.000;
    l_discount NUMBER := 0;
    l_amount   NUMBER;
  BEGIN
    IF p_quantity IS NULL OR p_quantity <= 0 THEN
      RETURN 0;
    END IF;
    l_amount := p_quantity * l_rate;
    SELECT NVL(MAX(discount_pct), 0)
      INTO l_discount
      FROM segment_discounts
     WHERE segment = p_segment
       AND charge_code = 'LATE_FEE'
       AND ROWNUM = 1;
    l_amount := l_amount * (1 - l_discount / 100);
    RETURN ROUND(l_amount, 2);
  EXCEPTION
    WHEN NO_DATA_FOUND THEN
      RETURN ROUND(l_amount, 2);
  END rate_late_fee;

  ----------------------------------------------------------------------------
  -- Rate every line of an invoice and refresh its total.
  ----------------------------------------------------------------------------
  PROCEDURE rate_invoice(p_invoice_id IN NUMBER) IS
    l_segment customers.segment%TYPE;
    l_amount  NUMBER;
  BEGIN
    SELECT c.segment INTO l_segment
      FROM invoices i JOIN customers c ON c.id = i.customer_id
     WHERE i.id = p_invoice_id;

    FOR line IN (SELECT id, charge_code, quantity FROM invoice_lines WHERE invoice_id = p_invoice_id) LOOP
      l_amount := CASE line.charge_code
        WHEN 'VOICE_LOCAL' THEN rate_voice_local(line.quantity, l_segment)
        WHEN 'VOICE_STD' THEN rate_voice_std(line.quantity, l_segment)
        WHEN 'VOICE_ISD' THEN rate_voice_isd(line.quantity, l_segment)
        WHEN 'SMS_DOM' THEN rate_sms_dom(line.quantity, l_segment)
        WHEN 'SMS_INTL' THEN rate_sms_intl(line.quantity, l_segment)
        WHEN 'DATA_4G' THEN rate_data_4g(line.quantity, l_segment)
        WHEN 'DATA_5G' THEN rate_data_5g(line.quantity, l_segment)
        WHEN 'ROAM_DATA' THEN rate_roam_data(line.quantity, l_segment)
        WHEN 'ROAM_VOICE' THEN rate_roam_voice(line.quantity, l_segment)
        WHEN 'VAS_MUSIC' THEN rate_vas_music(line.quantity, l_segment)
        WHEN 'VAS_VIDEO' THEN rate_vas_video(line.quantity, l_segment)
        WHEN 'LEASED_LINE' THEN rate_leased_line(line.quantity, l_segment)
        WHEN 'MPLS_PORT' THEN rate_mpls_port(line.quantity, l_segment)
        WHEN 'CLOUD_CONNECT' THEN rate_cloud_connect(line.quantity, l_segment)
        WHEN 'IOT_SIM' THEN rate_iot_sim(line.quantity, l_segment)
        WHEN 'IOT_DATA' THEN rate_iot_data(line.quantity, l_segment)
        WHEN 'DEVICE_EMI' THEN rate_device_emi(line.quantity, l_segment)
        WHEN 'LATE_FEE' THEN rate_late_fee(line.quantity, l_segment)
        ELSE 0
      END;
      UPDATE invoice_lines SET amount = l_amount WHERE id = line.id;
    END LOOP;

    MERGE INTO invoices i
    USING (SELECT invoice_id, SUM(amount) AS total FROM invoice_lines
            WHERE invoice_id = p_invoice_id GROUP BY invoice_id) t
       ON (i.id = t.invoice_id)
     WHEN MATCHED THEN UPDATE SET i.total_amount = t.total;

    log_event('Rated invoice ' || p_invoice_id);
  EXCEPTION
    WHEN OTHERS THEN
      log_event('Rating failed for ' || p_invoice_id || ': ' || SQLERRM);
      RAISE;
  END rate_invoice;

  ----------------------------------------------------------------------------
  -- Allocate a payment to the oldest open invoices of the customer hierarchy.
  ----------------------------------------------------------------------------
  PROCEDURE allocate_payment(p_payment_id IN NUMBER) IS
    l_remaining NUMBER;
    l_customer  NUMBER;
  BEGIN
    SELECT p.amount, i.customer_id INTO l_remaining, l_customer
      FROM payments p JOIN invoices i ON i.id = p.invoice_id
     WHERE p.id = p_payment_id;

    FOR inv IN (
      SELECT i.id, i.total_amount
        FROM invoices i
       WHERE i.status = 'ISSUED'
         AND i.customer_id IN (SELECT c.id FROM customers c
                                START WITH c.id = l_customer
                              CONNECT BY PRIOR c.id = c.parent_id)
       ORDER BY i.invoice_date
    ) LOOP
      EXIT WHEN l_remaining <= 0;
      IF l_remaining >= inv.total_amount THEN
        UPDATE invoices SET status = 'PAID' WHERE id = inv.id;
        l_remaining := l_remaining - inv.total_amount;
      END IF;
    END LOOP;

    INSERT INTO ledger_entries@ledger_db (customer_id, amount, source_ref)
    VALUES (l_customer, -l_remaining, 'PAY-' || p_payment_id);
    log_event('Allocated payment ' || p_payment_id);
  END allocate_payment;

  ----------------------------------------------------------------------------
  -- Month-end: rate all draft invoices, then schedule the revenue refresh.
  ----------------------------------------------------------------------------
  PROCEDURE run_month_end IS
  BEGIN
    g_last_run_id := invoice_seq.NEXTVAL;
    FOR inv IN (SELECT id FROM invoices WHERE status = 'DRAFT') LOOP
      rate_invoice(inv.id);
    END LOOP;
    DBMS_SCHEDULER.create_job(
      job_name   => 'REFRESH_REVENUE_' || g_last_run_id,
      job_type   => 'PLSQL_BLOCK',
      job_action => 'BEGIN DBMS_MVIEW.REFRESH(''MV_MONTHLY_REVENUE''); END;',
      enabled    => TRUE);
    log_event('Month-end run ' || g_last_run_id || ' complete');
  END run_month_end;

END pkg_billing;
/
