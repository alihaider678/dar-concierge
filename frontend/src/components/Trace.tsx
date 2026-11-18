import { AnimatePresence, motion } from 'framer-motion'
import { BarChart3, Building, Calculator, CalendarCheck, Check, ChevronDown, Coins, GitCompare, Library, Loader2, Percent, Search, Shuffle, Sparkles } from 'lucide-react'
import { useState } from 'react'
import type { Message } from '../lib/api'
import type { Dict, Lang } from '../lib/i18n'
import { TOOL_LABELS } from '../lib/i18n'

const ICONS: Record<string, typeof Search> = {
  search_listings: Search, market_stats: BarChart3, search_darglobal: Library,
  list_darglobal_projects: Building, get_project_details: Building, compare_projects: GitCompare,
  calculate_mortgage: Calculator, estimate_rental_yield: Percent, convert_currency: Coins, capture_lead: CalendarCheck,
}

function argText(args: Record<string, unknown>) {
  return Object.entries(args).filter(([, v]) => v !== null && v !== '' && v !== undefined)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? v.join(' | ') : String(v)}`).join(' · ')
}

export default function Trace({ m, t, lang }: { m: Message; t: Dict; lang: Lang }) {
  const steps = m.trace || []
  const [open, setOpen] = useState(true)
  const running = m.streaming && !m.content
  if (!steps.length && !running) return null
  return (
    <div className="mb-3 rounded-xl border border-white/5 bg-white/[.02]">
      <button onClick={() => setOpen(o => !o)} className="flex w-full items-center gap-2 px-3.5 py-2.5 text-xs">
        <Sparkles className="h-3.5 w-3.5 text-gold-300" />
        <span className={running ? 'shimmer font-medium' : 'text-zinc-400'}>
          {running ? (m.status || t.thinking) : `${t.trace} · ${steps.length} ${t.steps}${m.ms ? ` · ${(m.ms / 1000).toFixed(1)}s` : ''}`}
        </span>
        {m.model && <span className="ms-auto hidden truncate rounded-md bg-white/5 px-1.5 py-0.5 font-mono text-[10px] text-zinc-500 sm:block">{m.model.replace(':free', '')}</span>}
        <ChevronDown className={`h-3.5 w-3.5 text-zinc-500 transition ${open ? 'rotate-180' : ''} ${m.model ? '' : 'ms-auto'}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (steps.length > 0 || (m.fallbacks?.length ?? 0) > 0) && (
          <motion.ol initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            className="relative space-y-2.5 overflow-hidden px-3.5 pb-3">
            {m.fallbacks?.map((f, i) => (
              <li key={`fb${i}`} className="flex items-center gap-2 text-[11px] text-amber-300/70"><Shuffle className="h-3 w-3" />{t.fallback}: {f}</li>
            ))}
            {steps.map((s, i) => {
              const Icon = ICONS[s.name] || Search
              return (
                <motion.li key={s.id + i} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} className="relative flex gap-3">
                  {i < steps.length - 1 && <span className="absolute start-[13px] top-7 h-[calc(100%-12px)] w-px bg-gradient-to-b from-gold-500/40 to-transparent" />}
                  <div className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${s.status === 'done' ? 'bg-gold-400/10 text-gold-300' : 'bg-white/5 text-zinc-400'}`}>
                    {s.status === 'running' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
                  </div>
                  <div className="min-w-0 flex-1 text-xs">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-zinc-200">{TOOL_LABELS[s.name]?.[lang] || s.name}</span>
                      {s.status === 'done' && <Check className="h-3 w-3 text-emerald-400" />}
                      {s.ms != null && <span className="text-[10px] text-zinc-600">{s.ms}ms</span>}
                    </div>
                    <div className="truncate font-mono text-[10.5px] text-zinc-500" dir="ltr">{s.name}({argText(s.args)})</div>
                    {s.summary && <div className="mt-0.5 text-[11px] text-gold-200/70">→ {s.summary}</div>}
                  </div>
                </motion.li>
              )
            })}
          </motion.ol>
        )}
      </AnimatePresence>
    </div>
  )
}
