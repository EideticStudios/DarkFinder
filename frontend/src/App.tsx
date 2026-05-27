import Map from './components/Map'
import BortleLegend from './components/BortleLegend'
import './App.css'

export default function App() {
  return (
    <div className="app">
      <header className="header">
        <h1 className="title">DarkFinder</h1>
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
        <Map />
        <BortleLegend />
      </div>
    </div>
  )
}
