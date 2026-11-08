CREATE OR ALTER PROCEDURE claims.usp_CloseStaleClaims
    @IdleDays INT = 365
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Closed TABLE (ClaimId BIGINT PRIMARY KEY, OldReserve DECIMAL(18,2));

    BEGIN TRY
        BEGIN TRANSACTION;

        UPDATE c
        SET c.Status = 'CLOSED',
            c.ReserveAmount = 0,
            c.ClosedAt = SYSUTCDATETIME()
        OUTPUT inserted.ClaimId, deleted.ReserveAmount INTO @Closed (ClaimId, OldReserve)
        FROM claims.Claim c
        WHERE c.Status = 'OPEN'
          AND NOT EXISTS (
              SELECT 1 FROM claims.ClaimNote n
              WHERE n.ClaimId = c.ClaimId
                AND n.CreatedAt >= DATEADD(DAY, -@IdleDays, SYSUTCDATETIME())
          )
          AND NOT EXISTS (
              SELECT 1 FROM claims.Payment p
              WHERE p.ClaimId = c.ClaimId
                AND p.PaidAt >= DATEADD(DAY, -@IdleDays, SYSUTCDATETIME())
          );

        INSERT INTO claims.ReserveHistory (ClaimId, OldReserve, NewReserve, ChangedBy)
        SELECT ClaimId, OldReserve, 0, 'stale-claims-job' FROM @Closed;

        INSERT INTO claims.ClaimNote (ClaimId, Author, Body)
        SELECT ClaimId, 'stale-claims-job', CONCAT('Closed after ', @IdleDays, ' days without activity.') FROM @Closed;

        INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
        SELECT 'Claim', ClaimId, 'AUTO_CLOSE', NULL, 'stale-claims-job' FROM @Closed;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO
