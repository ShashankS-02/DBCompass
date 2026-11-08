using ClaimsHub.Data;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;

namespace ClaimsHub.Controllers;

[ApiController]
[Route("api/claims")]
public class ClaimsController : ControllerBase
{
    private readonly ClaimsDbContext _db;

    public ClaimsController(ClaimsDbContext db) => _db = db;

    [HttpGet("{claimNumber}")]
    public async Task<IActionResult> GetClaim(string claimNumber)
    {
        var claim = await _db.Claims
            .Include(c => c.Lines)
            .Include(c => c.Payments)
            .FirstOrDefaultAsync(c => c.ClaimNumber == claimNumber);
        return claim is null ? NotFound() : Ok(claim);
    }

    [HttpPost("{claimId:long}/reserve")]
    public async Task<IActionResult> AdjustReserve(long claimId, [FromBody] decimal newReserve)
    {
        await _db.Database.ExecuteSqlRawAsync(
            "EXEC claims.usp_AdjustReserve @ClaimId, @NewReserve, @AdjustedBy",
            new SqlParameter("@ClaimId", claimId),
            new SqlParameter("@NewReserve", newReserve),
            new SqlParameter("@AdjustedBy", User.Identity?.Name ?? "system"));
        return NoContent();
    }

    [HttpPost("{claimId:long}/settle")]
    public async Task<IActionResult> Settle(long claimId)
    {
        await _db.Database.ExecuteSqlRawAsync("EXEC claims.usp_SettleClaim @ClaimId", new SqlParameter("@ClaimId", claimId));
        return NoContent();
    }

    [HttpGet("open-by-region")]
    public async Task<IActionResult> OpenByRegion()
    {
        var rows = await _db.Claims
            .Where(c => c.Status == "OPEN")
            .GroupBy(c => c.Policy!.Customer!.CountryCode)
            .Select(g => new { Country = g.Key, Count = g.Count(), Reserve = g.Sum(c => c.ReserveAmount) })
            .ToListAsync();
        return Ok(rows);
    }
}
