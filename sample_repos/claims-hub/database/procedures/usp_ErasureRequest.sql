-- GDPR right to erasure: pseudonymise a customer whose policies have all expired and claims are closed.
CREATE OR ALTER PROCEDURE claims.usp_ErasureRequest
    @CustomerId  BIGINT,
    @RequestedBy NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @ActivePolicies INT;
    DECLARE @OpenClaims INT;
    DECLARE @RetentionCutoff DATE = DATEADD(YEAR, -10, CAST(SYSUTCDATETIME() AS DATE));

    SELECT @ActivePolicies = COUNT(*)
    FROM claims.Policy p
    WHERE p.CustomerId = @CustomerId
      AND p.EndDate >= CAST(SYSUTCDATETIME() AS DATE);

    SELECT @OpenClaims = COUNT(*)
    FROM claims.Claim c
    JOIN claims.Policy p ON p.PolicyId = c.PolicyId
    WHERE p.CustomerId = @CustomerId
      AND (c.Status NOT IN ('CLOSED', 'SETTLED') OR c.ClosedAt >= @RetentionCutoff);

    IF @ActivePolicies > 0
        THROW 50061, 'Customer still has active policies.', 1;

    IF @OpenClaims > 0
        THROW 50062, 'Customer has claims inside the legal retention period.', 1;

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE claims.Customer
        SET FullName = CONCAT('ERASED-', CustomerId),
            Email = NULL
        WHERE CustomerId = @CustomerId;

        UPDATE n
        SET n.Body = N'[erased]'
        FROM claims.ClaimNote n
        JOIN claims.Claim c ON c.ClaimId = n.ClaimId
        JOIN claims.Policy p ON p.PolicyId = c.PolicyId
        WHERE p.CustomerId = @CustomerId;

        UPDATE pay
        SET pay.PayeeIban = 'ERASED'
        FROM claims.Payment pay
        JOIN claims.Claim c ON c.ClaimId = pay.ClaimId
        JOIN claims.Policy p ON p.PolicyId = c.PolicyId
        WHERE p.CustomerId = @CustomerId;

        INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
        VALUES ('Customer', @CustomerId, 'ERASURE', 'GDPR Article 17 request completed', @RequestedBy);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO
