CREATE OR ALTER PROCEDURE claims.usp_RecalculateReserves
    @AsOfDate DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @AsOfDate IS NULL
        SET @AsOfDate = CAST(SYSUTCDATETIME() AS DATE);

    DECLARE @ClaimId BIGINT;
    DECLARE @Claimed DECIMAL(18,2);
    DECLARE @Approved DECIMAL(18,2);
    DECLARE @Paid DECIMAL(18,2);
    DECLARE @Current DECIMAL(18,2);
    DECLARE @Target DECIMAL(18,2);
    DECLARE @AgeDays INT;
    DECLARE @Updated INT = 0;

    DECLARE claim_cursor CURSOR LOCAL FAST_FORWARD FOR
        SELECT c.ClaimId, c.ReserveAmount, c.PaidAmount, DATEDIFF(DAY, c.LossDate, @AsOfDate)
        FROM claims.Claim c
        WHERE c.Status IN ('OPEN', 'REFERRED', 'APPROVED');

    OPEN claim_cursor;
    FETCH NEXT FROM claim_cursor INTO @ClaimId, @Current, @Paid, @AgeDays;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SELECT @Claimed = SUM(l.ClaimedAmount),
               @Approved = SUM(l.ApprovedAmount)
        FROM claims.ClaimLine l
        WHERE l.ClaimId = @ClaimId;

        -- Approved lines reserve at 100%; unapproved lines decay with claim age.
        SET @Target = ISNULL(@Approved, 0)
                    + (ISNULL(@Claimed, 0) - ISNULL(@Approved, 0))
                      * CASE
                            WHEN @AgeDays < 90 THEN 1.00
                            WHEN @AgeDays < 180 THEN 0.85
                            WHEN @AgeDays < 365 THEN 0.70
                            ELSE 0.50
                        END
                    - ISNULL(@Paid, 0);

        IF @Target < 0
            SET @Target = 0;

        IF ABS(@Target - @Current) >= 1
        BEGIN
            UPDATE claims.Claim SET ReserveAmount = @Target WHERE ClaimId = @ClaimId;

            INSERT INTO claims.ReserveHistory (ClaimId, OldReserve, NewReserve, ChangedBy)
            VALUES (@ClaimId, @Current, @Target, 'reserve-job');

            SET @Updated += 1;
        END

        FETCH NEXT FROM claim_cursor INTO @ClaimId, @Current, @Paid, @AgeDays;
    END

    CLOSE claim_cursor;
    DEALLOCATE claim_cursor;

    INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
    VALUES ('Job', 0, 'RESERVE_RECALC', CONCAT(@Updated, ' claims updated as of ', @AsOfDate), 'reserve-job');
END
GO
