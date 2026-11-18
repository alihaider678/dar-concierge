// Runs inside a normal Chrome tab on wasalt.sa (paste into DevTools console).
// Reads public SEO search pages (32 listings each), keeps only listing facts
// (no owner/contact data) and downloads them as wasalt_listings.json, which
// scraper/import_wasalt.py then merges into data/raw/wasalt_listings.jsonl.
// Polite: sequential requests with a 1.5s delay.
window.__dcCollect = async function (paths, { delay = 1500 } = {}) {
  const IMG = (id, n) => `https://imagedelivery.net/1DNKFJPRaeUdy_j8F7HT3w/production/properties/${id}/images/${n}/width=800,quality=60,format=auto`
  const num = v => { const n = parseFloat(String(v ?? '').replace(/,/g, '')); return isFinite(n) ? n : null }
  const all = new Map()
  const log = []
  for (const path of paths) {
    try {
      const html = await fetch(path).then(r => r.text())
      const m = html.match(/id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/)
      const props = JSON.parse(m[1]).props.pageProps.searchResult?.properties || []
      let added = 0
      for (const p of props) {
        const i = p.propertyInfo || {}
        const a = Object.fromEntries((p.attributes || []).map(x => [x.key, x.value]))
        const sale = i.propertyFor === 'sale'
        const rec = {
          id: p.id, url: `https://wasalt.sa/en/property/${i.propertyFor}/${i.slug}`,
          title: i.title, purpose: i.propertyFor, category: i.propertyMainType, type: i.propertySubType,
          city: i.city, district: i.district || i.zone, territory: i.territory, address: i.address,
          price: sale ? num(i.salePrice) : num(i.expectedRent), rent_frequency: i.rentFreq || null,
          currency: i.currencyType || 'SAR', bedrooms: num(a.noOfBedrooms), bathrooms: num(a.noOfBathrooms),
          area_sqm: num(a.builtUpArea ?? a.landArea), furnishing: i.furnishingType || null,
          description: (i.description || '').slice(0, 1500),
          amenities: (p.featureAmenities || []).map(x => x?.name).filter(Boolean).slice(0, 20),
          lat: num(p.location?.lat), lon: num(p.location?.lon),
          images: (p.propertyFiles?.images || []).slice(0, 6).map(n => IMG(p.id, n)),
          rega_licensed: !!p.isRegaProp, verified: !!p.isVerified,
          published_at: p.publishedAt, updated_at: p.updatedAt, source: 'Wasalt.sa',
        }
        if (rec.price && !all.has(rec.id)) { all.set(rec.id, rec); added++ }
      }
      log.push({ page: path, listings: props.length, new: added, total: all.size })
    } catch (e) { log.push({ page: path, error: String(e) }) }
    await new Promise(r => setTimeout(r, delay))
  }
  const blob = new Blob([JSON.stringify([...all.values()])], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob); a.download = 'wasalt_listings.json'; a.click()
  return log
}

// ---- run ----
const __paths = [];
for (const city of ['riyadh','jeddah','makkah','madinah','dammam','al-khobar','khamis-mushayt'])
  for (const kind of ['properties','apartments','villas'])
    for (const p of ['sale','rent']) __paths.push(`/en/${kind}-for-${p}-in-${city}`);
console.table(await window.__dcCollect(__paths));
