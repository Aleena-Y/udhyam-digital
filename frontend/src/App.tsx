import { FormEvent, useEffect, useMemo, useState } from 'react'
import { ArrowRight, Bot, CheckCircle2, FileCheck2, Loader2, MessageCircle, Mic, Package, RefreshCw, ShieldCheck, Sparkles, Upload, Volume2 } from 'lucide-react'
import './App.css'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

type Product = {
  product_id: string
  category: string
  product_name: string
  description: string
  unit: string
  price_min: number
  price_max: number
  setup_fee: number
  eligible?: boolean
  ineligibility_reasons?: string[]
}

type Business = {
  business_id: number
  name: string
  business_type?: string
  segment?: string
  city?: string
  city_tier: number
  state?: string
  employee_count: number
  num_sites: number
  has_gstin: boolean
}

type ChatMessage = { role: 'user' | 'assistant'; content: string }
type Quote = { quote_id: number; total_monthly_inr: number; total_setup_inr: number; contract_months: number; line_items: Array<{ product_id: string; quantity: number; monthly_price: number; setup_fee: number }> }
type Order = { order_id: number; status: string; typical_install_days: number; timeline: Array<{ status: string; timestamp: string; note: string }>; timeline_steps: Array<{ step: string; completed: boolean; current: boolean }> }
type DashboardSummary = { total_leads: number; activated: number; conversion_rate_pct: number; recovery_candidates: number; kyc_verified: number; funnel_source: string }
type RecoveryCandidate = { lead_id: string; business_name: string; city: string; recovery_score: number; drop_reason: string }
type DropReason = { reason: string; count: number; avg_recovery_score: number }

const translations: Record<string, Record<string, string>> = {
  English: {},
  Hindi: {
    'Get started': 'शुरू करें', Solutions: 'समाधान', 'How it works': 'यह कैसे काम करता है',
    'Ask advisor': 'सलाहकार से पूछें', 'Build my solution': 'अपना समाधान बनाएं',
    'Talk to an advisor': 'सलाहकार से बात करें', 'Your business': 'आपका व्यवसाय',
    'Start with the basics.': 'बुनियादी जानकारी से शुरू करें', 'Recommended solutions': 'अनुशंसित समाधान',
    'Choose what helps you grow.': 'अपने विकास के लिए समाधान चुनें', 'Secure onboarding': 'सुरक्षित ऑनबोर्डिंग',
    'Complete your KYC.': 'अपना KYC पूरा करें', 'Order tracking': 'ऑर्डर ट्रैकिंग',
    'Admin console': 'एडमिन कंसोल', 'Translate': 'अनुवाद', 'Upload documents': 'दस्तावेज़ अपलोड करें',
    'Select a plan to continue': 'जारी रखने के लिए योजना चुनें',
  },
  Tamil: {
    'Get started': 'தொடங்குங்கள்', Solutions: 'தீர்வுகள்', 'How it works': 'இது எப்படி செயல்படுகிறது',
    'Ask advisor': 'ஆலோசகரிடம் கேளுங்கள்', 'Build my solution': 'என் தீர்வை உருவாக்கு',
    'Talk to an advisor': 'ஆலோசகரிடம் பேசுங்கள்', 'Your business': 'உங்கள் வணிகம்',
    'Start with the basics.': 'அடிப்படை தகவல்களுடன் தொடங்குங்கள்', 'Recommended solutions': 'பரிந்துரைக்கப்பட்ட தீர்வுகள்',
    'Choose what helps you grow.': 'உங்கள் வளர்ச்சிக்கு உதவும் தீர்வைத் தேர்ந்தெடுக்கவும்', 'Secure onboarding': 'பாதுகாப்பான ஆன்போர்டிங்',
    'Complete your KYC.': 'உங்கள் KYC-ஐ முடிக்கவும்', 'Order tracking': 'ஆர்டர் கண்காணிப்பு',
    'Admin console': 'நிர்வாக கன்சோல்', 'Translate': 'மொழிபெயர்க்க', 'Upload documents': 'ஆவணங்களை பதிவேற்றவும்',
    'Select a plan to continue': 'தொடர ஒரு திட்டத்தைத் தேர்ந்தெடுக்கவும்',
  },
}

declare global {
  interface Window {
    webkitSpeechRecognition?: new () => SpeechRecognition
    SpeechRecognition?: new () => SpeechRecognition
  }
  interface SpeechRecognition extends EventTarget {
    lang: string
    interimResults: boolean
    onresult: ((event: SpeechRecognitionEvent) => void) | null
    onerror: (() => void) | null
    start: () => void
  }
  interface SpeechRecognitionEvent {
    results: { [index: number]: { [index: number]: { transcript: string } } }
  }
}

const money = (value: number) => `₹${value.toLocaleString('en-IN')}`

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { 'Content-Type': 'application/json', ...(options?.headers ?? {}) },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail?.message ?? body.detail ?? `Request failed (${response.status})`)
  }
  return response.json()
}

function App() {
  const [products, setProducts] = useState<Product[]>([])
  const [business, setBusiness] = useState<Business | null>(null)
  const [selected, setSelected] = useState<string[]>([])
  const [category, setCategory] = useState('All')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [chatOpen, setChatOpen] = useState(false)
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)
  const [chatSessionId, setChatSessionId] = useState<string>()
  const [language, setLanguage] = useState('English')
  const [isListening, setIsListening] = useState(false)
  const [quote, setQuote] = useState<Quote | null>(null)
  const [order, setOrder] = useState<Order | null>(null)
  const [kyc, setKyc] = useState<{ overall_status: string; checks: Record<string, string> } | null>(null)
  const [kycConsent, setKycConsent] = useState(false)
  const [gstin, setGstin] = useState('')
  const [udyam, setUdyam] = useState('')
  const [kycMessage, setKycMessage] = useState('')
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null)
  const [recoveryCandidates, setRecoveryCandidates] = useState<RecoveryCandidate[]>([])
  const [dropReasons, setDropReasons] = useState<DropReason[]>([])
  const [adminBusinessId, setAdminBusinessId] = useState('')
  const [adminKyc, setAdminKyc] = useState<{ overall_status: string; checks: Record<string, string>; failure_reasons?: string[] } | null>(null)
  const [adminReviewNote, setAdminReviewNote] = useState('')
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: 'Hi! I’m your Accel Business Advisor. Tell me about your business and I’ll help you find the right services.' },
  ])
  const [form, setForm] = useState({
    name: '', business_type: 'Retail', city: '', state: '', employee_count: 1, num_sites: 1,
    city_tier: 2, segment: 'micro', has_gstin: false,
  })

  const categories = useMemo(() => ['All', ...Array.from(new Set(products.map((p) => p.category)))], [products])
  const visibleProducts = products.filter((p) => category === 'All' || p.category === category)
  const eligibleCount = products.filter((p) => p.eligible).length
  const t = (text: string) => translations[language]?.[text] || text

  useEffect(() => {
    request<{ products: Product[] }>('/recommend/catalogue')
      .then((data) => setProducts(data.products))
      .catch((cause: Error) => setError(cause.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    request<DashboardSummary>('/dashboard/summary').then(setDashboard).catch(() => undefined)
    request<{ candidates: RecoveryCandidate[] }>('/leads/recovery-candidates?min_score=50&limit=8').then((data) => setRecoveryCandidates(data.candidates)).catch(() => undefined)
    request<{ reasons: DropReason[] }>('/dashboard/drop-reasons').then((data) => setDropReasons(data.reasons.slice(0, 6))).catch(() => undefined)
  }, [])

  const createBusiness = async (event: FormEvent) => {
    event.preventDefault()
    setSaving(true)
    setError('')
    try {
      const created = await request<Business>('/business/', { method: 'POST', body: JSON.stringify(form) })
      setBusiness(created)
      const recommendations = await request<{ products: Product[] }>('/recommend/', {
        method: 'POST',
        body: JSON.stringify({ ...form, gstin_active: form.has_gstin, bundle_product_ids: [] }),
      })
      setProducts(recommendations.products)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to save your profile.')
    } finally {
      setSaving(false)
    }
  }

  const toggleProduct = (id: string) => {
    setSelected((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  }

  const selectPlanFromChat = (content: string) => {
    const ids = Array.from(new Set(content.match(/P\d{2}/g) ?? [])).filter((id) => products.some((product) => product.product_id === id && product.eligible !== false))
    if (ids.length > 0) setSelected((current) => Array.from(new Set([...current, ...ids])))
    setChatOpen(false)
    document.getElementById('solutions')?.scrollIntoView({ behavior: 'smooth' })
  }

  const createQuote = async () => {
    if (!business || selected.length === 0) return
    setError('')
    try {
      const created = await request<Quote>('/quotes/', {
        method: 'POST',
        body: JSON.stringify({ business_id: business.business_id, city_tier: business.city_tier, line_items: selected.map((product_id) => ({ product_id, quantity: 1 })) }),
      })
      setQuote(created)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create quote.')
    }
  }

  const checkout = async () => {
    if (!quote) return
    try {
      const created = await request<Order>(`/quotes/${quote.quote_id}/checkout`, { method: 'POST' })
      const tracked = await request<Order>(`/orders/${created.order_id}`)
      setOrder(tracked)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to start checkout.')
    }
  }

  const startKyc = async () => {
    if (!business || !kycConsent) return
    try {
      await request('/kyc/consent', { method: 'POST', body: JSON.stringify({ business_id: business.business_id, purpose: 'KYC document collection', consent_text: 'I consent to collection and processing of KYC documents for onboarding.', consented: true }) })
      setKyc(await request(`/kyc/status/${business.business_id}`))
      setKycMessage('Consent recorded. You can now validate identifiers and upload documents.')
    } catch (cause) {
      setKycMessage(cause instanceof Error ? cause.message : 'Unable to record consent.')
    }
  }

  const validateIdentifier = async (type: 'gstin' | 'udyam') => {
    if (!business) return
    const value = type === 'gstin' ? gstin : udyam
    if (!value) return
    try {
      const result = await request<{ status: string; format_reason: string }>(`/kyc/validate-${type}`, { method: 'POST', body: JSON.stringify({ [type === 'gstin' ? 'gstin' : 'udyam_number']: value, business_id: business.business_id }) })
      setKycMessage(`${type.toUpperCase()}: ${result.status} — ${result.format_reason}`)
      setKyc(await request(`/kyc/status/${business.business_id}`))
    } catch (cause) {
      setKycMessage(cause instanceof Error ? cause.message : 'Validation failed.')
    }
  }

  const uploadDocument = async (docType: string, file?: File) => {
    if (!business || !file) return
    const formData = new FormData()
    formData.append('business_id', String(business.business_id))
    formData.append('doc_type', docType)
    formData.append('file', file)
    try {
      const response = await fetch(`${API_URL}/kyc/upload-document`, { method: 'POST', body: formData })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail ?? 'Upload failed.')
      setKycMessage(result.warning)
      setKyc(await request(`/kyc/status/${business.business_id}`))
    } catch (cause) {
      setKycMessage(cause instanceof Error ? cause.message : 'Upload failed.')
    }
  }

    const loadAdminKyc = async () => {
      if (!adminBusinessId) return
      try {
        setAdminKyc(await request(`/kyc/status/${adminBusinessId}`))
      } catch (cause) {
        setKycMessage(cause instanceof Error ? cause.message : 'Unable to load KYC review.')
      }
    }

    const reviewAdminKyc = async (decision: 'VERIFIED' | 'FAILED' | 'MANUAL_REVIEW') => {
      if (!adminBusinessId) return
      try {
        await request(`/kyc/review/${adminBusinessId}`, { method: 'POST', body: JSON.stringify({ decision, reviewer_note: adminReviewNote }) })
        await loadAdminKyc()
        setKycMessage(`Admin review saved as ${decision}.`)
      } catch (cause) {
        setKycMessage(cause instanceof Error ? cause.message : 'Unable to save admin review.')
      }
    }

  const startVoiceInput = () => {
    const Recognition = window.SpeechRecognition ?? window.webkitSpeechRecognition
    if (!Recognition) {
      setKycMessage('Voice input is not supported by this browser.')
      return
    }

    const recognition = new Recognition()
    recognition.lang = language === 'Hindi' ? 'hi-IN' : language === 'Tamil' ? 'ta-IN' : 'en-IN'
    recognition.interimResults = false
    recognition.onresult = (event) => {
      setChatInput(event.results[0][0].transcript)
      setIsListening(false)
    }
    recognition.onerror = () => setIsListening(false)
    setIsListening(true)
    recognition.start()
  }

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault()
    const content = chatInput.trim()
    if (!content || chatLoading) return
    setChatInput('')
    setChatMessages((current) => [...current, { role: 'user', content }])
    setChatLoading(true)
    try {
      const response = await fetch(`${API_URL}/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, business_id: business?.business_id, language, session_id: chatSessionId }),
      })
      if (!response.ok || !response.body) throw new Error('The AI advisor is unavailable.')
      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let answer = ''
      setChatMessages((current) => [...current, { role: 'assistant', content: '' }])
      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        for (const line of decoder.decode(value).split('\n')) {
          if (!line.startsWith('data: ')) continue
          const eventData = JSON.parse(line.slice(6)) as { content?: string; done?: boolean }
          if (eventData.done && !chatSessionId) setChatSessionId((eventData as { session_id?: string }).session_id)
          if (eventData.content) {
            answer += eventData.content
            setChatMessages((current) => current.map((message, index) =>
              index === current.length - 1 ? { ...message, content: answer } : message,
            ))
          }
        }
      }
    } catch (cause) {
      setChatMessages((current) => [...current, { role: 'assistant', content: cause instanceof Error ? cause.message : 'Please try again.' }])
    } finally {
      setChatLoading(false)
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><div className="brand-mark">A</div><div><strong>Accel</strong><span>Business Digital</span></div></div>
        <nav><a href="#profile">{t('Get started')}</a><a href="#solutions">{t('Solutions')}</a><a href="#how-it-works">{t('How it works')}</a><a href="#admin">{t('Admin console')}</a></nav>
        <div className="topbar-actions"><label className="translate-control"><Volume2 size={14} /><select aria-label="Translate page" value={language} onChange={(e) => setLanguage(e.target.value)}><option>English</option><option>Hindi</option><option>Tamil</option></select></label><button className="advisor-button" onClick={() => setChatOpen(true)}><MessageCircle size={17} /> {t('Ask advisor')}</button></div>
      </header>

      <main>
        <section className="hero-section">
          <div className="hero-copy">
            <p className="eyebrow"><Sparkles size={15} /> Built for ambitious businesses</p>
            <h1>Everything your business needs to <em>move forward.</em></h1>
            <p className="hero-text">Reliable connectivity, cloud tools and security from one trusted partner. Tell us about your business and get a tailored recommendation in minutes.</p>
            <div className="hero-actions"><a className="primary-button" href="#profile">{t('Build my solution')} <ArrowRight size={17} /></a><button className="text-button" onClick={() => setChatOpen(true)}>{t('Talk to an advisor')} <MessageCircle size={16} /></button></div>
            <div className="trust-row"><span><CheckCircle2 size={16} /> Personalised recommendations</span><span><ShieldCheck size={16} /> Secure by design</span></div>
          </div>
          <div className="hero-card"><div className="orb"><span>01</span></div><div className="hero-card-label">Your next<br /><strong>business advantage</strong></div></div>
        </section>

        <section className="stats-strip"><div><strong>25</strong><span>business solutions</span></div><div><strong>24/7</strong><span>advisor support</span></div><div><strong>1</strong><span>simple monthly bill</span></div></section>

        <section className="workspace-section" id="profile">
          <div className="section-heading"><div><p className="eyebrow">01 / {t('Your business')}</p><h2>{t('Start with the basics.')}</h2></div><p>We use this information to apply the catalogue’s eligibility rules and show relevant solutions.</p></div>
          <form className="profile-form" onSubmit={createBusiness}>
            <label>Business name<input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="e.g. Mehta & Sons" /></label>
            <label>Business type<select value={form.business_type} onChange={(e) => setForm({ ...form, business_type: e.target.value })}><option>Retail</option><option>Professional services</option><option>Manufacturing</option><option>Hospitality</option><option>Healthcare</option></select></label>
            <label>City<input required value={form.city} onChange={(e) => setForm({ ...form, city: e.target.value })} placeholder="e.g. Bengaluru" /></label>
            <label>State<input value={form.state} onChange={(e) => setForm({ ...form, state: e.target.value })} placeholder="e.g. Karnataka" /></label>
            <label>Employees<input type="number" min="1" value={form.employee_count} onChange={(e) => setForm({ ...form, employee_count: Number(e.target.value) })} /></label>
            <label>Business sites<input type="number" min="1" value={form.num_sites} onChange={(e) => setForm({ ...form, num_sites: Number(e.target.value) })} /></label>
            <label>City tier<select value={form.city_tier} onChange={(e) => setForm({ ...form, city_tier: Number(e.target.value) })}><option value="1">Tier 1</option><option value="2">Tier 2</option></select></label>
            <label>Business segment<select value={form.segment} onChange={(e) => setForm({ ...form, segment: e.target.value })}><option value="micro">Micro</option><option value="prof">Professional</option><option value="multi">Multi-site</option><option value="mfg">Manufacturing</option></select></label>
            <label className="checkbox-label"><input type="checkbox" checked={form.has_gstin} onChange={(e) => setForm({ ...form, has_gstin: e.target.checked })} /> I have an active GSTIN</label>
            <button className="primary-button form-submit" disabled={saving}>{saving ? <Loader2 className="spin" size={17} /> : <ArrowRight size={17} />} {saving ? 'Saving...' : 'Show my solutions'}</button>
          </form>
          {error && <p className="error-message">{error}</p>}
        </section>

        <section className="solutions-section" id="solutions">
          <div className="section-heading"><div><p className="eyebrow">02 / {t('Recommended solutions')}</p><h2>{t('Choose what helps you grow.')}</h2></div><span className="count-badge">{eligibleCount} eligible for your profile</span></div>
          <div className="filter-row">{categories.map((item) => <button key={item} className={category === item ? 'filter active' : 'filter'} onClick={() => setCategory(item)}>{item}</button>)}<button className="refresh-button" onClick={() => window.location.reload()}><RefreshCw size={15} /> Refresh data</button></div>
          {loading ? <div className="loading"><Loader2 className="spin" /> Loading catalogue...</div> : <div className="product-grid">{visibleProducts.map((product) => <article className={product.eligible === false ? 'product-card disabled' : 'product-card'} key={product.product_id}><div className="product-top"><span className="product-category">{product.category}</span><span className="product-id">{product.product_id}</span></div><h3>{product.product_name}</h3><p>{product.description}</p><div className="product-footer"><div><strong>{money(product.price_min)} – {money(product.price_max)}</strong><small>per month · {product.unit}</small></div><button disabled={product.eligible === false} className={selected.includes(product.product_id) ? 'select-button selected' : 'select-button'} onClick={() => toggleProduct(product.product_id)}>{selected.includes(product.product_id) ? <CheckCircle2 size={17} /> : <Package size={17} />} {selected.includes(product.product_id) ? 'Added' : product.eligible === false ? 'Not eligible' : 'Add'}</button></div>{product.eligible === false && <small className="reason">{product.ineligibility_reasons?.[0]}</small>}</article>)}</div>}
          {business && <div className="checkout-bar"><span>{selected.length} solution{selected.length === 1 ? '' : 's'} selected</span><button className="primary-button" disabled={!selected.length} onClick={createQuote}>Create editable quote <ArrowRight size={17} /></button></div>}
          {quote && <div className="quote-card"><div><p className="eyebrow">Your quote · #{quote.quote_id}</p><h3>{money(quote.total_monthly_inr)} / month <small>+ {money(quote.total_setup_inr)} setup</small></h3><p>{quote.contract_months}-month recommended contract. Prices are calculated by the backend catalogue rules.</p></div><button className="primary-button" onClick={checkout}>Accept & start simulated order <ArrowRight size={17} /></button></div>}
        </section>

        {business && selected.length > 0 && <section className="onboarding-section">
          <div className="section-heading"><div><p className="eyebrow">03 / {t('Secure onboarding')}</p><h2>{t('Complete your KYC.')}</h2></div><p>{t('Select a plan to continue')}. Upload only the documents needed for onboarding. OCR assists comparison; it never proves authenticity.</p></div>
          <div className="consent-box"><label className="checkbox-label"><input type="checkbox" checked={kycConsent} onChange={(e) => setKycConsent(e.target.checked)} /> I consent to KYC document collection for onboarding.</label><button className="select-button" onClick={startKyc} disabled={!kycConsent}>Save consent</button></div>
          <div className="kyc-grid"><div className="kyc-identifiers"><label>GSTIN<input value={gstin} onChange={(e) => setGstin(e.target.value.toUpperCase())} placeholder="15-character GSTIN" /></label><button className="select-button" onClick={() => validateIdentifier('gstin')}>Validate GSTIN</button><label>Udyam number<input value={udyam} onChange={(e) => setUdyam(e.target.value.toUpperCase())} placeholder="UDYAM-XX-00-NNNNNNN" /></label><button className="select-button" onClick={() => validateIdentifier('udyam')}>Validate Udyam</button></div><div className="kyc-documents">{['gst_certificate', 'udyam_certificate', 'signatory_id', 'address_proof'].map((doc) => <label className="upload-field" key={doc}><span><Upload size={15} /> {doc.replaceAll('_', ' ')}</span><input type="file" accept=".png,.jpg,.jpeg,.pdf" onChange={(e) => uploadDocument(doc, e.target.files?.[0])} disabled={!kycConsent} /></label>)}</div></div>
          {kyc && <div className="kyc-status"><FileCheck2 size={17} /> Overall status: <strong>{kyc.overall_status}</strong>{Object.entries(kyc.checks).map(([key, status]) => <span key={key}>{key.replaceAll('_', ' ')}: {status}</span>)}</div>}
          {kycMessage && <p className="notice">{kycMessage}</p>}
        </section>}

        {order && <section className="order-section"><div className="section-heading"><div><p className="eyebrow">04 / Order tracking</p><h2>Your order is moving.</h2></div><span className="count-badge">Simulated demo status</span></div><div className="timeline">{order.timeline_steps.map((step) => <div className={step.completed ? 'timeline-step completed' : 'timeline-step'} key={step.step}><span>{step.completed ? <CheckCircle2 size={18} /> : <span className="timeline-dot" />}</span><strong>{step.step}</strong></div>)}</div><p className="notice">Typical installation: {order.typical_install_days} days. Status updates are simulated and are not connected to a telecom network.</p></section>}

        {dashboard && <section className="dashboard-section" id="admin"><div className="section-heading"><div><p className="eyebrow">Operations / Admin & partner view</p><h2>Make every lead count.</h2></div><p>Dataset-derived performance indicators for admins and channel partners.</p></div><div className="metric-grid"><div><strong>{dashboard.total_leads.toLocaleString('en-IN')}</strong><span>dataset leads</span></div><div><strong>{dashboard.activated.toLocaleString('en-IN')}</strong><span>activated</span></div><div><strong>{dashboard.conversion_rate_pct}%</strong><span>conversion rate</span></div><div><strong>{dashboard.recovery_candidates.toLocaleString('en-IN')}</strong><span>high-priority recoveries</span></div><div><strong>{dashboard.kyc_verified.toLocaleString('en-IN')}</strong><span>live KYC verified</span></div></div><a className="primary-button admin-main-link" href="/admin">Open full admin analytics <ArrowRight size={17} /></a></section>}

        <section className="how-section" id="how-it-works"><p className="eyebrow">03 / A simpler way forward</p><h2>From “what do I need?”<br /><em>to “let’s get started.”</em></h2><div className="steps"><div><span>01</span><h3>Tell us your goals</h3><p>Share a few details about your business and what you want to improve.</p></div><div><span>02</span><h3>Get a clear recommendation</h3><p>Our rules-based catalogue finds solutions that fit your business profile.</p></div><div><span>03</span><h3>Speak to a real advisor</h3><p>Refine your bundle with help from our AI advisor, powered by Ollama.</p></div></div></section>
      </main>
      <footer><div className="brand"><div className="brand-mark">A</div><div><strong>Accel</strong><span>Business Digital</span></div></div><span>© 2026 Accel Business. Demo platform.</span></footer>

      {chatOpen && <div className="chat-overlay" onClick={() => setChatOpen(false)}><aside className="chat-panel" onClick={(e) => e.stopPropagation()}><div className="chat-header"><div><Bot size={19} /><strong>Business Advisor</strong></div><button onClick={() => setChatOpen(false)}>×</button></div><div className="chat-options"><select value={language} onChange={(e) => setLanguage(e.target.value)}><option>English</option><option>Hindi</option><option>Tamil</option></select><span><Volume2 size={14} /> {chatSessionId ? 'Context retained' : 'New conversation'}</span></div><div className="chat-body">{chatMessages.map((message, index) => <div className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>{message.content || <Loader2 className="spin" size={17} />}{message.role === 'assistant' && message.content.match(/P\d{2}/) && <button className="chat-plan-button" onClick={() => selectPlanFromChat(message.content)}>Select plan from this advice</button>}</div>)}</div><form className="chat-form" onSubmit={sendMessage}><button type="button" className={isListening ? 'voice-button listening' : 'voice-button'} onClick={startVoiceInput}><Mic size={18} /></button><input value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="Ask about your business..." /><button disabled={chatLoading}><ArrowRight size={18} /></button></form></aside></div>}
    </div>
  )
}

export default App
