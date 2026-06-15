import { useEffect, useState } from 'react'
import Map from './components/Map'
import BortleLegend from './components/BortleLegend'
import EmissionLegend from './components/EmissionLegend'
import LayerToggle from './components/LayerToggle'
import IntroModal from './components/IntroModal'
import AboutModal from './components/AboutModal'
import Footer from './components/Footer'
import type { LayerId } from './lib/layers'
import { API_BASE } from './lib/api'
import './App.css'

const INTRO_SEEN_KEY = 'darkfinder-intro-seen'

export default function App() {
  const [hasData, setHasData] = useState(false)
  const [skyglowAvailable, setSkyglowAvailable] = useState(false)
  const [layer, setLayer] = useState<LayerId>('skyglow')
  const [ready, setReady] = useState(false)
  const [showIntro, setShowIntro] = useState(() => !localStorage.getItem(INTRO_SEEN_KEY))
  const [showAbout, setShowAbout] = useState(false)

  const handleCloseIntro = () => {
    setShowIntro(false)
    localStorage.setItem(INTRO_SEEN_KEY, '1')
  }

  useEffect(() => {
    fetch(`${API_BASE}/layers`)
      .then((r) => r.json())
      .then((data: { emission: boolean; skyglow: boolean }) => {
        if (data.emission) {
          setHasData(true)
          setSkyglowAvailable(data.skyglow)
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
        {ready && <Map layer={activeLayer} hasData={hasData} />}
        {activeLayer === 'skyglow' ? <BortleLegend /> : <EmissionLegend />}
        <Footer />
      </div>
      {showIntro && <IntroModal onClose={handleCloseIntro} />}
      {showAbout && <AboutModal onClose={() => setShowAbout(false)} />}
    </div>
  )
}
