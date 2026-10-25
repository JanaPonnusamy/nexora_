/* Procurement — Internal Supplier Stock Distribution: per-store WhatsApp sender.
   Target database: NEXORA_PLATFORM (SQL Server).

   distribution_config.whatsapp_sender picks WHO sends a store's stock file:
     'HO'    — the HO backend's own WhatsApp session (the original behaviour).
     'STORE' — the store's own WhatsApp, linked inside that store's Electron
               Stock Client. HO only queues the run item
               (whatsapp_status = 'store_pending'); the store app claims it
               (store_sending), sends it and reports sent/failed back.

   Idempotent.
*/

IF COL_LENGTH('procurement.distribution_config', 'whatsapp_sender') IS NULL
    ALTER TABLE procurement.distribution_config
        ADD whatsapp_sender VARCHAR(10) NOT NULL
            CONSTRAINT DF_distribution_config_whatsapp_sender DEFAULT 'HO';
GO

IF COL_LENGTH('procurement.distribution_run_item', 'whatsapp_claimed_at') IS NULL
    ALTER TABLE procurement.distribution_run_item ADD whatsapp_claimed_at DATETIME NULL;
GO
