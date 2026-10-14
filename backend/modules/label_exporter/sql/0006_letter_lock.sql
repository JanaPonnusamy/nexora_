-- Label Exporter: per-letter lock.
--
-- Owner requirement: once a shelf letter's review is complete, a super-admin
-- can LOCK it so the Y/N review, unit correction and location-assignment
-- controls for that letter become read-only on the grid. Lock is letter-wide
-- (not per-row) since the workflow is "walk the shelf one letter at a time,
-- then seal it" - a single row stuck mid-review would defeat the point.
--
-- Idempotent: guarded by OBJECT_ID, so ensure_schema() can run it on every
-- startup like the rest of this module's DDL.

IF OBJECT_ID('dbo.label_letter_lock', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.label_letter_lock (
        id          UNIQUEIDENTIFIER NOT NULL
                    CONSTRAINT PK_label_letter_lock PRIMARY KEY
                    CONSTRAINT DF_label_letter_lock_id DEFAULT NEWID(),
        tenant_id   UNIQUEIDENTIFIER NOT NULL,
        store_id    UNIQUEIDENTIFIER NOT NULL,
        letter      CHAR(1) NOT NULL,
        locked_by   UNIQUEIDENTIFIER NULL,
        locked_at   DATETIME2 NULL,
        CONSTRAINT UQ_label_letter_lock UNIQUE (tenant_id, store_id, letter)
    );
END;
GO
