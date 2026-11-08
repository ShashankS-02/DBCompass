CREATE OR ALTER PROCEDURE claims.usp_RegulatorExport
    @PeriodStart DATE,
    @PeriodEnd   DATE
AS
BEGIN
    SET NOCOUNT ON;

    IF @PeriodEnd < @PeriodStart
        THROW 50041, 'Period end is before period start.', 1;

    ;WITH claim_totals AS (
        SELECT c.ClaimId,
               cu.CountryCode,
               p.ProductCode,
               c.Status,
               c.ReserveAmount,
               c.PaidAmount,
               c.FraudScore,
               YEAR(c.LossDate) AS LossYear
        FROM claims.Claim c
        JOIN claims.Policy p ON p.PolicyId = c.PolicyId
        JOIN claims.Customer cu ON cu.CustomerId = p.CustomerId
        WHERE c.LossDate BETWEEN @PeriodStart AND @PeriodEnd
    ),
    payments_in_period AS (
        SELECT pay.ClaimId, SUM(pay.Amount) AS PaidInPeriod
        FROM claims.Payment pay
        WHERE pay.PaidAt >= @PeriodStart
          AND pay.PaidAt < DATEADD(DAY, 1, @PeriodEnd)
        GROUP BY pay.ClaimId
    )
    SELECT t.CountryCode,
           t.ProductCode,
           t.LossYear,
           COUNT(*) AS ClaimCount,
           SUM(CASE WHEN t.Status = 'SETTLED' THEN 1 ELSE 0 END) AS SettledCount,
           SUM(CASE WHEN t.FraudScore >= 70 THEN 1 ELSE 0 END) AS FraudHeldCount,
           SUM(t.ReserveAmount) AS OutstandingReserve,
           SUM(t.PaidAmount) AS PaidToDate,
           SUM(ISNULL(pp.PaidInPeriod, 0)) AS PaidInPeriod,
           AVG(t.PaidAmount + t.ReserveAmount) AS AverageIncurred
    FROM claim_totals t
    LEFT JOIN payments_in_period pp ON pp.ClaimId = t.ClaimId
    GROUP BY t.CountryCode, t.ProductCode, t.LossYear
    ORDER BY t.CountryCode, t.ProductCode, t.LossYear;

    INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
    VALUES ('Job', 0, 'REGULATOR_EXPORT', CONCAT(@PeriodStart, ' to ', @PeriodEnd), SUSER_SNAME());
END
GO
