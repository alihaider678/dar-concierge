export type Role = 'user' | 'assistant'

export interface ListingCard {
  kind: 'listing'; id: number; title: string; url: string; purpose: string; type: string
  city: string; district: string; price: number; currency: string; rent_frequency?: string | null
  bedrooms?: number | null; bathrooms?: number | null; area_sqm?: number | null
  image?: string | null; lat?: number | null; lon?: number | null; rega_licensed: boolean
}
export interface ProjectCard {
  kind: 'project'; slug: string; name: string; url: string; country?: string | null
  brands: string[]; summary: string; specs: Record<string, string>; image?: string | null
}
export interface CompareCard { kind: 'compare'; items: ProjectCard[] }
export interface MortgageCard {
  kind: 'mortgage'; property_price: number; currency: string; down_payment: number; loan_amount: number
  annual_rate_pct: number; years: number; monthly_payment: number; total_interest: number; total_paid: number
}
export interface YieldCard {
  kind: 'yield'; property_price: number; annual_rent: number; currency: string
  gross_yield_pct: number; net_yield_pct: number; payback_years: number
}
export interface StatsCard {
  kind: 'stats'; scope: { city: string; purpose: string; type: string }; count: number
  median_price_sar: number; p25_price_sar?: number | null; p75_price_sar?: number | null
  median_price_per_sqm_sar?: number | null
  top_districts: { district: string; listings: number; median_price_sar: number }[]
  type_mix: Record<string, number>
}
export interface LeadCard { kind: 'lead'; reference: string; name: string; interest: string; preferred_time?: string | null }
export type Card = ListingCard | ProjectCard | CompareCard | MortgageCard | YieldCard | StatsCard | LeadCard

export interface TraceStep {
  id: string; name: string; args: Record<string, unknown>
  status: 'running' | 'done'; summary?: string; ms?: number
}
export interface Message {
  id: string; role: Role; content: string
  trace?: TraceStep[]; cards?: Card[]; status?: string; model?: string
  fallbacks?: string[]; error?: string; streaming?: boolean; ms?: number
}

export interface AgentEvent {
  type: 'status' | 'token' | 'reset' | 'tool_start' | 'tool_end' | 'cards' | 'fallback' | 'error' | 'done'
  [k: string]: any // eslint-disable-line @typescript-eslint/no-explicit-any
}

export interface Stats {
  listings: number; for_sale: number; for_rent: number; cities: number; projects: number
  passages: number; top_cities: string[]; countries: string[]
}
export interface ProjectSummary {
  slug: string; name: string; country?: string; brands: string[]; image?: string; url: string
  summary: string; location?: string
}

export async function streamChat(
  messages: { role: Role; content: string }[],
  onEvent: (e: AgentEvent) => void,
  signal?: AbortSignal,
) {
  const res = await fetch('/api/chat', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }), signal,
  })
  if (!res.ok || !res.body) {
    let msg = `Request failed (${res.status})`
    try { msg = (await res.json()).detail || msg } catch { /* ignore */ }
    onEvent({ type: 'error', message: msg })
    return
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const raw = buf.slice(0, i); buf = buf.slice(i + 2)
      const line = raw.split('\n').find(l => l.startsWith('data:'))
      if (line) { try { onEvent(JSON.parse(line.slice(5).trim())) } catch { /* skip */ } }
    }
  }
}

export const getJSON = <T,>(url: string): Promise<T> => fetch(url).then(r => r.json())

export function money(v: number | null | undefined, cur = 'SAR') {
  if (v == null || isNaN(v)) return '—'
  const abs = Math.abs(v)
  const s = abs >= 1e6 ? `${(v / 1e6).toFixed(abs >= 1e7 ? 1 : 2).replace(/\.0+$/, '')}M`
    : abs >= 1e4 ? `${Math.round(v / 1e3)}K` : Math.round(v).toLocaleString()
  return `${cur} ${s}`
}
