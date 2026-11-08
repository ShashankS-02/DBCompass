package com.example.billing;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.math.BigDecimal;

@Service
public class BillingService {
    private final JdbcTemplate jdbc;

    public BillingService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void rateInvoice(long invoiceId) {
        jdbc.update("BEGIN pkg_billing.rate_invoice(?); END;", invoiceId);
    }

    @Transactional(readOnly = true)
    public BigDecimal ledgerBalance(long customerId) {
        return jdbc.queryForObject(
            "SELECT SUM(l.amount) FROM ledger_entries@ledger_db l WHERE l.customer_id = ? GROUP BY l.customer_id",
            BigDecimal.class, customerId);
    }

    @Scheduled(cron = "${billing.month-end.cron}")
    public void monthEndRun() {
        jdbc.update("BEGIN pkg_billing.run_month_end; END;");
    }
}
