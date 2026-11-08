package com.example.billing;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "PAYMENTS")
public class Payment {
    @Id
    private Long id;

    @ManyToOne
    @JoinColumn(name = "INVOICE_ID")
    private Invoice invoice;

    private BigDecimal amount;
    private String cardReference;
}
