CREATE OR ALTER PROCEDURE claims.usp_AdjustReserve
    @ClaimId     BIGINT,
    @NewReserve  DECIMAL(18,2),
    @AdjustedBy  NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @OldReserve DECIMAL(18,2);
    DECLARE @Status VARCHAR(20);
    DECLARE @AdjusterId INT;
    DECLARE @AuthorityLimit DECIMAL(18,2);
    DECLARE @CoverageLimit DECIMAL(18,2);
    DECLARE @PaidAmount DECIMAL(18,2);

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT @OldReserve = c.ReserveAmount,
               @Status = c.Status,
               @AdjusterId = c.AdjusterId,
               @PaidAmount = c.PaidAmount,
               @CoverageLimit = p.CoverageLimit
        FROM claims.Claim c WITH (UPDLOCK, HOLDLOCK)
        JOIN claims.Policy p ON p.PolicyId = c.PolicyId
        WHERE c.ClaimId = @ClaimId;

        IF @OldReserve IS NULL
            THROW 50001, 'Claim not found.', 1;

        IF @Status IN ('CLOSED', 'SETTLED')
            THROW 50002, 'Reserve cannot change on a closed claim.', 1;

        IF @NewReserve < 0
            THROW 50003, 'Reserve cannot be negative.', 1;

        IF @NewReserve + @PaidAmount > @CoverageLimit
            THROW 50004, 'Reserve plus payments exceed the policy coverage limit.', 1;

        SELECT @AuthorityLimit = a.AuthorityLimit
        FROM claims.Adjuster a
        WHERE a.AdjusterId = @AdjusterId;

        IF @AuthorityLimit IS NOT NULL AND @NewReserve > @AuthorityLimit
        BEGIN
            INSERT INTO claims.ClaimNote (ClaimId, Author, Body)
            VALUES (@ClaimId, @AdjustedBy, CONCAT('Reserve of ', @NewReserve, ' exceeds adjuster authority; referred to supervisor.'));

            UPDATE claims.Claim
            SET Status = 'REFERRED'
            WHERE ClaimId = @ClaimId;
        END

        UPDATE claims.Claim
        SET ReserveAmount = @NewReserve
        WHERE ClaimId = @ClaimId;

        INSERT INTO claims.ReserveHistory (ClaimId, OldReserve, NewReserve, ChangedBy)
        VALUES (@ClaimId, @OldReserve, @NewReserve, @AdjustedBy);

        INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
        VALUES ('Claim', @ClaimId, 'RESERVE', CONCAT(@OldReserve, ' -> ', @NewReserve), @AdjustedBy);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO
