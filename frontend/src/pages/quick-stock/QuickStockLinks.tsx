import { useState } from 'react'
import { QUICK_STOCK_URLS } from './quickStockUrls'

function CopyRow({ label, url }: { label: string; url: string }) {
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // clipboard blocked — the URL is still visible to copy manually
    }
  }

  return (
    <div className="qs-link-row">
      <span className="qs-link-row__label">{label}</span>
      <code className="qs-link-row__url">{url}</code>
      <button type="button" className="qs-link-row__copy" onClick={copy}>
        {copied ? 'Copied' : 'Copy'}
      </button>
    </div>
  )
}

/** Fixed HO LAN + public links, shown so this page can be opened from any
 *  other device without hunting for the URL. */
export function QuickStockLinks() {
  return (
    <div className="qs-links">
      <div className="qs-links__title">Open on another device</div>
      <CopyRow label="LAN" url={QUICK_STOCK_URLS.lan} />
      <CopyRow label="Internet" url={QUICK_STOCK_URLS.public} />
    </div>
  )
}
