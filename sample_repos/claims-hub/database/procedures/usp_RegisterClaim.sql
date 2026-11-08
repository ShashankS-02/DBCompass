CREATE OR ALTER PROCEDURE claims.usp_RegisterClaim
    @PolicyNumber  VARCHAR(30),
    @LossDate      DATE,
    @CoverageCode  VARCHAR(20),
    @ClaimedAmount DECIMAL(18,2),
    @Description   NVARCHAR(MAX),
    @ReportedBy    NVARCHAR(100),
    @ClaimId       BIGINT OUTPUT,
    @ClaimNumber   VARCHAR(30) OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @PolicyId BIGINT;
    DECLARE @StartDate DATE;
    DECLARE @EndDate DATE;
    DECLARE @Region VARCHAR(10);
    DECLARE @AdjusterId INT;
    DECLARE @Sequence INT;

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT @PolicyId = p.PolicyId,
               @StartDate = p.StartDate,
               @EndDate = p.EndDate,
               @Region = cu.CountryCode
        FROM claims.Policy p
        JOIN claims.Customer cu ON cu.CustomerId = p.CustomerId
        WHERE p.PolicyNumber = @PolicyNumber;

        IF @PolicyId IS NULL
            THROW 50031, 'Policy not found.', 1;

        IF @LossDate NOT BETWEEN @StartDate AND @EndDate
            THROW 50032, 'Loss date is outside the policy period.', 1;

        -- Least-loaded adjuster in the customer's region.
        SELECT TOP (1) @AdjusterId = a.AdjusterId
        FROM claims.Adjuster a
        LEFT JOIN claims.Claim c ON c.AdjusterId = a.AdjusterId AND c.Status IN ('OPEN', 'REFERRED')
        WHERE a.Region = @Region
        GROUP BY a.AdjusterId
        ORDER BY COUNT(c.ClaimId) ASC, a.AdjusterId ASC;

        SELECT @Sequence = NEXT VALUE FOR claims.seq_ClaimNumber;
        SET @ClaimNumber = CONCAT('CL-', YEAR(@LossDate), '-', RIGHT(CONCAT('0000000', @Sequence), 7));

        INSERT INTO claims.Claim (ClaimNumber, PolicyId, AdjusterId, LossDate, ReserveAmount)
        VALUES (@ClaimNumber, @PolicyId, @AdjusterId, @LossDate, @ClaimedAmount);

        SET @ClaimId = SCOPE_IDENTITY();

        INSERT INTO claims.ClaimLine (ClaimId, CoverageCode, ClaimedAmount)
        VALUES (@ClaimId, @CoverageCode, @ClaimedAmount);

        INSERT INTO claims.ClaimNote (ClaimId, Author, Body)
        VALUES (@ClaimId, @ReportedBy, @Description);

        INSERT INTO claims.ReserveHistory (ClaimId, OldReserve, NewReserve, ChangedBy)
        VALUES (@ClaimId, 0, @ClaimedAmount, @ReportedBy);

        INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
        VALUES ('Claim', @ClaimId, 'REGISTER', @ClaimNumber, @ReportedBy);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH

    EXEC claims.usp_ScoreFraud @ClaimId = @ClaimId;
END
GO
