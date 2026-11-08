namespace ClaimsHub.Models;

public class Policy
{
    public long PolicyId { get; set; }
    public string PolicyNumber { get; set; } = "";
    public string ProductCode { get; set; } = "";
    public DateTime StartDate { get; set; }
    public DateTime EndDate { get; set; }
    public long CustomerId { get; set; }
    public Customer? Customer { get; set; }
    public List<Claim> Claims { get; set; } = new();
}

public class Customer
{
    public long CustomerId { get; set; }
    public string FullName { get; set; } = "";
    public string CountryCode { get; set; } = "";
    public List<Policy> Policies { get; set; } = new();
}

public class Claim
{
    public long ClaimId { get; set; }
    public string ClaimNumber { get; set; } = "";
    public long PolicyId { get; set; }
    public Policy? Policy { get; set; }
    public DateTime LossDate { get; set; }
    public string Status { get; set; } = "OPEN";
    public decimal ReserveAmount { get; set; }
    public decimal PaidAmount { get; set; }
    public int FraudScore { get; set; }
    public List<ClaimLine> Lines { get; set; } = new();
    public List<Payment> Payments { get; set; } = new();
    public List<ClaimNote> Notes { get; set; } = new();
}

public class ClaimLine
{
    public long ClaimLineId { get; set; }
    public long ClaimId { get; set; }
    public Claim? Claim { get; set; }
    public string CoverageCode { get; set; } = "";
    public decimal ClaimedAmount { get; set; }
    public decimal ApprovedAmount { get; set; }
}

public class Payment
{
    public long PaymentId { get; set; }
    public long ClaimId { get; set; }
    public Claim? Claim { get; set; }
    public decimal Amount { get; set; }
    public DateTime PaidAt { get; set; }
    public string PayeeIban { get; set; } = "";
}

public class ClaimNote
{
    public long ClaimNoteId { get; set; }
    public long ClaimId { get; set; }
    public Claim? Claim { get; set; }
    public string Author { get; set; } = "";
    public string Body { get; set; } = "";
    public DateTime CreatedAt { get; set; }
}

public class Adjuster
{
    public int AdjusterId { get; set; }
    public string Name { get; set; } = "";
    public string Region { get; set; } = "";
}
