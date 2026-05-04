import { Download, FileText } from 'lucide-react'
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

  const runDownload = async () => {
    const filename = `${ticker}_report.pdf`
    setBusy('pdf')
    try {
      await downloadFile(`/api/stock/${ticker}/export/pdf`, filename)
      notify(`Downloaded ${filename}`)
      setOpen(false)
    } catch {
      notify('Download failed - please try again')
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
          <button type="button" className="recent-item" disabled={busy !== null} onClick={runDownload}>
            <span><FileText size={15} /> Download PDF Report</span>
            {busy === 'pdf' ? <Download className="spin" size={15} /> : null}
          </button>
        </div>
      ) : null}
      {toast ? <div className="toast">{toast}</div> : null}
    </div>
  )
}
