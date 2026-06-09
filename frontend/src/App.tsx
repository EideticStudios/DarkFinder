import { useEffect, useState } from 'react'
import Map from './components/Map'
import BortleLegend from './components/BortleLegend'
import SkyglowLegend from './components/SkyglowLegend'
import YearSelector from './components/YearSelector'
import LayerToggle from './components/LayerToggle'
import type { LayerId } from './lib/layers'
import './App.css'

const API_BASE = 'http://localhost:8000/api/v1'
const DEFAULT_YEAR = 2023

export default function App() {
  const [year, setYear] = useState<number>(DEFAULT_YEAR)
  const [availableYears, setAvailableYears] = useState<number[]>([])
  const [skyglowYears, setSkyglowYears] = useState<number[]>([])
  const [layer, setLayer] = useState<LayerId>('emission')
  const [ready, setReady] = useState(false)

  useEffect(() => {
    fetch(`${API_BASE}/years`)
      .then((r) => r.json())
      .then((data: { years: number[]; skyglow_years?: number[] }) => {
        if (data.years?.length) {
          setAvailableYears(data.years)
          setYear(data.years[data.years.length - 1])
        }
        if (data.skyglow_years?.length) {
          setSkyglowYears(data.skyglow_years)
        }
      })
      .catch(() => {
        // Backend not running — will fall back to GIBS tiles
      })
      .finally(() => setReady(true))
  }, [])

  const skyglowAvailable = skyglowYears.includes(year)

  // Fall back to emission if current year lacks skyglow
  const activeLayer = layer === 'skyglow' && !skyglowAvailable ? 'emission' : layer

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">DarkFinder</h1>
        <YearSelector year={year} years={availableYears} onChange={setYear} />
        <LayerToggle layer={activeLayer} onChange={setLayer} skyglowAvailable={skyglowAvailable} />
        <a
          href="https://github.com/samrichards/dark-finder"
          target="_blank"
          rel="noopener noreferrer"
          className="githubLink"
        >
          GitHub
        </a>
      </header>
      <div className="mapWrapper">
        {ready && <Map year={year} layer={activeLayer} hasData={availableYears.length > 0} />}
        {activeLayer === 'skyglow' ? <SkyglowLegend /> : <BortleLegend />}
      </div>
    </div>
  )
}
