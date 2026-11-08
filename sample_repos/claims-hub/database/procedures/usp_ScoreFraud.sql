CREATE OR ALTER PROCEDURE claims.usp_ScoreFraud
    @ClaimId BIGINT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @PolicyId BIGINT;
    DECLARE @CustomerId BIGINT;
    DECLARE @LossDate DATE;
    DECLARE @StartDate DATE;
    DECLARE @ReportedAt DATETIME2;
    DECLARE @Claimed DECIMAL(18,2);
    DECLARE @CoverageLimit DECIMAL(18,2);
    DECLARE @PriorClaims INT;
    DECLARE @SharedIbans INT;
    DECLARE @Score INT = 0;

    SELECT @PolicyId = c.PolicyId,
           @LossDate = c.LossDate,
           @ReportedAt = c.ReportedAt,
           @StartDate = p.StartDate,
           @CustomerId = p.CustomerId,
           @CoverageLimit = p.CoverageLimit
    FROM claims.Claim c
    JOIN claims.Policy p ON p.PolicyId = c.PolicyId
    WHERE c.ClaimId = @ClaimId;

    IF @PolicyId IS NULL
        THROW 50021, 'Claim not found.', 1;

    DELETE FROM claims.FraudSignal WHERE ClaimId = @ClaimId;

    -- Loss shortly after the policy started.
    IF DATEDIFF(DAY, @StartDate, @LossDate) BETWEEN 0 AND 30
    BEGIN
        INSERT INTO claims.FraudSignal (ClaimId, SignalCode, Weight) VALUES (@ClaimId, 'EARLY_LOSS', 25);
        SET @Score += 25;
    END

    -- Late reporting.
    IF DATEDIFF(DAY, @LossDate, @ReportedAt) > 60
    BEGIN
        INSERT INTO claims.FraudSignal (ClaimId, SignalCode, Weight) VALUES (@ClaimId, 'LATE_REPORT', 15);
        SET @Score += 15;
    END

    -- Claimed amount close to the limit.
    SELECT @Claimed = SUM(l.ClaimedAmount) FROM claims.ClaimLine l WHERE l.ClaimId = @ClaimId;
    IF @Claimed >= @CoverageLimit * 0.9
    BEGIN
        INSERT INTO claims.FraudSignal (ClaimId, SignalCode, Weight) VALUES (@ClaimId, 'NEAR_LIMIT', 20);
        SET @Score += 20;
    END

    -- Frequent claimant.
    SELECT @PriorClaims = COUNT(*)
    FROM claims.Claim c
    JOIN claims.Policy p ON p.PolicyId = c.PolicyId
    WHERE p.CustomerId = @CustomerId
      AND c.ClaimId <> @ClaimId
      AND c.LossDate >= DATEADD(YEAR, -3, @LossDate);
    IF @PriorClaims >= 3
    BEGIN
        INSERT INTO claims.FraudSignal (ClaimId, SignalCode, Weight) VALUES (@ClaimId, 'FREQUENT_CLAIMANT', 20);
        SET @Score += 20;
    END

    -- Payee account shared with other customers.
    SELECT @SharedIbans = COUNT(DISTINCT p2.CustomerId)
    FROM claims.Payment pay
    JOIN claims.Payment other ON other.PayeeIban = pay.PayeeIban AND other.ClaimId <> pay.ClaimId
    JOIN claims.Claim c2 ON c2.ClaimId = other.ClaimId
    JOIN claims.Policy p2 ON p2.PolicyId = c2.PolicyId
    WHERE pay.ClaimId = @ClaimId
      AND p2.CustomerId <> @CustomerId;
    IF @SharedIbans > 0
    BEGIN
        INSERT INTO claims.FraudSignal (ClaimId, SignalCode, Weight) VALUES (@ClaimId, 'SHARED_PAYEE', 30);
        SET @Score += 30;
    END

    UPDATE claims.Claim
    SET FraudScore = CASE WHEN @Score > 100 THEN 100 ELSE @Score END
    WHERE ClaimId = @ClaimId;

    INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
    VALUES ('Claim', @ClaimId, 'FRAUD_SCORE', CONCAT('Score ', @Score), SUSER_SNAME());
END
GO
