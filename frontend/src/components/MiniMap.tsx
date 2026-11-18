import L from 'leaflet'
import { MapContainer, Marker, Popup, TileLayer } from 'react-leaflet'
import type { ListingCard } from '../lib/api'
import { money } from '../lib/api'

const pin = L.divIcon({
  className: '',
  html: '<div style="width:14px;height:14px;border-radius:99px;background:linear-gradient(135deg,#f3dfa2,#b8893b);border:2px solid #07070a;box-shadow:0 0 0 4px rgba(212,173,91,.25)"></div>',
  iconSize: [14, 14], iconAnchor: [7, 7],
})

export default function MiniMap({ pins }: { pins: ListingCard[] }) {
  const bounds = L.latLngBounds(pins.map(p => [p.lat!, p.lon!] as [number, number])).pad(0.3)
  return (
    <div className="h-72 overflow-hidden rounded-2xl gold-border">
      <MapContainer bounds={bounds} scrollWheelZoom={false} className="h-full w-full">
        <TileLayer url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; OpenStreetMap &copy; CARTO' />
        {pins.map(p => (
          <Marker key={p.id} position={[p.lat!, p.lon!]} icon={pin}>
            <Popup>
              <a href={p.url} target="_blank" rel="noreferrer" className="block text-xs">
                <b>{money(p.price, p.currency)}</b><br />{p.title}<br /><span style={{ color: '#a8a29e' }}>{p.district}, {p.city}</span>
              </a>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
