package com.example.billing;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "INVOICE_LINES")
public class InvoiceLine {
    @Id
    private Long id;

    @ManyToOne
    @JoinColumn(name = "INVOICE_ID")
    private Invoice invoice;

    private String chargeCode;
    private BigDecimal amount;
}
