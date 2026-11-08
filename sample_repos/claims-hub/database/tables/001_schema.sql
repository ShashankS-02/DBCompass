CREATE SCHEMA claims;
GO

CREATE TABLE claims.Customer (
    CustomerId     BIGINT IDENTITY(1,1) PRIMARY KEY,
    FullName       NVARCHAR(200) NOT NULL,
    CountryCode    CHAR(2)       NOT NULL,
    Email          NVARCHAR(320) NULL,
    CreatedAt      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE claims.Policy (
    PolicyId       BIGINT IDENTITY(1,1) PRIMARY KEY,
    PolicyNumber   VARCHAR(30)   NOT NULL UNIQUE,
    ProductCode    VARCHAR(20)   NOT NULL,
    CustomerId     BIGINT        NOT NULL REFERENCES claims.Customer(CustomerId),
    StartDate      DATE          NOT NULL,
    EndDate        DATE          NOT NULL,
    Deductible     DECIMAL(18,2) NOT NULL DEFAULT 0,
    CoverageLimit  DECIMAL(18,2) NOT NULL
);

CREATE TABLE claims.Adjuster (
    AdjusterId     INT IDENTITY(1,1) PRIMARY KEY,
    Name           NVARCHAR(200) NOT NULL,
    Region         VARCHAR(10)   NOT NULL,
    AuthorityLimit DECIMAL(18,2) NOT NULL
);

CREATE TABLE claims.Claim (
    ClaimId        BIGINT IDENTITY(1,1) PRIMARY KEY,
    ClaimNumber    VARCHAR(30)   NOT NULL UNIQUE,
    PolicyId       BIGINT        NOT NULL REFERENCES claims.Policy(PolicyId),
    AdjusterId     INT           NULL REFERENCES claims.Adjuster(AdjusterId),
    LossDate       DATE          NOT NULL,
    ReportedAt     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    Status         VARCHAR(20)   NOT NULL DEFAULT 'OPEN',
    ReserveAmount  DECIMAL(18,2) NOT NULL DEFAULT 0,
    PaidAmount     DECIMAL(18,2) NOT NULL DEFAULT 0,
    FraudScore     INT           NOT NULL DEFAULT 0,
    ClosedAt       DATETIME2     NULL
)
ON ps_ClaimsByYear(LossDate);

CREATE TABLE claims.ClaimLine (
    ClaimLineId    BIGINT IDENTITY(1,1) PRIMARY KEY,
    ClaimId        BIGINT        NOT NULL REFERENCES claims.Claim(ClaimId),
    CoverageCode   VARCHAR(20)   NOT NULL,
    ClaimedAmount  DECIMAL(18,2) NOT NULL,
    ApprovedAmount DECIMAL(18,2) NOT NULL DEFAULT 0
);

CREATE TABLE claims.Payment (
    PaymentId      BIGINT IDENTITY(1,1) PRIMARY KEY,
    ClaimId        BIGINT        NOT NULL REFERENCES claims.Claim(ClaimId),
    Amount         DECIMAL(18,2) NOT NULL,
    PaidAt         DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME(),
    PayeeIban      VARCHAR(34)   NOT NULL
);

CREATE TABLE claims.ClaimNote (
    ClaimNoteId    BIGINT IDENTITY(1,1) PRIMARY KEY,
    ClaimId        BIGINT        NOT NULL REFERENCES claims.Claim(ClaimId),
    Author         NVARCHAR(100) NOT NULL,
    Body           NVARCHAR(MAX) NOT NULL,
    CreatedAt      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE claims.ReserveHistory (
    ReserveHistoryId BIGINT IDENTITY(1,1) PRIMARY KEY,
    ClaimId        BIGINT        NOT NULL REFERENCES claims.Claim(ClaimId),
    OldReserve     DECIMAL(18,2) NOT NULL,
    NewReserve     DECIMAL(18,2) NOT NULL,
    ChangedBy      NVARCHAR(100) NOT NULL,
    ChangedAt      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE claims.FraudSignal (
    FraudSignalId  BIGINT IDENTITY(1,1) PRIMARY KEY,
    ClaimId        BIGINT        NOT NULL REFERENCES claims.Claim(ClaimId),
    SignalCode     VARCHAR(30)   NOT NULL,
    Weight         INT           NOT NULL,
    DetectedAt     DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE claims.AuditLog (
    AuditLogId     BIGINT IDENTITY(1,1) PRIMARY KEY,
    EntityName     VARCHAR(50)   NOT NULL,
    EntityId       BIGINT        NOT NULL,
    Action         VARCHAR(20)   NOT NULL,
    Detail         NVARCHAR(MAX) NULL,
    ChangedBy      NVARCHAR(100) NOT NULL,
    ChangedAt      DATETIME2     NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE INDEX IX_Claim_Status_LossDate ON claims.Claim(Status, LossDate) INCLUDE (ReserveAmount, PaidAmount);
CREATE INDEX IX_Payment_ClaimId ON claims.Payment(ClaimId);
