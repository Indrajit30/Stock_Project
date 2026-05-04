import { Check, Clipboard, Download, FileSpreadsheet, FileText, Presentation, X } from 'lucide-react'
import { type ReactNode, useState } from 'react'
import { downloadFile } from '../lib/api'

interface ExportMenuProps {
  ticker: string
  compactIcon?: ReactNode
}

export default function ExportMenu({ ticker, compactIcon }: ExportMenuProps) {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)

  const notify = (message: string) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 2200)
  }

  const runDownload = async (kind: 'pdf' | 'excel' | 'pptx') => {
    const filenames = {
      pdf: `${ticker}_report.pdf`,
      excel: `${ticker}_research.xlsx`,
      pptx: `${ticker}_deck.pptx`,
    }
    setBusy(kind)
    try {
      await downloadFile(`/api/stock/${ticker}/export/${kind}`, filenames[kind])
      notify(`Downloaded ${filenames[kind]}`)
      setOpen(false)
    } catch {
      notify('Download failed - please try again')
    } finally {
      setBusy(null)
    }
  }

  const copySummary = async () => {
    setBusy('copy')
    try {
      await navigator.clipboard.writeText(
        `${ticker} - AI stock research summary\nOpen the loaded report for the full verdict, bull case, risk factors, and citations.\n\nSource: StockAI - Data from SEC EDGAR and DefeatBeta API`,
      )
      notify('Copied verdict summary')
      setOpen(false)
    } catch {
      notify('Copy failed - please try again')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div style={{ position: 'relative' }}>
      <button type="button" className="text-button" onClick={() => setOpen((current) => !current)}>
        {compactIcon}
        <span className="export-label">Export</span>
      </button>
      {open ? (
        <div className="recent-menu" style={{ right: 0, left: 'auto', width: 270 }}>
          <button type="button" className="recent-item" disabled={busy !== null} onMouseDown={() => runDownload('pdf')}>
            <span><FileText size={15} /> Download PDF Report</span>
            {busy === 'pdf' ? <Download className="spin" size={15} /> : null}
          </button>
          <button type="button" className="recent-item" disabled={busy !== null} onMouseDown={() => runDownload('excel')}>
            <span><FileSpreadsheet size={15} /> Download Excel Workbook</span>
            {busy === 'excel' ? <Download className="spin" size={15} /> : null}
          </button>
          <button type="button" className="recent-item" disabled={busy !== null} onMouseDown={() => runDownload('pptx')}>
            <span><Presentation size={15} /> Download PowerPoint</span>
            {busy === 'pptx' ? <Download className="spin" size={15} /> : null}
          </button>
          <button type="button" className="recent-item" disabled={busy !== null} onMouseDown={copySummary}>
            <span><Clipboard size={15} /> Copy Verdict Summary</span>
            {busy === 'copy' ? <Check size={15} /> : null}
          </button>
        </div>
      ) : null}
      {toast ? <div className="toast">{toast}</div> : null}
      {busy === 'error' ? <X aria-hidden="true" size={0} /> : null}
    </div>
  )
}
