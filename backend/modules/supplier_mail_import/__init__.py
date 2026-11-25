"""Supplier stock import from mail.

Each tenant configures ONE mailbox (IMAP). Each supplier on a store's
OrderSuppliers list can be switched to mail import; its sender address is
MailImportFrom, falling back to the supplier's existing Email column. A
background loop reads the tenant mailbox (read-only -- mails are never marked
read or moved), finds the newest mail from that supplier with an Excel
attachment, and imports it through the same path as the manual Supplier Excel
import (modules.supplier_stock_analysis.excel_import), using the supplier's
saved column mapping. Every mail handled is logged once in
dbo.supplier_mail_import_log, so a mail is never imported twice.
"""
