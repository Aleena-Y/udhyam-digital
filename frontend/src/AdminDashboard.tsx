import { useEffect, useState } from 'react'
import { BarChart3, CheckCircle2, ClipboardCheck, Loader2, ShieldAlert, Users, XCircle } from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type Summary = {
  total_leads: number
  activated: number
  conversion_rate_pct: number
  recovery_candidates: number
  kyc_verified: number
  top_segments: Array<{ segment: string; total_leads: number; activated: number; conversion_pct: number }>
}
type Funnel = { funnel: Array<{ stage: string; count: number }> }
type DropReason = { reason: string; count: number; avg_recovery_score: number }
type Candidate = { lead_id: string; business_name: string; city: string; recovery_score: number; drop_reason: string }
type KycStatus = { overall_status: string; checks: Record<string, string>; failure_reasons?: string[] }

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`)
  if (!response.ok) throw new Error(`Request failed (${response.status})`)
  return response.json()
}

async function send(path: string, body: object) {
  const response = await fetch(`${API_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const data = await response.json().catch(() => ({}))
    throw new Error(data.detail ?? `Request failed (${response.status})`)
  }
  return response.json()
}

const colors = ['#164b32', '#e8794e', '#93b85d', '#c4a24e', '#7a8f83', '#aa6d52']

export default function AdminDashboard() {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [funnel, setFunnel] = useState<Funnel | null>(null)
  const [reasons, setReasons] = useState<DropReason[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [businessId, setBusinessId] = useState('')
  const [kyc, setKyc] = useState<KycStatus | null>(null)
  const [note, setNote] = useState('')
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(true)

  const loadData = async () => {
    setLoading(true)
    try {
      const [nextSummary, nextFunnel, nextReasons, nextCandidates] = await Promise.all([
        get<Summary>('/dashboard/summary'),
        get<Funnel>('/dashboard/funnel'),
        get<{ reasons: DropReason[] }>('/dashboard/drop-reasons'),
        get<{ candidates: Candidate[] }>('/leads/recovery-candidates?min_score=50&limit=8'),
      ])
      setSummary(nextSummary)
      setFunnel(nextFunnel)
      setReasons(nextReasons.reasons.slice(0, 8))
      setCandidates(nextCandidates.candidates)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to load dashboard data.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadData() }, [])

  const loadKyc = async () => {
    if (!businessId) return
    try {
      setKyc(await get<KycStatus>(`/kyc/status/${businessId}`))
      setMessage('')
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to load KYC.')
    }
  }

  const review = async (decision: 'VERIFIED' | 'FAILED' | 'MANUAL_REVIEW') => {
    try {
      await send(`/kyc/review/${businessId}`, { decision, reviewer_note: note })
      await loadKyc()
      setMessage(`KYC decision saved: ${decision}`)
    } catch (error) {
      setMessage(error instanceof Error ? error.message : 'Unable to save review.')
    }
  }

  if (loading) return <div className="admin-loading"><Loader2 className="spin" /> Loading admin analytics...</div>

  return (
    <div className="admin-page">
      <header className="admin-topbar">
        <a className="admin-brand" href="/"><span>A</span><strong>Accel Business <small>Admin Console</small></strong></a>
        <div className="admin-top-actions"><span>Dataset + live onboarding data</span><a href="/">Customer view</a></div>
      </header>
      <main className="admin-main">
        <div className="admin-title-row"><div><p className="eyebrow">Operations / Admin</p><h1>Know what needs attention.</h1><p>Review acquisition performance, recovery opportunities, and KYC decisions from one place.</p></div><button className="admin-refresh" onClick={loadData}>Refresh data</button></div>
        {message && <div className="admin-message">{message}</div>}
        <section className="admin-metrics">
          <div><Users size={18} /><strong>{summary?.total_leads.toLocaleString('en-IN')}</strong><span>Total leads</span><small>Dataset-derived</small></div>
          <div><CheckCircle2 size={18} /><strong>{summary?.activated.toLocaleString('en-IN')}</strong><span>Activated</span><small>Dataset-derived</small></div>
          <div><BarChart3 size={18} /><strong>{summary?.conversion_rate_pct}%</strong><span>Conversion rate</span><small>Dataset-derived</small></div>
          <div><ShieldAlert size={18} /><strong>{summary?.recovery_candidates}</strong><span>Recovery candidates</span><small>Rule-scored</small></div>
          <div><ClipboardCheck size={18} /><strong>{summary?.kyc_verified}</strong><span>Verified KYC</span><small>Live records</small></div>
        </section>
        <section className="chart-grid">
          <div className="chart-card"><div className="chart-heading"><h2>Funnel performance</h2><span>From smb_leads.csv</span></div><ResponsiveContainer width="100%" height={280}><BarChart data={funnel?.funnel}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e1e7e1" /><XAxis dataKey="stage" tick={{ fontSize: 10 }} /><YAxis tick={{ fontSize: 10 }} /><Tooltip /><Bar dataKey="count" fill="#164b32" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div>
          <div className="chart-card"><div className="chart-heading"><h2>Drop-off reasons</h2><span>Higher score = recoverable</span></div><ResponsiveContainer width="100%" height={280}><BarChart data={reasons} layout="vertical" margin={{ left: 20, right: 20 }}><CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e1e7e1" /><XAxis type="number" tick={{ fontSize: 10 }} /><YAxis dataKey="reason" type="category" width={125} tick={{ fontSize: 9 }} /><Tooltip /><Bar dataKey="count" fill="#e8794e" radius={[0, 3, 3, 0]} /></BarChart></ResponsiveContainer></div>
        </section>
        <section className="admin-lower-grid">
          <div className="admin-table-card"><div className="chart-heading"><h2>Recovery queue</h2><span>What to assign next</span></div>{candidates.map((candidate) => <div className="admin-table-row" key={candidate.lead_id}><div><strong>{candidate.business_name}</strong><small>{candidate.lead_id} · {candidate.city}</small><small>{candidate.drop_reason}</small></div><b>{candidate.recovery_score}</b><button className="admin-small-button">Review</button></div>)}{candidates.length === 0 && <p className="empty-admin">No candidates match the current threshold.</p>}</div>
          <div className="admin-table-card"><div className="chart-heading"><h2>KYC review desk</h2><span>Approve only after evidence review</span></div><div className="kyc-admin-search"><input type="number" min="1" value={businessId} onChange={(event) => setBusinessId(event.target.value)} placeholder="Business ID" /><button className="admin-small-button" onClick={loadKyc}>Load</button></div>{kyc ? <><div className="kyc-admin-status"><strong>{kyc.overall_status}</strong>{Object.entries(kyc.checks).map(([key, status]) => <span key={key}>{key.replaceAll('_', ' ')}: {status}</span>)}</div><input className="review-note" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Reviewer note" /><div className="review-buttons"><button onClick={() => review('VERIFIED')}><CheckCircle2 size={15} /> Approve</button><button onClick={() => review('MANUAL_REVIEW')}><ClipboardCheck size={15} /> Manual review</button><button onClick={() => review('FAILED')}><XCircle size={15} /> Reject</button></div></> : <p className="empty-admin">Enter a business ID to inspect KYC checks, OCR results, and registry evidence.</p>}</div>
        </section>
        <section className="admin-note"><strong>Governance note</strong><span>Metrics marked dataset-derived come from the supplied CSV files. KYC approval is an explicit admin decision; OCR is supporting evidence only and cannot establish document authenticity.</span></section>
      </main>
    </div>
  )
}
