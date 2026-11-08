CREATE OR ALTER TRIGGER claims.trg_PaymentAudit
ON claims.Payment
AFTER INSERT, UPDATE, DELETE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
    SELECT 'Payment', i.PaymentId,
           CASE WHEN d.PaymentId IS NULL THEN 'INSERT' ELSE 'UPDATE' END,
           CONCAT('Claim ', i.ClaimId, ' amount ', i.Amount),
           SUSER_SNAME()
    FROM inserted i
    LEFT JOIN deleted d ON d.PaymentId = i.PaymentId;

    INSERT INTO claims.AuditLog (EntityName, EntityId, Action, Detail, ChangedBy)
    SELECT 'Payment', d.PaymentId, 'DELETE', CONCAT('Claim ', d.ClaimId, ' amount ', d.Amount), SUSER_SNAME()
    FROM deleted d
    WHERE NOT EXISTS (SELECT 1 FROM inserted i WHERE i.PaymentId = d.PaymentId);
END
GO

CREATE SEQUENCE claims.seq_ClaimNumber START WITH 1 INCREMENT BY 1;
GO
