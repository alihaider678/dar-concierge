import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, ArrowUp, Building2, Calculator, Crown, Globe2, Languages, MapPinned, Plus, RotateCcw, Square } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { CardDeck } from './components/Cards'
import Trace from './components/Trace'
import type { AgentEvent, Message, ProjectSummary, Stats } from './lib/api'
import { getJSON, streamChat } from './lib/api'
import type { Lang } from './lib/i18n'
import { PROMPTS, T } from './lib/i18n'

const uid = () => Math.random().toString(36).slice(2, 10)
const GROUP_ICON = { luxury: Crown, saudi: MapPinned, tools: Calculator }

export default function App() {
  const [lang, setLang] = useState<Lang>(() => (localStorage.getItem('dc-lang') as Lang) || 'en')
  const t = T[lang]
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [stats, setStats] = useState<Stats | null>(null)
  const [projects, setProjects] = useState<ProjectSummary[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const endRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr'
    document.documentElement.lang = lang
    localStorage.setItem('dc-lang', lang)
  }, [lang])
  useEffect(() => {
    getJSON<Stats>('/api/stats').then(setStats).catch(() => {})
    getJSON<ProjectSummary[]>('/api/projects').then(p => setProjects(p.filter(x => x.image))).catch(() => {})
  }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' }) }, [messages])

  const patch = (id: string, fn: (m: Message) => Message) => setMessages(ms => ms.map(m => (m.id === id ? fn(m) : m)))

  const send = useCallback(async (text: string, base?: Message[]) => {
    const q = text.trim()
    if (!q || busy) return
    const user: Message = { id: uid(), role: 'user', content: q }
    const bot: Message = { id: uid(), role: 'assistant', content: '', trace: [], cards: [], streaming: true, status: T[lang].planning }
    const history = [...(base ?? messages), user]
    setMessages([...history, bot])
    setInput('')
    setBusy(true)
    const ctrl = new AbortController()
    abortRef.current = ctrl
    const onEvent = (e: AgentEvent) => {
      patch(bot.id, m => {
        switch (e.type) {
          case 'status': return { ...m, model: e.model, status: e.step ? T[lang].composing : T[lang].planning }
          case 'token': return { ...m, content: m.content + e.text }
          case 'reset': return { ...m, content: '' }
          case 'tool_start': return { ...m, trace: [...(m.trace || []), { id: e.id, name: e.name, args: e.args, status: 'running' }] }
          case 'tool_end': return { ...m, trace: (m.trace || []).map(s => (s.id === e.id && s.status === 'running' ? { ...s, status: 'done', summary: e.summary, ms: e.ms } : s)) }
          case 'cards': return { ...m, cards: [...(m.cards || []), ...e.cards] }
          case 'fallback': return { ...m, fallbacks: [...(m.fallbacks || []), `${String(e.from).split('/')[1]?.replace(':free', '')} → ${String(e.to).split('/')[1]?.replace(':free', '')}`] }
          case 'error': return { ...m, error: e.message, streaming: false }
          case 'done': return { ...m, streaming: false, model: e.model, ms: e.ms }
          default: return m
        }
      })
    }
    try {
      await streamChat(history.map(({ role, content }) => ({ role, content })), onEvent, ctrl.signal)
    } catch (err) {
      if ((err as Error).name !== 'AbortError') onEvent({ type: 'error', message: 'Connection lost. Please retry.' })
    } finally {
      patch(bot.id, m => ({ ...m, streaming: false }))
      setBusy(false)
      abortRef.current = null
    }
  }, [busy, messages, lang])

  const retry = (botId: string) => {
    const idx = messages.findIndex(m => m.id === botId)
    const prevUser = messages[idx - 1]
    if (prevUser?.role === 'user') send(prevUser.content, messages.slice(0, idx - 1))
  }
  const reset = () => { abortRef.current?.abort(); setMessages([]); setBusy(false) }
  const empty = messages.length === 0

  useEffect(() => {
    const ta = taRef.current
    if (ta) { ta.style.height = 'auto'; ta.style.height = `${Math.min(ta.scrollHeight, 180)}px` }
  }, [input])

  return (
    <div className="grain relative flex h-full">
      <Sidebar lang={lang} setLang={setLang} stats={stats} projects={projects} onNew={reset} onAsk={q => send(q)} />
      <main className="relative z-10 flex min-w-0 flex-1 flex-col">
        <TopBar lang={lang} setLang={setLang} onNew={reset} />
        <div className="scroll-thin flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-4xl px-4 pb-44 sm:px-8">
            <AnimatePresence mode="wait">
              {empty ? (
                <Hero key="hero" lang={lang} stats={stats} projects={projects} onAsk={q => send(q)} />
              ) : (
                <motion.div key="chat" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-8 pt-8">
                  {messages.map(m => (m.role === 'user' ? (
                    <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
                      <div className="max-w-[85%] rounded-2xl rounded-ee-md bg-gradient-to-br from-gold-300 to-gold-500 px-4 py-2.5 text-[0.95rem] font-medium text-ink-950 shadow-lg shadow-gold-500/10">{m.content}</div>
                    </motion.div>
                  ) : (
                    <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="flex gap-3 sm:gap-4">
                      <Avatar pulse={!!m.streaming} />
                      <div className="min-w-0 flex-1">
                        <Trace m={m} t={t} lang={lang} />
                        {m.cards && m.cards.length > 0 && <div className="mb-4"><CardDeck cards={m.cards} t={t} /></div>}
                        {m.content && (
                          <div className={`prose-dc ${m.streaming ? 'caret' : ''}`}>
                            <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: p => <a {...p} target="_blank" rel="noreferrer" /> }}>{m.content}</ReactMarkdown>
                          </div>
                        )}
                        {m.error && (
                          <div className="mt-2 flex items-center gap-3 rounded-xl border border-amber-400/20 bg-amber-400/5 px-3.5 py-2.5 text-sm text-amber-200">
                            <AlertTriangle className="h-4 w-4 shrink-0" />{m.error}
                            <button onClick={() => retry(m.id)} className="ms-auto flex items-center gap-1 text-xs text-gold-200 hover:text-white"><RotateCcw className="h-3.5 w-3.5" />{t.retry}</button>
                          </div>
                        )}
                      </div>
                    </motion.div>
                  )))}
                  <div ref={endRef} />
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Composer */}
        <div className="pointer-events-none absolute inset-x-0 bottom-0 bg-gradient-to-t from-ink-950 via-ink-950/95 to-transparent pt-16">
          <div className="pointer-events-auto mx-auto w-full max-w-4xl px-4 pb-4 sm:px-8 sm:pb-6">
            <form onSubmit={e => { e.preventDefault(); send(input) }}
              className="group relative flex items-end gap-2 rounded-2xl glass p-2 shadow-2xl shadow-black/50 transition focus-within:border-gold-400/40">
              <textarea ref={taRef} rows={1} value={input} onChange={e => setInput(e.target.value)} placeholder={t.placeholder}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input) } }}
                className="max-h-44 flex-1 resize-none bg-transparent px-3 py-2.5 text-[0.95rem] text-zinc-100 placeholder:text-zinc-500 focus:outline-none" />
              {busy ? (
                <button type="button" onClick={() => abortRef.current?.abort()} aria-label={t.stop}
                  className="grid h-10 w-10 place-items-center rounded-xl bg-white/10 text-zinc-200 hover:bg-white/15"><Square className="h-4 w-4 fill-current" /></button>
              ) : (
                <button type="submit" disabled={!input.trim()} aria-label={t.send}
                  className="grid h-10 w-10 place-items-center rounded-xl bg-gradient-to-br from-gold-200 to-gold-500 text-ink-950 transition hover:brightness-110 disabled:opacity-30"><ArrowUp className="h-5 w-5" /></button>
              )}
            </form>
            <p className="mt-2 text-center text-[10.5px] text-zinc-600">{t.disclaimer}</p>
          </div>
        </div>
      </main>
    </div>
  )
}

function Avatar({ pulse }: { pulse?: boolean }) {
  return (
    <div className="relative mt-0.5 h-9 w-9 shrink-0">
      {pulse && <span className="absolute inset-0 animate-ping rounded-xl bg-gold-400/20" />}
      <div className="relative grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-ink-700 to-ink-850 gold-border">
        <span className="font-display text-lg font-bold gold-text">D</span>
      </div>
    </div>
  )
}

function Logo({ lang }: { lang: Lang }) {
  return (
    <div className="flex items-center gap-3">
      <div className="grid h-10 w-10 place-items-center rounded-xl bg-ink-850 gold-border shadow-lg shadow-gold-500/10">
        <span className="font-display text-2xl font-bold gold-text">D</span>
      </div>
      <div>
        <div className="font-display text-xl font-semibold leading-none tracking-wide text-gold-100">{T[lang].brand}</div>
        <div className="mt-1 text-[10px] uppercase tracking-[.22em] text-zinc-500">{T[lang].tagline}</div>
      </div>
    </div>
  )
}

function LangToggle({ lang, setLang }: { lang: Lang; setLang: (l: Lang) => void }) {
  return (
    <button onClick={() => setLang(lang === 'en' ? 'ar' : 'en')}
      className="flex items-center gap-1.5 rounded-lg border border-white/10 px-2.5 py-1.5 text-xs text-zinc-300 hover:border-gold-400/40 hover:text-gold-100">
      <Languages className="h-3.5 w-3.5" />{lang === 'en' ? 'العربية' : 'English'}
    </button>
  )
}

function TopBar({ lang, setLang, onNew }: { lang: Lang; setLang: (l: Lang) => void; onNew: () => void }) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 px-4 py-3 lg:hidden">
      <Logo lang={lang} />
      <div className="flex gap-2">
        <LangToggle lang={lang} setLang={setLang} />
        <button onClick={onNew} aria-label={T[lang].newChat} className="rounded-lg border border-white/10 p-1.5 text-zinc-300"><Plus className="h-4 w-4" /></button>
      </div>
    </div>
  )
}

function Sidebar({ lang, setLang, stats, projects, onNew, onAsk }: {
  lang: Lang; setLang: (l: Lang) => void; stats: Stats | null; projects: ProjectSummary[]; onNew: () => void; onAsk: (q: string) => void
}) {
  const t = T[lang]
  return (
    <aside className="relative z-10 hidden w-80 shrink-0 flex-col border-e border-white/5 bg-ink-900/60 backdrop-blur-xl lg:flex">
      <div className="space-y-5 p-5">
        <Logo lang={lang} />
        <button onClick={onNew} className="flex w-full items-center justify-center gap-2 rounded-xl border border-gold-400/25 bg-gold-400/5 py-2.5 text-sm text-gold-100 transition hover:bg-gold-400/10">
          <Plus className="h-4 w-4" />{t.newChat}
        </button>
        <div className="grid grid-cols-2 gap-2">
          {[
            { v: stats?.listings, l: t.listings, I: MapPinned },
            { v: stats?.projects, l: t.projects, I: Building2 },
            { v: stats?.cities, l: t.cities, I: Globe2 },
            { v: stats?.countries?.length, l: t.countries, I: Crown },
          ].map(({ v, l, I }) => (
            <div key={l} className="rounded-xl glass p-3">
              <I className="mb-1.5 h-3.5 w-3.5 text-gold-400" />
              <div className="font-display text-2xl font-semibold text-gold-100">{v != null ? v.toLocaleString() : '—'}</div>
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">{l}</div>
            </div>
          ))}
        </div>
      </div>
      <div className="px-5 text-[10px] uppercase tracking-[.22em] text-zinc-500">{t.collection}</div>
      <div className="scroll-thin mt-3 flex-1 space-y-2 overflow-y-auto px-5 pb-4">
        {projects.slice(0, 24).map(p => (
          <button key={p.slug} onClick={() => onAsk(lang === 'ar' ? `أخبرني عن ${p.name}` : `Tell me about ${p.name}`)}
            className="group flex w-full items-center gap-3 rounded-xl p-1.5 text-start transition hover:bg-white/5">
            <img src={p.image} alt="" loading="lazy" className="h-11 w-14 shrink-0 rounded-lg object-cover opacity-80 group-hover:opacity-100" />
            <div className="min-w-0">
              <div className="truncate text-sm text-zinc-200 group-hover:text-gold-100">{p.name}</div>
              <div className="truncate text-[11px] text-zinc-500">{p.location || p.country}</div>
            </div>
          </button>
        ))}
      </div>
      <div className="flex items-center justify-between border-t border-white/5 p-4">
        <span className="flex items-center gap-1.5 text-[11px] text-zinc-500"><span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />{t.poweredBy}</span>
        <LangToggle lang={lang} setLang={setLang} />
      </div>
    </aside>
  )
}

function Hero({ lang, stats, projects, onAsk }: { lang: Lang; stats: Stats | null; projects: ProjectSummary[]; onAsk: (q: string) => void }) {
  const t = T[lang]
  const groups = useMemo(() => (['luxury', 'saudi', 'tools'] as const).map(g => ({ g, items: PROMPTS[lang].filter(p => p.group === g) })), [lang])
  const strip = projects.slice(0, 8)
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -12 }} className="pt-10 sm:pt-16">
      <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-gold-400/20 bg-gold-400/5 px-3 py-1 text-[11px] uppercase tracking-[.2em] text-gold-200">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-gold-300" />{t.heroKicker}
      </div>
      <h1 className="font-display text-4xl font-semibold leading-[1.05] sm:text-6xl">
        <span className="text-zinc-100">{t.heroTitle1}</span><br /><span className="gold-text">{t.heroTitle2}</span>
      </h1>
      <p className="mt-5 max-w-2xl text-[0.98rem] leading-relaxed text-zinc-400">{t.heroSub}</p>
      {stats && (
        <div className="mt-6 flex flex-wrap gap-x-6 gap-y-2 text-sm text-zinc-400">
          <span><b className="text-gold-200">{stats.listings.toLocaleString()}</b> {t.listings}</span>
          <span><b className="text-gold-200">{stats.projects}</b> {t.projects}</span>
          <span><b className="text-gold-200">{stats.countries.length}</b> {t.countries}</span>
        </div>
      )}

      {strip.length > 0 && (
        <div className="relative mt-9 -mx-4 overflow-hidden sm:-mx-8">
          <div className="pointer-events-none absolute inset-y-0 start-0 z-10 w-16 bg-gradient-to-r from-ink-950 to-transparent rtl:bg-gradient-to-l" />
          <div className="pointer-events-none absolute inset-y-0 end-0 z-10 w-16 bg-gradient-to-l from-ink-950 to-transparent rtl:bg-gradient-to-r" />
          <motion.div className="flex w-max gap-3 px-4" animate={{ x: lang === 'ar' ? ['0%', '50%'] : ['0%', '-50%'] }} transition={{ duration: 45, ease: 'linear', repeat: Infinity }}>
            {[...strip, ...strip].map((p, i) => (
              <button key={i} onClick={() => onAsk(lang === 'ar' ? `أخبرني عن ${p.name}` : `Tell me about ${p.name}`)}
                className="group relative h-40 w-60 shrink-0 overflow-hidden rounded-2xl gold-border">
                <img src={p.image} alt={p.name} className="absolute inset-0 h-full w-full object-cover transition duration-700 group-hover:scale-110" />
                <div className="absolute inset-0 bg-gradient-to-t from-ink-950/95 via-ink-950/20" />
                <div className="absolute bottom-3 start-3 end-3 text-start">
                  <div className="font-display text-lg font-semibold leading-tight text-white">{p.name}</div>
                  <div className="text-[11px] text-gold-200/80">{p.location || p.country}</div>
                </div>
              </button>
            ))}
          </motion.div>
        </div>
      )}

      <div className="mt-10 grid gap-4 md:grid-cols-3">
        {groups.map(({ g, items }, gi) => {
          const Icon = GROUP_ICON[g]
          return (
            <motion.div key={g} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + gi * 0.08 }} className="space-y-2">
              <div className="flex items-center gap-2 text-[11px] uppercase tracking-[.18em] text-gold-300/80"><Icon className="h-3.5 w-3.5" />{t[g]}</div>
              {items.map(p => (
                <button key={p.text} onClick={() => onAsk(p.text)}
                  className="w-full rounded-xl glass px-3.5 py-3 text-start text-[13px] leading-snug text-zinc-300 transition hover:-translate-y-0.5 hover:border-gold-400/30 hover:text-gold-100">
                  {p.text}
                </button>
              ))}
            </motion.div>
          )
        })}
      </div>
    </motion.div>
  )
}
