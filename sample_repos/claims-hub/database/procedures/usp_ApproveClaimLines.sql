CREATE OR ALTER PROCEDURE claims.usp_ApproveClaimLines
    @ClaimId     BIGINT,
    @ApprovedBy  NVARCHAR(100),
    @Lines       NVARCHAR(MAX)   -- JSON: [{"claimLineId": 1, "approvedAmount": 1200.00}, ...]
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @Status VARCHAR(20);
    DECLARE @FraudScore INT;
    DECLARE @AuthorityLimit DECIMAL(18,2);
    DECLARE @TotalApproved DECIMAL(18,2);
    DECLARE @CoverageLimit DECIMAL(18,2);
    DECLARE @Paid DECIMAL(18,2);

    DECLARE @Requested TABLE (ClaimLineId BIGINT PRIMARY KEY, ApprovedAmount DECIMAL(18,2));

    INSERT INTO @Requested (ClaimLineId, ApprovedAmount)
    SELECT j.claimLineId, j.approvedAmount
    FROM OPENJSON(@Lines) WITH (claimLineId BIGINT '$.claimLineId', approvedAmount DECIMAL(18,2) '$.approvedAmount') j;

    BEGIN TRY
        BEGIN TRANSACTION;

        SELECT @Status = c.Status,
               @FraudScore = c.FraudScore,
               @Paid = c.PaidAmount,
               @AuthorityLimit = a.AuthorityLimit,
               @CoverageLimit = p.CoverageLimit
        FROM claims.Claim c WITH (UPDLOCK, HOLDLOCK)
        JOIN claims.Policy p ON p.PolicyId = c.PolicyId
        LEFT JOIN claims.Adjuster a ON a.AdjusterId = c.AdjusterId
        WHERE c.ClaimId = @ClaimId;

        IF @Status IS NULL
            THROW 50051, 'Claim not found.', 1;

        IF @Status NOT IN ('OPEN', 'REFERRED')
            THROW 50052, 'Lines can only be approved on open or referred claims.', 1;

        IF EXISTS (
            SELECT 1 FROM @Requested r
            LEFT JOIN claims.ClaimLine l ON l.ClaimLineId = r.ClaimLineId AND l.ClaimId = @ClaimId
            WHERE l.ClaimLineId IS NULL
        )
            THROW 50053, 'One or more lines do not belong to this claim.', 1;

        IF EXISTS (
            SELECT 1 FROM @Requested r
            JOIN claims.ClaimLine l ON l.ClaimLineId = r.ClaimLineId
            WHERE r.ApprovedAmount < 0 OR r.ApprovedAmount > l.ClaimedAmount
        )
            THROW 50054, 'Approved amount must be between zero and the claimed amount.', 1;

        UPDATE l
        SET l.ApprovedAmount = r.ApprovedAmount
        FROM claims.ClaimLine l
        JOIN @Requested r ON r.ClaimLineId = l.ClaimLineId;

        SELECT @TotalApproved = SUM(l.ApprovedAmount)
        FROM claims.ClaimLine l
        WHERE l.ClaimId = @ClaimId;

        IF @TotalApproved > @CoverageLimit
            THROW 50055, 'Total approved exceeds the coverage limit.', 1;

        UPDATE claims.Claim
        SET Status = CASE
                         WHEN @FraudScore >= 70 THEN 'FRAUD_REVIEW'
                         WHEN @AuthorityLimit IS NOT NULL AND @TotalApproved > @AuthorityLimit THEN 'REFERRED'
                         ELSE 'APPROVED'
                     END,
            ReserveAmount = CASE WHEN @TotalApproved - @Paid > 0 THEN @TotalApproved - @Paid ELSE 0 END
        WHERE ClaimId = @ClaimId;

        INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
        VALUES ('Claim', @ClaimId, 'APPROVE_LINES', CONCAT('Total approved ', @TotalApproved), @ApprovedBy);

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
GO
