import { useEffect, useState } from 'react'
import Map from './components/Map'
import BortleLegend from './components/BortleLegend'
import YearSelector from './components/YearSelector'
import './App.css'

const API_BASE = 'http://localhost:8000/api/v1'
const DEFAULT_YEAR = 2023

export default function App() {
  const [year, setYear] = useState<number>(DEFAULT_YEAR)
  const [availableYears, setAvailableYears] = useState<number[]>([])

  useEffect(() => {
    fetch(`${API_BASE}/years`)
      .then((r) => r.json())
      .then((data: { years: number[] }) => {
        if (data.years?.length) {
          setAvailableYears(data.years)
          setYear(data.years[data.years.length - 1])
        }
      })
      .catch(() => {
        // Backend not running — year selector stays hidden
      })
  }, [])

  return (
    <div className="app">
      <header className="header">
        <h1 className="title">DarkFinder</h1>
        <YearSelector year={year} years={availableYears} onChange={setYear} />
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
        <Map year={year} />
        <BortleLegend />
      </div>
    </div>
  )
}
