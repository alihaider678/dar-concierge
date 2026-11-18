import { motion } from 'framer-motion'
import { ArrowUpRight, BadgeCheck, Bath, BedDouble, Building2, CalendarCheck, Crown, MapPin, Maximize2, TrendingUp, Wallet } from 'lucide-react'
import { lazy, Suspense, useState } from 'react'
import type { Card, CompareCard, LeadCard, ListingCard, MortgageCard, ProjectCard, StatsCard, YieldCard } from '../lib/api'
import { money } from '../lib/api'
import type { Dict } from '../lib/i18n'

const MiniMap = lazy(() => import('./MiniMap'))

const rise = { initial: { opacity: 0, y: 14 }, animate: { opacity: 1, y: 0 } }

function Img({ src, alt, className }: { src?: string | null; alt: string; className?: string }) {
  const [ok, setOk] = useState(!!src)
  return ok && src ? (
    <img src={src} alt={alt} loading="lazy" onError={() => setOk(false)} className={className} />
  ) : (
    <div className={`${className} grid place-items-center bg-gradient-to-br from-ink-700 to-ink-850`}>
      <Building2 className="h-8 w-8 text-gold-500/40" />
    </div>
  )
}

export function ListingTile({ c, t, i }: { c: ListingCard; t: Dict; i: number }) {
  return (
    <motion.a {...rise} transition={{ delay: i * 0.05 }} href={c.url} target="_blank" rel="noreferrer"
      className="group relative w-64 shrink-0 overflow-hidden rounded-2xl glass hover:border-gold-400/40 transition">
      <div className="relative h-36 overflow-hidden">
        <Img src={c.image} alt={c.title} className="h-full w-full object-cover transition duration-700 group-hover:scale-105" />
        <div className="absolute inset-0 bg-gradient-to-t from-ink-950/90 via-transparent" />
        <span className={`absolute top-2.5 start-2.5 rounded-full px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${c.purpose === 'rent' ? 'bg-sky-400/90 text-ink-950' : 'bg-gold-300 text-ink-950'}`}>
          {c.purpose === 'rent' ? t.rent : t.sale}
        </span>
        {c.rega_licensed && <BadgeCheck className="absolute top-2.5 end-2.5 h-5 w-5 text-emerald-300 drop-shadow" aria-label="REGA licensed" />}
        <div className="absolute bottom-2 start-3 end-3">
          <div className="font-display text-xl font-semibold text-gold-100">
            {money(c.price, c.currency)}
            {c.purpose === 'rent' && c.rent_frequency && <span className="ms-1 text-xs font-sans text-zinc-400">/{c.rent_frequency}</span>}
          </div>
        </div>
      </div>
      <div className="space-y-2 p-3.5">
        <div className="line-clamp-1 text-sm font-medium text-zinc-100">{c.title}</div>
        <div className="flex items-center gap-1 text-xs text-zinc-400"><MapPin className="h-3.5 w-3.5 text-gold-400" />{[c.district, c.city].filter(Boolean).join(', ')}</div>
        <div className="flex items-center gap-3 text-xs text-zinc-300">
          {c.bedrooms != null && <span className="flex items-center gap-1"><BedDouble className="h-3.5 w-3.5 text-zinc-500" />{c.bedrooms} {t.beds}</span>}
          {c.bathrooms != null && <span className="flex items-center gap-1"><Bath className="h-3.5 w-3.5 text-zinc-500" />{c.bathrooms} {t.baths}</span>}
          {c.area_sqm != null && <span className="flex items-center gap-1"><Maximize2 className="h-3.5 w-3.5 text-zinc-500" />{Math.round(c.area_sqm)} {t.sqm}</span>}
        </div>
        <div className="flex items-center justify-between pt-1 text-[11px] text-zinc-500">
          <span>Source: Wasalt.sa</span>
          <span className="flex items-center gap-0.5 text-gold-300 opacity-0 transition group-hover:opacity-100">{t.onWasalt}<ArrowUpRight className="h-3 w-3" /></span>
        </div>
      </div>
    </motion.a>
  )
}

export function ProjectTile({ c, t, i, wide }: { c: ProjectCard; t: Dict; i: number; wide?: boolean }) {
  const loc = c.specs?.location || c.country
  return (
    <motion.a {...rise} transition={{ delay: i * 0.06 }} href={c.url} target="_blank" rel="noreferrer"
      className={`group relative shrink-0 overflow-hidden rounded-2xl gold-border ${wide ? 'w-full' : 'w-72'} h-60`}>
      <Img src={c.image} alt={c.name} className="absolute inset-0 h-full w-full object-cover transition duration-[1.2s] group-hover:scale-110" />
      <div className="absolute inset-0 bg-gradient-to-t from-ink-950 via-ink-950/55 to-transparent" />
      <div className="absolute inset-x-0 bottom-0 space-y-1.5 p-4">
        <div className="flex flex-wrap gap-1.5">
          {c.brands?.slice(0, 2).map(b => (
            <span key={b} className="flex items-center gap-1 rounded-full bg-gold-300/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gold-200 backdrop-blur">
              <Crown className="h-3 w-3" />{b}
            </span>
          ))}
        </div>
        <div className="font-display text-2xl font-semibold leading-tight text-white">{c.name}</div>
        {loc && <div className="flex items-center gap-1 text-xs text-zinc-300"><MapPin className="h-3.5 w-3.5 text-gold-400" />{loc}</div>}
        <div className="flex items-center gap-1 pt-1 text-xs text-gold-300 opacity-80 group-hover:opacity-100">{t.explore}<ArrowUpRight className="h-3.5 w-3.5 transition group-hover:translate-x-0.5 group-hover:-translate-y-0.5" /></div>
      </div>
    </motion.a>
  )
}

function Compare({ c, t }: { c: CompareCard; t: Dict }) {
  const keys = Array.from(new Set(c.items.flatMap(p => Object.keys(p.specs || {})))).slice(0, 7)
  return (
    <motion.div {...rise} className="overflow-hidden rounded-2xl glass">
      <div className="grid" style={{ gridTemplateColumns: `repeat(${c.items.length}, minmax(0,1fr))` }}>
        {c.items.map((p, i) => <div key={p.slug} className="p-2"><ProjectTile c={p} t={t} i={i} wide /></div>)}
      </div>
      {keys.length > 0 && (
        <div className="divide-y divide-white/5 border-t border-white/5 text-sm">
          {keys.map(k => (
            <div key={k} className="grid" style={{ gridTemplateColumns: `repeat(${c.items.length}, minmax(0,1fr))` }}>
              {c.items.map(p => (
                <div key={p.slug} className="px-4 py-2.5">
                  <div className="text-[10px] uppercase tracking-wider text-gold-400/80">{k.replace(/_/g, ' ')}</div>
                  <div className="text-zinc-200">{p.specs?.[k] || '—'}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      )}
    </motion.div>
  )
}

function Metric({ label, value, big }: { label: string; value: string; big?: boolean }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-[.14em] text-zinc-500">{label}</div>
      <div className={`${big ? 'font-display text-3xl gold-text' : 'text-base text-zinc-100'} font-semibold`}>{value}</div>
    </div>
  )
}

function Mortgage({ c, t }: { c: MortgageCard; t: Dict }) {
  const pctInterest = Math.round((c.total_interest / (c.loan_amount + c.total_interest)) * 100)
  return (
    <motion.div {...rise} className="relative overflow-hidden rounded-2xl glass p-5 max-w-xl">
      <Wallet className="absolute -end-4 -top-4 h-28 w-28 text-gold-400/5" />
      <div className="grid grid-cols-2 gap-5 sm:grid-cols-4">
        <div className="col-span-2"><Metric big label={t.monthly} value={`${c.currency} ${c.monthly_payment.toLocaleString()}`} /></div>
        <Metric label={t.down} value={money(c.down_payment, c.currency)} />
        <Metric label={t.loan} value={money(c.loan_amount, c.currency)} />
      </div>
      <div className="mt-5">
        <div className="mb-1.5 flex justify-between text-[11px] text-zinc-400">
          <span>Principal {100 - pctInterest}%</span><span>{t.interest} {money(c.total_interest, c.currency)} · {pctInterest}%</span>
        </div>
        <div className="flex h-2 overflow-hidden rounded-full bg-ink-700">
          <motion.div initial={{ width: 0 }} animate={{ width: `${100 - pctInterest}%` }} transition={{ duration: 1 }} className="bg-gradient-to-r from-gold-500 to-gold-200" />
        </div>
        <div className="mt-2 text-[11px] text-zinc-500">{c.annual_rate_pct}% · {c.years}y · indicative</div>
      </div>
    </motion.div>
  )
}

function Yield({ c, t }: { c: YieldCard; t: Dict }) {
  const pct = Math.min(c.gross_yield_pct / 12, 1) * 100
  return (
    <motion.div {...rise} className="flex max-w-xl items-center gap-6 rounded-2xl glass p-5">
      <div className="relative h-24 w-24 shrink-0">
        <svg viewBox="0 0 36 36" className="h-full w-full -rotate-90">
          <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1e1e28" strokeWidth="3" />
          <motion.circle cx="18" cy="18" r="15.9" fill="none" stroke="url(#yg)" strokeWidth="3" strokeLinecap="round"
            initial={{ strokeDasharray: '0 100' }} animate={{ strokeDasharray: `${pct} 100` }} transition={{ duration: 1.1 }} />
          <defs><linearGradient id="yg"><stop offset="0" stopColor="#b8893b" /><stop offset="1" stopColor="#f3dfa2" /></linearGradient></defs>
        </svg>
        <div className="absolute inset-0 grid place-items-center font-display text-xl font-semibold text-gold-100">{c.gross_yield_pct}%</div>
      </div>
      <div className="grid flex-1 grid-cols-2 gap-4">
        <Metric label={t.gross} value={`${c.gross_yield_pct}%`} />
        <Metric label={t.net} value={`${c.net_yield_pct}%`} />
        <Metric label={t.payback} value={`${c.payback_years}y`} />
        <Metric label="Rent / yr" value={money(c.annual_rent, c.currency)} />
      </div>
    </motion.div>
  )
}

function Stats({ c, t }: { c: StatsCard; t: Dict }) {
  const max = Math.max(...c.top_districts.map(d => d.median_price_sar), 1)
  return (
    <motion.div {...rise} className="max-w-2xl rounded-2xl glass p-5">
      <div className="mb-4 flex items-center gap-2 text-xs uppercase tracking-[.14em] text-gold-300">
        <TrendingUp className="h-4 w-4" />{c.scope.city} · {c.scope.purpose} · {c.scope.type} · {c.count} listings
      </div>
      <div className="grid grid-cols-3 gap-4">
        <Metric big label={t.median} value={money(c.median_price_sar)} />
        <Metric label={t.perSqm} value={c.median_price_per_sqm_sar ? `SAR ${c.median_price_per_sqm_sar.toLocaleString()}` : '—'} />
        <Metric label={t.range} value={c.p25_price_sar ? `${money(c.p25_price_sar)} – ${money(c.p75_price_sar).replace('SAR ', '')}` : '—'} />
      </div>
      {c.top_districts.length > 0 && (
        <div className="mt-5 space-y-2">
          <div className="text-[10px] uppercase tracking-[.14em] text-zinc-500">{t.topDistricts}</div>
          {c.top_districts.slice(0, 6).map((d, i) => (
            <div key={d.district} className="grid grid-cols-[8rem_1fr_5rem] items-center gap-3 text-xs">
              <span className="truncate text-zinc-300">{d.district}</span>
              <div className="h-1.5 overflow-hidden rounded-full bg-ink-700">
                <motion.div initial={{ width: 0 }} animate={{ width: `${(d.median_price_sar / max) * 100}%` }} transition={{ delay: i * 0.08, duration: 0.8 }}
                  className="h-full rounded-full bg-gradient-to-r from-gold-600 to-gold-300" />
              </div>
              <span className="text-end text-zinc-400">{money(d.median_price_sar)}</span>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  )
}

function Lead({ c, t }: { c: LeadCard; t: Dict }) {
  return (
    <motion.div {...rise} className="flex max-w-md items-center gap-4 rounded-2xl border border-emerald-400/25 bg-emerald-400/5 p-4">
      <div className="grid h-11 w-11 place-items-center rounded-full bg-emerald-400/15"><CalendarCheck className="h-5 w-5 text-emerald-300" /></div>
      <div className="text-sm">
        <div className="font-medium text-emerald-200">{t.leadSaved}</div>
        <div className="text-zinc-400">{c.interest}{c.preferred_time ? ` · ${c.preferred_time}` : ''}</div>
        <div className="text-xs text-zinc-500">{t.ref}: <span className="font-mono text-zinc-300">{c.reference}</span></div>
      </div>
    </motion.div>
  )
}

export function CardDeck({ cards, t }: { cards: Card[]; t: Dict }) {
  const listings = dedupe(cards.filter((c): c is ListingCard => c.kind === 'listing'), c => c.id)
  const compares = cards.filter((c): c is CompareCard => c.kind === 'compare')
  const compared = new Set(compares.flatMap(c => c.items.map(i => i.slug)))
  const projects = dedupe(cards.filter((c): c is ProjectCard => c.kind === 'project' && !compared.has(c.slug)), c => c.slug)
  const others = cards.filter(c => !['listing', 'project', 'compare'].includes(c.kind))
  const pins = listings.filter(l => l.lat && l.lon)
  const [showMap, setShowMap] = useState(false)
  if (!cards.length) return null
  return (
    <div className="space-y-3">
      {compares.map((c, i) => <Compare key={i} c={c} t={t} />)}
      {projects.length > 0 && (
        <div className="scroll-thin -mx-1 flex gap-3 overflow-x-auto px-1 pb-2">{projects.map((c, i) => <ProjectTile key={c.slug} c={c} t={t} i={i} />)}</div>
      )}
      {listings.length > 0 && (
        <>
          <div className="scroll-thin -mx-1 flex gap-3 overflow-x-auto px-1 pb-2">{listings.map((c, i) => <ListingTile key={c.id} c={c} t={t} i={i} />)}</div>
          {pins.length > 0 && (
            <button onClick={() => setShowMap(s => !s)} className="flex items-center gap-1.5 text-xs text-gold-300 hover:text-gold-100">
              <MapPin className="h-3.5 w-3.5" />{t.map} ({pins.length})
            </button>
          )}
          {showMap && <Suspense fallback={<div className="h-64 animate-pulse rounded-2xl bg-ink-800" />}><MiniMap pins={pins} /></Suspense>}
        </>
      )}
      {others.map((c, i) => {
        switch (c.kind) {
          case 'mortgage': return <Mortgage key={i} c={c} t={t} />
          case 'yield': return <Yield key={i} c={c} t={t} />
          case 'stats': return <Stats key={i} c={c} t={t} />
          case 'lead': return <Lead key={i} c={c} t={t} />
          default: return null
        }
      })}
    </div>
  )
}

function dedupe<T>(arr: T[], key: (x: T) => unknown): T[] {
  const s = new Set(); return arr.filter(x => { const k = key(x); if (s.has(k)) return false; s.add(k); return true })
}
