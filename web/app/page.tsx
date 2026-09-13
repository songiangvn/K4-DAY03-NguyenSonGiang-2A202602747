'use client'

import { useEffect, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowRight, CalendarDays, Check, ChevronDown, Clock3,
  Database, FileText, History, Loader2, MapPin, MessageCircle, Plus, RotateCcw,
  Search, Send, ShieldCheck, Sparkles, Stethoscope, UserRound, X,
} from 'lucide-react'

/* ========================================================================
   KIỂU DỮ LIỆU — khớp với phản hồi của src/api_server.py
   ======================================================================== */

type TraceStep = {
  step: number
  kind: 'tool' | 'final'
  thought: string
  tool_name?: string
  arguments?: Record<string, unknown>
  status?: string
  summary: string
  llm_latency_ms?: number
  mcp_latency_ms?: number
}

type RankedDoctor = {
  rank: number
  doctor_id: string
  full_name: string
  title: string
  specialty: string
  experience_years: number
  room: string
  consultation_fee_vnd: number
  match_score: number | null
  is_returning_doctor: boolean
  ranking_reasons: string[]
  earliest_slot?: { date: string; time: string }
  available_slots: Record<string, string[]>
}

type QuickNote = { headline: string; bullets: string[]; alerts: string[] }

type Booking = {
  booking_id: string
  patient_id: string
  patient_name: string
  doctor_name: string
  specialty: string
  room: string
  date: string
  time_slot: string
  consultation_fee_vnd: number
  doctor_quick_note: QuickNote
}

type ChatReply = {
  answer: string
  steps: TraceStep[]
  patient: { full_name: string; total_visits: number; quick_note: QuickNote } | null
  ranked: { specialty: string; recommendation: string; doctors: RankedDoctor[] } | null
  booking: Booking | null
  tool_calls: number
  elapsed_ms: number
  model: string
}

type Turn = { question: string; reply: ChatReply | null; error?: string }

type Patient = {
  patient_id: string
  full_name: string
  phone: string
  chronic_conditions: string[]
  allergies: string[]
  total_visits: number
}

type Health = { provider: string; model: string; live_llm: boolean; mcp_server: string; tools: { name: string }[] }

/* ========================================================================
   TIỆN ÍCH
   ======================================================================== */

const money = (v: number) => new Intl.NumberFormat('vi-VN').format(v) + ' ₫'

const prettyDate = (iso: string) => {
  const d = new Date(iso + 'T00:00:00')
  if (Number.isNaN(d.getTime())) return iso
  const days = ['Chủ nhật', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7']
  return `${days[d.getDay()]}, ${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')}/${d.getFullYear()}`
}

const initials = (name: string) =>
  name.replace(/^(PGS\.TS|GS\.TS|TS\.BS|ThS\.BS|BS\.CKI{1,2}|BS)\.?\s*/i, '')
    .split(/\s+/).filter(Boolean).slice(-2).map(w => w[0]).join('').toUpperCase()

/**
 * Rút gọn câu trả lời khi các thẻ bác sĩ bên dưới đã trình bày cùng nội dung.
 * Tránh việc người dùng phải đọc hai lần cùng một danh sách lý do xếp hạng.
 */
const trimAnswer = (answer: string, hasCards: boolean) => {
  if (!hasCards) return answer
  const cut = answer.search(/\n\s*#*\s*(Lý do đề xuất|Các lựa chọn khác|Lý do:|Đề xuất bác sĩ)/i)
  return (cut > 0 ? answer.slice(0, cut) : answer).trim()
}

/**
 * Hiển thị câu trả lời của LLM dưới dạng văn bản có định dạng nhẹ.
 * Các model như gpt-4o-mini thường trả về Markdown (`###`, `**đậm**`, `- gạch đầu dòng`),
 * nếu in thô sẽ lộ ký hiệu nên cần chuyển thành phần tử React tương ứng.
 */
function RichText({ text }: { text: string }) {
  if (!text) return null

  const renderInline = (line: string) =>
    line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
      part.startsWith('**') && part.endsWith('**')
        ? <b key={i}>{part.slice(2, -2)}</b>
        : <span key={i}>{part}</span>
    )

  const blocks: React.ReactNode[] = []
  let bullets: string[] = []

  const flushBullets = () => {
    if (!bullets.length) return
    blocks.push(
      <ul className="answer-list" key={`ul-${blocks.length}`}>
        {bullets.map((b, i) => <li key={i}>{renderInline(b)}</li>)}
      </ul>
    )
    bullets = []
  }

  text.split('\n').forEach((raw, idx) => {
    const line = raw.trimEnd()

    if (/^\s*[-*]\s+/.test(line) || /^\s*\d+\.\s+/.test(line)) {
      bullets.push(line.replace(/^\s*(?:[-*]|\d+\.)\s+/, ''))
      return
    }

    flushBullets()

    if (!line.trim()) return

    if (/^#{1,6}\s+/.test(line)) {
      blocks.push(
        <p className="answer-heading" key={`h-${idx}`}>
          {renderInline(line.replace(/^#{1,6}\s+/, ''))}
        </p>
      )
      return
    }

    blocks.push(<p className="answer-para" key={`p-${idx}`}>{renderInline(line)}</p>)
  })

  flushBullets()
  return <>{blocks}</>
}

/* ========================================================================
   THÀNH PHẦN GIAO DIỆN
   ======================================================================== */

function Logo() {
  return (
    <div className="logo" aria-label="Online Vinmec">
      <div className="logo-mark">✦</div>
      <div><strong>ONLINE.</strong><span>VINMEC</span></div>
    </div>
  )
}

/** Dấu vết ReAct: hiển thị từng bước Thought → Action → Observation */
function ToolTrace({ steps, running }: { steps: TraceStep[]; running: boolean }) {
  if (!steps.length && !running) return null
  return (
    <div className="tool-trace">
      <div className="trace-label">
        {running ? <Loader2 className="spin" aria-hidden="true" /> : <Activity aria-hidden="true" />}
        {running ? 'Agent đang xử lý yêu cầu' : `Agent đã thực hiện ${steps.filter(s => s.kind === 'tool').length} lượt gọi công cụ`}
      </div>
      {steps.map(s => {
        const failed = s.status && !['SUCCESS'].includes(s.status)
        return (
          <div className="trace-step" key={`${s.step}-${s.tool_name ?? 'final'}`}>
            <div className={`trace-dot ${s.kind === 'final' ? 'complete' : failed ? 'failed' : 'complete'}`}>
              {failed ? <AlertTriangle aria-hidden="true" /> : <Check aria-hidden="true" />}
            </div>
            <div>
              <strong>{s.tool_name ?? 'final_answer'}</strong>
              {typeof s.llm_latency_ms === 'number' && (
                <span className="trace-latency">{Math.round(s.llm_latency_ms)}ms</span>
              )}
              <p>{s.summary}</p>
              {s.arguments && Object.keys(s.arguments).length > 0 && (
                <p className="trace-args">{JSON.stringify(s.arguments)}</p>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** Thẻ bác sĩ kèm điểm phù hợp và lý do xếp hạng */
function DoctorCard({
  doctor, isTop, onSelect, selectedSlot,
}: {
  doctor: RankedDoctor
  isTop: boolean
  onSelect: (d: RankedDoctor, date: string, time: string) => void
  selectedSlot: string
}) {
  const slots: { date: string; time: string }[] = []
  Object.entries(doctor.available_slots || {}).forEach(([date, times]) => {
    ;(times || []).forEach(time => slots.push({ date, time }))
  })
  const shown = slots.slice(0, 4)

  return (
    <article className={`doctor-result ${isTop ? 'top-pick' : ''}`}>
      <div className="doctor-result-top">
        <span className="avatar large">{initials(doctor.full_name)}</span>
        <div className="doctor-identity">
          <h3>
            {doctor.full_name}
            {doctor.is_returning_doctor && (
              <span className="returning-tag"><History aria-hidden="true" /> Bác sĩ quen</span>
            )}
          </h3>
          <p>{doctor.specialty} · {doctor.experience_years} năm kinh nghiệm · {doctor.room} · {money(doctor.consultation_fee_vnd)}</p>
        </div>
        {doctor.match_score !== null && (
          <span className="match-score"><Sparkles aria-hidden="true" /> {doctor.match_score}/100</span>
        )}
      </div>

      {doctor.ranking_reasons?.length > 0 && (
        <div className="reason">
          <ShieldCheck aria-hidden="true" />
          <span>
            <b>Vì sao được gợi ý:</b>
            <ul>{doctor.ranking_reasons.slice(0, 3).map((r, i) => <li key={i}>{r}</li>)}</ul>
          </span>
        </div>
      )}

      <div className="doctor-result-bottom">
        <div className="mini-slots">
          {shown.map(s => {
            const key = `${doctor.doctor_id}|${s.date}|${s.time}`
            return (
              <button
                type="button"
                key={key}
                className={selectedSlot === key ? 'active' : ''}
                onClick={() => onSelect(doctor, s.date, s.time)}
              >
                <Clock3 aria-hidden="true" /> {s.time} · {s.date.slice(8)}/{s.date.slice(5, 7)}
              </button>
            )
          })}
          {!shown.length && <span className="no-slot-hint">Không còn khung giờ trống</span>}
        </div>
        {shown.length > 0 && (
          <button className="choose-button" type="button" onClick={() => onSelect(doctor, shown[0].date, shown[0].time)}>
            Chọn bác sĩ <ArrowRight aria-hidden="true" />
          </button>
        )}
      </div>
    </article>
  )
}

/** Quick Note — bản tóm tắt bệnh sử gửi kèm cho bác sĩ */
function QuickNoteBlock({ note }: { note: QuickNote }) {
  if (!note) return null
  return (
    <div className="quick-note">
      <FileText aria-hidden="true" />
      <div>
        <p><b>Quick Note gửi bác sĩ:</b> {note.headline}</p>
        {note.bullets?.length > 0 && <ul>{note.bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>}
        {note.alerts?.map((a, i) => <span className="alert-line" key={i}>{a}</span>)}
      </div>
    </div>
  )
}

/* ========================================================================
   TRANG CHÍNH
   ======================================================================== */

export default function Page() {
  const [prompt, setPrompt] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const [loading, setLoading] = useState(false)
  const [health, setHealth] = useState<Health | null>(null)
  const [patients, setPatients] = useState<Patient[]>([])
  const [activePatient, setActivePatient] = useState('')
  const [selected, setSelected] = useState<{ doctor: RankedDoctor; date: string; time: string } | null>(null)
  const [success, setSuccess] = useState<Booking | null>(null)
  const [showTrace, setShowTrace] = useState(false)
  const [trace, setTrace] = useState<unknown[]>([])

  // Mã phiên sinh ở phía client sau khi hydrate xong — dùng Date.now() ngay trong
  // useState sẽ khiến HTML máy chủ và máy khách khác nhau, gây lỗi hydration.
  const sessionRef = useRef('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const started = turns.length > 0

  useEffect(() => {
    sessionRef.current = `WEB-${Date.now()}`
    fetch('/api/health').then(r => r.json()).then(setHealth).catch(() => setHealth(null))
    fetch('/api/patients').then(r => r.json()).then(d => setPatients(d.patients ?? [])).catch(() => {})
  }, [])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns, loading])

  const patient = patients.find(p => p.patient_id === activePatient)

  /** Gửi câu hỏi tới Agent; tự gắn mã bệnh nhân nếu người dùng đã chọn hồ sơ */
  async function send(text: string) {
    const question = text.trim()
    if (!question || loading) return

    const enriched =
      activePatient && !/BN\d{6,}/i.test(question)
        ? `Tôi là bệnh nhân ${activePatient}. ${question}`
        : question

    setPrompt('')
    setSelected(null)
    setTurns(t => [...t, { question, reply: null }])
    setLoading(true)

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: enriched, session_id: sessionRef.current || 'WEB' }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Agent không phản hồi')
      setTurns(t => t.map((turn, i) => (i === t.length - 1 ? { ...turn, reply: data } : turn)))
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      setTurns(t => t.map((turn, i) => (i === t.length - 1 ? { ...turn, error: msg } : turn)))
    } finally {
      setLoading(false)
    }
  }

  /** Xác nhận đặt lịch với bác sĩ & khung giờ người dùng vừa chọn trên thẻ */
  function confirmBooking() {
    if (!selected) return
    const { doctor, date, time } = selected
    send(
      `Đặt lịch khám giúp tôi với bác sĩ mã ${doctor.doctor_id} vào ${time} ngày ${date}.`
    )
  }

  function reset() {
    setTurns([])
    setPrompt('')
    setSelected(null)
    setSuccess(null)
  }

  async function openTrace() {
    try {
      const d = await fetch('/api/trace').then(r => r.json())
      setTrace(d.trace ?? [])
    } catch { setTrace([]) }
    setShowTrace(true)
  }

  // Phiếu hẹn mới nhất — dùng để bật hộp thoại thành công
  useEffect(() => {
    const last = turns[turns.length - 1]
    if (last?.reply?.booking && last.reply.booking.booking_id !== success?.booking_id) {
      setSuccess(last.reply.booking)
      setSelected(null)
    }
  }, [turns]) // eslint-disable-line react-hooks/exhaustive-deps

  const toolCount = turns.reduce((n, t) => n + (t.reply?.tool_calls ?? 0), 0)

  return (
    <main className="site-shell">
      {/* ------------------------------ TOPBAR ------------------------------ */}
      <header className="topbar">
        <div className="topbar-inner">
          <Logo />
          <div className="searchbar">
            <button className="location-button" type="button">
              <MapPin aria-hidden="true" /> Vinmec Times City <ChevronDown aria-hidden="true" />
            </button>
            <span className="search-divider" />
            <input aria-label="Tìm kiếm dịch vụ" placeholder="Tìm kiếm dịch vụ, chuyên khoa, bác sĩ" />
            <Search aria-hidden="true" className="search-icon" />
          </div>
          <nav className="account-nav" aria-label="Tài khoản">
            <button type="button" className="link-button">Đăng ký</button>
            <button type="button" className="login-button">Đăng nhập</button>
            <button type="button" className="primary-button small">Đặt lịch khám</button>
          </nav>
        </div>
        <div className="subnav">
          <button type="button">Chuyên khoa</button>
          <button type="button">Bác sĩ</button>
          <button type="button">Gói khám</button>
        </div>
      </header>

      <section className="agent-wrap">
        <div className="agent-layout">
          {/* ----------------------------- SIDEBAR ---------------------------- */}
          <aside className="agent-sidebar">
            <div className="agent-brand">
              <div className="agent-orb"><Sparkles aria-hidden="true" /></div>
              <div>
                <h1>Trợ lý sức khỏe<br />Vinmec</h1>
                <span className={`online-status ${health?.live_llm ? '' : 'offline'}`}>
                  <i />{health ? (health.live_llm ? 'Đang trực tuyến' : 'Chế độ offline') : 'Đang kết nối…'}
                </span>
              </div>
            </div>

            <div className="connected-badge">
              <Database aria-hidden="true" />
              <span>
                <b>MCP connected</b>
                <small>{health?.tools?.length ?? 4} công cụ y tế</small>
              </span>
              <Check aria-hidden="true" />
            </div>

            {/* Chọn hồ sơ bệnh nhân để demo bộ nhớ dài hạn */}
            <div className="sidebar-section patient-picker">
              <span className="eyebrow">HỒ SƠ BỆNH NHÂN</span>
              <select
                value={activePatient}
                onChange={e => setActivePatient(e.target.value)}
                aria-label="Chọn hồ sơ bệnh nhân"
              >
                <option value="">— Khách vãng lai —</option>
                {patients.map(p => (
                  <option key={p.patient_id} value={p.patient_id}>
                    {p.full_name} ({p.patient_id})
                  </option>
                ))}
              </select>
              {patient && (
                <div className="patient-chips">
                  <span>{patient.total_visits} lượt khám</span>
                  {patient.chronic_conditions.map(c => <span key={c}>{c}</span>)}
                  {patient.allergies.map(a => <span className="alert" key={a}>Dị ứng {a}</span>)}
                </div>
              )}
            </div>

            <div className="sidebar-section hide-mobile">
              <span className="eyebrow">CÔNG CỤ MCP</span>
              <div className="tool-list">
                {(health?.tools ?? []).map(t => (
                  <div key={t.name}><i />{t.name}</div>
                ))}
              </div>
            </div>

            <div className="sidebar-section safety hide-mobile">
              <ShieldCheck aria-hidden="true" />
              <p>Trợ lý chỉ hỗ trợ tra cứu và đặt lịch, không chẩn đoán bệnh hay kê đơn thuốc.</p>
            </div>

            <button type="button" className="new-chat" onClick={reset}>
              <Plus aria-hidden="true" /> Cuộc hội thoại mới
            </button>
          </aside>

          {/* --------------------------- KHUNG CHAT --------------------------- */}
          <section className="chat-panel">
            <div className="chat-header">
              <div>
                <span className="eyebrow">VINMEC CARE AGENT</span>
                <h2>Đặt lịch khám cùng trợ lý AI</h2>
              </div>
              <div className="header-actions">
                {health && (
                  <span className={`model-tag ${health.live_llm ? '' : 'mock'}`}>
                    {health.live_llm ? health.model : 'MOCK OFFLINE'}
                  </span>
                )}
                <button type="button" className="reset-button" onClick={openTrace}>
                  <Activity aria-hidden="true" /> Trace log
                </button>
                <button type="button" className="reset-button" onClick={reset}>
                  <RotateCcw aria-hidden="true" /> Làm mới
                </button>
              </div>
            </div>

            <div className="chat-scroll" ref={scrollRef}>
              <div className="welcome-message">
                <div className="message-avatar"><Sparkles aria-hidden="true" /></div>
                <div>
                  <span className="message-label">Vinmec Agent <small>vừa xong</small></span>
                  <p>
                    Xin chào! Tôi có thể giúp bạn tìm bác sĩ phù hợp và đặt lịch khám tại Vinmec.
                    Nếu bạn chọn hồ sơ bệnh nhân ở thanh bên, tôi sẽ dựa vào tiền sử khám để gợi ý
                    bác sĩ đã từng theo dõi bạn.
                  </p>
                  <div className="safety-note">
                    <ShieldCheck aria-hidden="true" /> Tôi không chẩn đoán bệnh hay kê đơn thuốc.
                  </div>
                </div>
              </div>

              {!started && (
                <div className="quick-prompts">
                  <span>Gợi ý nhanh</span>
                  <button type="button" onClick={() => send('Tôi bị đau dạ dày, nên khám khoa nào và bác sĩ nào còn trống lịch?')}>
                    Tôi bị đau dạ dày
                  </button>
                  <button type="button" onClick={() => send('Xem lại giúp tôi lịch sử khám bệnh và dặn dò của bác sĩ lần trước')}>
                    Xem lịch sử khám
                  </button>
                  <button type="button" onClick={() => send('Chọn giúp tôi bác sĩ phù hợp nhất và đặt lịch sớm nhất, giải thích vì sao chọn bác sĩ đó')}>
                    Gợi ý bác sĩ phù hợp
                  </button>
                  <button type="button" onClick={() => send('Quy trình khám bệnh tại Vinmec gồm những bước nào?')}>
                    Quy trình khám bệnh
                  </button>
                </div>
              )}

              {turns.map((turn, idx) => (
                <div key={idx}>
                  <div className="user-bubble">
                    <span>{turn.question}</span>
                    <UserRound aria-hidden="true" />
                  </div>

                  {turn.reply && <ToolTrace steps={turn.reply.steps} running={false} />}

                  {turn.error && (
                    <div className="error-banner">
                      <AlertTriangle aria-hidden="true" />
                      <span>
                        <b>Không nhận được phản hồi từ Agent.</b><br />
                        {turn.error}<br />
                        Hãy kiểm tra API server đã chạy chưa: <code>python src/api_server.py</code>
                      </span>
                    </div>
                  )}

                  {turn.reply && (
                    <div className="agent-result">
                      <div className="result-heading">
                        <div className="message-avatar"><Stethoscope aria-hidden="true" /></div>
                      </div>
                      <div className="agent-body">
                        <span className="message-label">
                          Vinmec Agent
                          <small>{turn.reply.tool_calls} công cụ · {Math.round(turn.reply.elapsed_ms)}ms</small>
                        </span>
                        <div className="agent-answer">
                          <RichText text={trimAnswer(turn.reply.answer, Boolean(turn.reply.ranked?.doctors?.length))} />
                        </div>

                        {turn.reply.patient?.quick_note && !turn.reply.booking && (
                          <QuickNoteBlock note={turn.reply.patient.quick_note} />
                        )}

                        {turn.reply.ranked?.doctors?.length ? (
                          <>
                            {turn.reply.ranked.recommendation && (
                              <div className="reason recommendation">
                                <Sparkles aria-hidden="true" />
                                <span><b>Đề xuất của trợ lý:</b> {turn.reply.ranked.recommendation}</span>
                              </div>
                            )}
                            {turn.reply.ranked.doctors.map((d, i) => (
                              <DoctorCard
                                key={d.doctor_id}
                                doctor={d}
                                isTop={i === 0 && d.match_score !== null}
                                selectedSlot={selected ? `${selected.doctor.doctor_id}|${selected.date}|${selected.time}` : ''}
                                onSelect={(doctor, date, time) => setSelected({ doctor, date, time })}
                              />
                            ))}
                          </>
                        ) : null}
                      </div>
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <>
                  <div className="thinking"><i /><i /><i /> Agent đang suy luận và gọi công cụ…</div>
                  <ToolTrace steps={[]} running />
                </>
              )}

              {/* Bản nháp phiếu hẹn khi người dùng đã chọn bác sĩ + khung giờ */}
              {selected && !loading && (
                <div className="booking-draft">
                  <div className="draft-header">
                    <div>
                      <span className="eyebrow">XÁC NHẬN LỊCH KHÁM</span>
                      <h3>Bạn đã chọn khung giờ</h3>
                    </div>
                    <FileText aria-hidden="true" />
                  </div>
                  <div className="draft-grid">
                    <div><span>Bác sĩ</span><b>{selected.doctor.full_name}</b></div>
                    <div><span>Chuyên khoa</span><b>{selected.doctor.specialty}</b></div>
                    <div><span>Ngày khám</span><b><CalendarDays aria-hidden="true" /> {prettyDate(selected.date)}</b></div>
                    <div><span>Khung giờ</span><b><Clock3 aria-hidden="true" /> {selected.time}</b></div>
                    <div><span>Phòng khám</span><b><MapPin aria-hidden="true" /> {selected.doctor.room}</b></div>
                    <div><span>Phí khám</span><b>{money(selected.doctor.consultation_fee_vnd)}</b></div>
                  </div>
                  <button type="button" className="primary-button confirm-button" onClick={confirmBooking}>
                    Xác nhận đặt lịch <ArrowRight aria-hidden="true" />
                  </button>
                </div>
              )}
            </div>

            {/* ----------------------------- COMPOSER ---------------------------- */}
            <form
              className="composer"
              onSubmit={e => { e.preventDefault(); send(prompt) }}
            >
              <textarea
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                    e.preventDefault()
                    send(prompt)
                  }
                }}
                placeholder={
                  activePatient
                    ? `Hỏi với tư cách ${patient?.full_name ?? activePatient}…`
                    : 'Mô tả triệu chứng hoặc nhu cầu đặt lịch…'
                }
                rows={1}
                aria-label="Tin nhắn cho Vinmec Agent"
                disabled={loading}
              />
              <button className="send-button" type="submit" aria-label="Gửi tin nhắn" disabled={loading || !prompt.trim()}>
                {loading ? <Loader2 className="spin" aria-hidden="true" /> : <Send aria-hidden="true" />}
              </button>
              <span className="composer-hint">
                Enter để gửi · Shift + Enter xuống dòng
                {toolCount > 0 && ` · đã gọi ${toolCount} lượt công cụ trong phiên này`}
              </span>
            </form>
          </section>
        </div>
      </section>

      <button className="floating-help" type="button" aria-label="Mở hỗ trợ">
        <MessageCircle aria-hidden="true" />
      </button>

      {/* -------------------------- HỘP THOẠI THÀNH CÔNG ------------------------- */}
      {success && (
        <div className="modal-backdrop" onClick={() => setSuccess(null)}>
          <div className="success-modal" role="dialog" aria-modal="true" aria-labelledby="success-title" onClick={e => e.stopPropagation()}>
            <button className="modal-close" type="button" aria-label="Đóng" onClick={() => setSuccess(null)}>
              <X aria-hidden="true" />
            </button>
            <div className="success-icon"><Check aria-hidden="true" /></div>
            <h2 id="success-title">Đặt lịch thành công</h2>
            <p>Phiếu hẹn đã được ghi nhận và gửi kèm tóm tắt bệnh sử cho bác sĩ.</p>
            <div className="booking-code">
              <span>Mã phiếu hẹn</span><b>{success.booking_id}</b>
            </div>
            <div className="success-details">
              <b>{success.doctor_name}</b>
              <span>{success.specialty} · {success.room}</span>
              <span>{prettyDate(success.date)} · {success.time_slot}</span>
              <span>Phí khám: {money(success.consultation_fee_vnd)}</span>
            </div>
            {success.doctor_quick_note && <QuickNoteBlock note={success.doctor_quick_note} />}
            <button type="button" className="primary-button modal-done" onClick={() => setSuccess(null)}>
              Hoàn tất
            </button>
          </div>
        </div>
      )}

      {/* ------------------------------ TRACE LOG ------------------------------ */}
      {showTrace && (
        <div className="trace-drawer" onClick={() => setShowTrace(false)}>
          <div className="trace-drawer-panel" onClick={e => e.stopPropagation()}>
            <div className="drawer-head">
              <div>
                <h2>Waterfall Trace Log</h2>
                <p>Chuỗi Thought → Action → Observation mà Agent đã thực thi, ghi tại <code>docs/trace_waterfall.json</code>.</p>
              </div>
              <button className="modal-close inline" type="button" aria-label="Đóng" onClick={() => setShowTrace(false)}>
                <X aria-hidden="true" />
              </button>
            </div>
            <div className="trace-stats">
              <div><b>{trace.length}</b><span>sự kiện</span></div>
              <div><b>{(trace as { action_type?: string }[]).filter(t => t.action_type === 'TOOL_EXECUTION').length}</b><span>lượt gọi công cụ</span></div>
              <div><b>{(trace as { action_type?: string }[]).filter(t => t.action_type === 'FINAL_ANSWER').length}</b><span>câu trả lời</span></div>
            </div>
            <pre className="trace-json">{JSON.stringify(trace, null, 2)}</pre>
          </div>
        </div>
      )}
    </main>
  )
}
