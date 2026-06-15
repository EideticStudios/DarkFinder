import { useEffect, useState } from 'react'
import Map from './components/Map'
import BortleLegend from './components/BortleLegend'
import EmissionLegend from './components/EmissionLegend'
import LayerToggle from './components/LayerToggle'
import IntroModal from './components/IntroModal'
import AboutModal from './components/AboutModal'
import Footer from './components/Footer'
import type { LayerId } from './lib/layers'
import './App.css'

const API_BASE = 'http://localhost:8000/api/v1'
const DEFAULT_YEAR = 2023
const INTRO_SEEN_KEY = 'darkfinder-intro-seen'

export default function App() {
  const [year, setYear] = useState<number>(DEFAULT_YEAR)
  const [hasData, setHasData] = useState(false)
  const [skyglowAvailable, setSkyglowAvailable] = useState(false)
  const [layer, setLayer] = useState<LayerId>('skyglow')
  const [ready, setReady] = useState(false)
  const [showIntro, setShowIntro] = useState(false)
  const [showAbout, setShowAbout] = useState(false)

  useEffect(() => {
    if (!localStorage.getItem(INTRO_SEEN_KEY)) {
      setShowIntro(true)
    }
  }, [])

  const handleCloseIntro = () => {
    setShowIntro(false)
    localStorage.setItem(INTRO_SEEN_KEY, '1')
  }

  useEffect(() => {
    fetch(`${API_BASE}/years`)
      .then((r) => r.json())
      .then((data: { years: number[]; skyglow_years?: number[] }) => {
        if (data.years?.length) {
          const latestYear = data.years[data.years.length - 1]
          setYear(latestYear)
          setHasData(true)
          setSkyglowAvailable(data.skyglow_years?.includes(latestYear) ?? false)
        }
      })
      .catch(() => {
        // Backend not running — will fall back to GIBS tiles
      })
      .finally(() => setReady(true))
  }, [])

  // Fall back to emission if skyglow not available
  const activeLayer = layer === 'skyglow' && !skyglowAvailable ? 'emission' : layer

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">DarkFinder</h1>
        <LayerToggle layer={activeLayer} onChange={setLayer} skyglowAvailable={skyglowAvailable} />
        <button type="button" className="aboutButton" onClick={() => setShowAbout(true)}>
          How this works
        </button>
      </header>
      <div className="mapWrapper">
        {ready && <Map year={year} layer={activeLayer} hasData={hasData} />}
        {activeLayer === 'skyglow' ? <BortleLegend /> : <EmissionLegend />}
        <Footer />
      </div>
      {showIntro && <IntroModal onClose={handleCloseIntro} />}
      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}
    </div>
  )
}
