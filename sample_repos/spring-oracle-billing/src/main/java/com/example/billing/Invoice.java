package com.example.billing;

import jakarta.persistence.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

@Entity
@Table(name = "INVOICES")
public class Invoice {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "invoice_seq")
    @SequenceGenerator(name = "invoice_seq", sequenceName = "INVOICE_SEQ")
    private Long id;

    @ManyToOne
    @JoinColumn(name = "CUSTOMER_ID")
    private Customer customer;

    @OneToMany(mappedBy = "invoice")
    private List<InvoiceLine> lines;

    @OneToMany(mappedBy = "invoice")
    private List<Payment> payments;

    private LocalDate invoiceDate;
    private BigDecimal totalAmount;
    private String status;
}
