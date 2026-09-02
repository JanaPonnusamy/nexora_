-- Replaces the suggestion-approval workflow from 0001 with a simpler model:
-- a single free-text 'remarks' field (predefined-list-or-custom, e.g. a unit
-- description correction or a shelf tip like "Counter"/"SYP"), reviewed
-- directly by whoever assigns the sublocation rather than through a
-- separate approval queue. This table was only added earlier the same day
-- and has no real data, so the old columns are dropped outright rather than
-- deprecated in place.

IF EXISTS (SELECT 1 FROM sys.default_constraints WHERE name = 'DF_label_review_suggestion_status')
BEGIN
    ALTER TABLE dbo.label_review DROP CONSTRAINT DF_label_review_suggestion_status;
END;

IF EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_label_review_suggestion_status'
      AND object_id = OBJECT_ID('dbo.label_review')
)
BEGIN
    DROP INDEX IX_label_review_suggestion_status ON dbo.label_review;
END;

IF COL_LENGTH('dbo.label_review', 'suggested_unit_description') IS NOT NULL
BEGIN
    ALTER TABLE dbo.label_review DROP COLUMN
        product_kind,
        suggested_unit_description,
        suggestion_status,
        final_unit_description,
        suggested_by,
        suggested_at,
        decided_by,
        decided_at;
END;

IF COL_LENGTH('dbo.label_review', 'remarks') IS NULL
BEGIN
    ALTER TABLE dbo.label_review ADD remarks NVARCHAR(200) NULL;
END;
