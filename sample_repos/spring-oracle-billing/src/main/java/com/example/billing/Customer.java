package com.example.billing;

import jakarta.persistence.*;
import java.util.List;

@Entity
@Table(name = "CUSTOMERS")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.SEQUENCE, generator = "customer_seq")
    @SequenceGenerator(name = "customer_seq", sequenceName = "CUSTOMER_SEQ")
    private Long id;

    private String name;
    private String segment;

    @ManyToOne
    @JoinColumn(name = "PARENT_ID")
    private Customer parent;

    @OneToMany(mappedBy = "customer")
    private List<Invoice> invoices;
}
