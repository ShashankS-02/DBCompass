CREATE OR ALTER PROCEDURE claims.usp_SettleClaim
    @ClaimId BIGINT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Approved DECIMAL(18,2);
    DECLARE @Paid DECIMAL(18,2);
    DECLARE @Deductible DECIMAL(18,2);
    DECLARE @Outstanding DECIMAL(18,2);
    DECLARE @FraudScore INT;
    DECLARE @PayeeIban VARCHAR(34);
    DECLARE @Status VARCHAR(20);

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT @Status = c.Status,
               @Paid = c.PaidAmount,
               @FraudScore = c.FraudScore,
               @Deductible = p.Deductible
        FROM claims.Claim c WITH (UPDLOCK, HOLDLOCK)
        JOIN claims.Policy p ON p.PolicyId = c.PolicyId
        WHERE c.ClaimId = @ClaimId;

        IF @Status IS NULL
            THROW 50011, 'Claim not found.', 1;

        IF @Status <> 'APPROVED'
            THROW 50012, 'Only approved claims can be settled.', 1;

        IF @FraudScore >= 70
            THROW 50013, 'Claim is held for fraud review.', 1;

        SELECT @Approved = SUM(l.ApprovedAmount)
        FROM claims.ClaimLine l
        WHERE l.ClaimId = @ClaimId;

        SET @Outstanding = ISNULL(@Approved, 0) - @Deductible - @Paid;

        IF @Outstanding > 0
        BEGIN
            SELECT TOP (1) @PayeeIban = p.PayeeIban
            FROM claims.Payment p
            WHERE p.ClaimId = @ClaimId
            ORDER BY p.PaidAt DESC;

            IF @PayeeIban IS NULL
                THROW 50014, 'No payee account on file for this claim.', 1;

            INSERT INTO claims.Payment (ClaimId, Amount, PayeeIban)
            VALUES (@ClaimId, @Outstanding, @PayeeIban);

            UPDATE claims.Claim
            SET PaidAmount = PaidAmount + @Outstanding
            WHERE ClaimId = @ClaimId;
        END

        UPDATE claims.Claim
        SET Status = 'SETTLED',
            ReserveAmount = 0,
            ClosedAt = SYSUTCDATETIME()
        WHERE ClaimId = @ClaimId;

        INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
        VALUES ('Claim', @ClaimId, 'SETTLE', CONCAT('Final payment ', @Outstanding), SUSER_SNAME());

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO
