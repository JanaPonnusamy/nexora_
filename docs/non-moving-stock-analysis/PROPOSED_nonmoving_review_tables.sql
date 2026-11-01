-- ============================================================================
-- PROPOSAL ONLY -- NOT APPLIED. Do not run without separate authorization.
-- ============================================================================
-- Non-Moving Stock Analysis: shared manual-review list + transfer-proposal
-- register. Additive (new tables only, no change to any existing object).
--
-- Why: today the review list and the "reviewed ✓ / ✕" marks on transfer
-- recommendations are kept in the Stock Client's localStorage (per PC), and a
-- transfer proposal is only an Excel file. A shared, audited record is needed
-- before several buyers can work the same list or a proposal can be tracked
-- to approval. Executing a transfer stays in the existing authorised process.
-- SQL Server 2014 compatible.
-- ============================================================================

IF OBJECT_ID('procurement.nonmoving_review_items') IS NULL
CREATE TABLE procurement.nonmoving_review_items (
    review_item_id   UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_nmri_id DEFAULT NEWID(),
    tenant_id        UNIQUEIDENTIFIER NOT NULL,
    store_id         UNIQUEIDENTIFIER NOT NULL,
    product_code     VARCHAR(100)     NOT NULL,
    classification   VARCHAR(20)      NULL,      -- snapshot when added
    days_since_sale  INT              NULL,
    cost_value       DECIMAL(18,2)    NULL,
    note             NVARCHAR(500)    NULL,
    status           VARCHAR(20)      NOT NULL CONSTRAINT DF_nmri_status DEFAULT 'OPEN',  -- OPEN / DONE / DROPPED
    created_by       UNIQUEIDENTIFIER NULL,
    created_at       DATETIME2(0)     NOT NULL CONSTRAINT DF_nmri_created DEFAULT SYSDATETIME(),
    closed_by        UNIQUEIDENTIFIER NULL,
    closed_at        DATETIME2(0)     NULL,
    CONSTRAINT PK_nonmoving_review_items PRIMARY KEY (review_item_id)
);
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_nmri_open_item')
CREATE UNIQUE INDEX UX_nmri_open_item
    ON procurement.nonmoving_review_items (tenant_id, store_id, product_code)
    WHERE status = 'OPEN';
GO

IF OBJECT_ID('procurement.transfer_proposals') IS NULL
CREATE TABLE procurement.transfer_proposals (
    proposal_id      UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_tp_id DEFAULT NEWID(),
    tenant_id        UNIQUEIDENTIFIER NOT NULL,
    status           VARCHAR(20)      NOT NULL CONSTRAINT DF_tp_status DEFAULT 'DRAFT',  -- DRAFT / SUBMITTED / APPROVED / REJECTED
    created_by       UNIQUEIDENTIFIER NULL,
    created_at       DATETIME2(0)     NOT NULL CONSTRAINT DF_tp_created DEFAULT SYSDATETIME(),
    decided_by       UNIQUEIDENTIFIER NULL,
    decided_at       DATETIME2(0)     NULL,
    remarks          NVARCHAR(500)    NULL,
    CONSTRAINT PK_transfer_proposals PRIMARY KEY (proposal_id)
);
GO

IF OBJECT_ID('procurement.transfer_proposal_lines') IS NULL
CREATE TABLE procurement.transfer_proposal_lines (
    proposal_line_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_tpl_id DEFAULT NEWID(),
    proposal_id      UNIQUEIDENTIFIER NOT NULL,
    source_store_id  UNIQUEIDENTIFIER NOT NULL,
    source_code      VARCHAR(100)     NOT NULL,
    dest_store_id    UNIQUEIDENTIFIER NOT NULL,
    dest_code        VARCHAR(100)     NOT NULL,
    suggested_qty    DECIMAL(18,3)    NOT NULL,
    approved_qty     DECIMAL(18,3)    NULL,
    transfer_value   DECIMAL(18,2)    NULL,      -- at source cost, snapshot
    reason           NVARCHAR(400)    NULL,
    calculation      NVARCHAR(1000)   NULL,
    CONSTRAINT PK_transfer_proposal_lines PRIMARY KEY (proposal_line_id),
    CONSTRAINT FK_tpl_proposal FOREIGN KEY (proposal_id) REFERENCES procurement.transfer_proposals (proposal_id)
);
GO
