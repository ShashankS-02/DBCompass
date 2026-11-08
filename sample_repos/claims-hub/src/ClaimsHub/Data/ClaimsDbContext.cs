using ClaimsHub.Models;
using Microsoft.EntityFrameworkCore;

namespace ClaimsHub.Data;

public class ClaimsDbContext : DbContext
{
    public ClaimsDbContext(DbContextOptions<ClaimsDbContext> options) : base(options) { }

    public DbSet<Policy> Policies => Set<Policy>();
    public DbSet<Customer> Customers => Set<Customer>();
    public DbSet<Claim> Claims => Set<Claim>();
    public DbSet<ClaimLine> ClaimLines => Set<ClaimLine>();
    public DbSet<Payment> Payments => Set<Payment>();
    public DbSet<ClaimNote> ClaimNotes => Set<ClaimNote>();
    public DbSet<Adjuster> Adjusters => Set<Adjuster>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<Policy>().HasOne(p => p.Customer).WithMany(c => c.Policies).HasForeignKey(p => p.CustomerId);
        modelBuilder.Entity<Claim>().HasOne(c => c.Policy).WithMany(p => p.Claims).HasForeignKey(c => c.PolicyId);
        modelBuilder.Entity<ClaimLine>().HasOne(l => l.Claim).WithMany(c => c.Lines).HasForeignKey(l => l.ClaimId);
        modelBuilder.Entity<Payment>().HasOne(p => p.Claim).WithMany(c => c.Payments).HasForeignKey(p => p.ClaimId);
        modelBuilder.Entity<ClaimNote>().HasOne(n => n.Claim).WithMany(c => c.Notes).HasForeignKey(n => n.ClaimId);
        modelBuilder.Entity<Claim>().HasIndex(c => c.ClaimNumber).IsUnique();
        modelBuilder.Entity<Claim>().Property(c => c.ReserveAmount).HasPrecision(18, 2);
        modelBuilder.Entity<Claim>().Property(c => c.PaidAmount).HasPrecision(18, 2);
    }
}
