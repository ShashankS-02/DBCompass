package com.example.billing;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import java.util.List;

public interface InvoiceRepository extends JpaRepository<Invoice, Long> {
    List<Invoice> findByCustomerId(Long customerId);

    @Query(value = "SELECT * FROM invoices WHERE invoice_date BETWEEN :from AND :to AND ROWNUM <= 500", nativeQuery = true)
    List<Invoice> findForPeriod(java.time.LocalDate from, java.time.LocalDate to);

    @Query(value = "SELECT c.id FROM customers c START WITH c.id = :root CONNECT BY PRIOR c.id = c.parent_id", nativeQuery = true)
    List<Long> findCustomerHierarchy(Long root);
}
