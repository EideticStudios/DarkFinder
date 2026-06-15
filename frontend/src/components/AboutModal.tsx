import { useEffect, useRef, type ReactNode } from 'react'
import { BORTLE_SCALE } from '../lib/bortleScale'
import { INTRO_DESCRIPTION } from '../lib/copy'
import styles from './AboutModal.module.css'

type AboutModalProps = {
  onClose: () => void
}

const GITHUB_URL = 'https://github.com/samrichards/dark-finder'

// Reference links, attached to each term the first time it appears in the copy.
const LINKS = {
  viirs: 'https://en.wikipedia.org/wiki/Visible_Infrared_Imaging_Radiometer_Suite',
  eog: 'https://eogdata.mines.edu/',
  earthEngine: 'https://earthengine.google.com/',
  blackMarble: 'https://blackmarble.gsfc.nasa.gov/',
  bortle: 'https://en.wikipedia.org/wiki/Bortle_scale',
  falchiGarstang: 'https://www.science.org/doi/10.1126/sciadv.1600377',
  cog: 'https://www.cogeo.org/',
  maplibre: 'https://maplibre.org/',
  cartoDarkMatter: 'https://carto.com/basemaps',
  react: 'https://react.dev/',
  vite: 'https://vite.dev/',
  fastapi: 'https://fastapi.tiangolo.com/',
  rioTiler: 'https://cogeotiff.github.io/rio-tiler/',
  scipy: 'https://scipy.org/',
} as const

function Ref({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={styles.link}>
      {children}
    </a>
  )
}

// The opening paragraph is shared verbatim with the intro modal (kept DRY via
// INTRO_DESCRIPTION), so we splice the NASA VIIRS link in around the phrase
// rather than duplicating the sentence.
const [introBeforeViirs, introAfterViirs] = INTRO_DESCRIPTION.split('NASA VIIRS')

export default function AboutModal({ onClose }: AboutModalProps) {
  const closeRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    closeRef.current?.focus()

    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [onClose])

  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        className={styles.modal}
        role="dialog"
        aria-modal="true"
        aria-labelledby="about-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.glow} aria-hidden="true" />
        <button
          ref={closeRef}
          type="button"
          className={styles.closeButton}
          onClick={onClose}
          aria-label="Close"
        >
          ×
        </button>

        <h2 id="about-title" className={styles.title}>
          How DarkFinder works
        </h2>

        <section className={styles.section}>
          <p className={styles.text}>
            {introBeforeViirs}
            <Ref href={LINKS.viirs}>NASA VIIRS</Ref>
            {introAfterViirs}
          </p>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Data sources</h3>
          <p className={styles.text}>
            The map is built from VIIRS VNL V2.2, the 2023 annual nighttime-lights composite
            produced by the <Ref href={LINKS.eog}>Earth Observation Group</Ref> at the Colorado
            School of Mines and accessed through{' '}
            <Ref href={LINKS.earthEngine}>Google Earth Engine</Ref>. It's the cloud-free,
            moonlight-corrected product, so each pixel reflects steady year-round upward radiance
            rather than transient weather. Values are calibrated radiance in nW/cm²/sr at roughly
            500 meter (15 arc-second) resolution, and the dataset is public domain.
          </p>
          <p className={styles.text}>
            If the live data server is unreachable, the client falls back to NASA's pre-rendered{' '}
            <Ref href={LINKS.blackMarble}>Black Marble tiles</Ref> (2016) so the map still renders.
          </p>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Sky Glow and Emission</h3>
          <p className={styles.text}>
            DarkFinder renders the same area two ways, switchable from the toggle at the top.
          </p>
          <p className={styles.text}>
            Emission is the raw upward radiance: the light leaving streetlights, buildings, and
            everything else shining straight up. It maps where light is actually being produced.
          </p>
          <p className={styles.text}>
            Sky Glow models what that light does next. Photons scatter through the atmosphere and
            brighten the sky for up to a hundred kilometers around their source, which is why a
            city washes out the stars long before you reach its streetlights. If you're hunting
            for a genuinely dark site, this is the view that matters, which is why I've set it as
            the default one.
          </p>
          <p className={styles.text}>
            Sky Glow is derived from the Emission layer by spreading each source's light outward
            and summing the contributions: nearby sources dominate, and their influence decays to
            zero by roughly a hundred kilometers. The falloff follows the established{' '}
            <Ref href={LINKS.falchiGarstang}>Falchi/Garstang model</Ref>, so the result
            approximates the artificial sky brightness an observer on the ground would actually
            see.
          </p>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>About the Bortle scale</h3>
          <p className={styles.text}>
            The <Ref href={LINKS.bortle}>Bortle scale</Ref> is a nine-step classification of
            night-sky darkness, running from Class&nbsp;1, the pristine skies you only find well
            away from any city, to Class&nbsp;9, the orange haze over a downtown. DarkFinder bins
            each pixel's radiance into one of those nine classes and colors it accordingly. It's a
            satellite-derived proxy rather than a ground-based sky-quality (SQM) reading, but it
            tracks real-world darkness closely enough to be a reliable guide to where the dark
            skies are.
          </p>
          <ul className={styles.scale}>
            {BORTLE_SCALE.map((entry) => (
              <li key={entry.class} className={styles.scaleRow}>
                <span className={styles.swatch} style={{ background: entry.color }} />
                <span className={styles.scaleLabel}>
                  <strong>{entry.label}</strong> · {entry.description}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>Technical specs</h3>
          <p className={styles.text}>
            DarkFinder has a <Ref href={LINKS.react}>React</Ref> and TypeScript frontend, built
            with <Ref href={LINKS.vite}>Vite</Ref>, and a Python{' '}
            <Ref href={LINKS.fastapi}>FastAPI</Ref> backend. The source data is the global VIIRS
            VNL V2.2 annual composite, which the pipeline reprojects and repackages into a{' '}
            <Ref href={LINKS.cog}>Cloud-Optimized GeoTIFF</Ref> (COG) with internal tiling and
            overviews, so any zoom level can be served from a few HTTP byte-range reads rather
            than loading the full multi-gigabyte raster.
          </p>
          <p className={styles.text}>
            Tiles are rendered on demand.
             An endpoint (<code>/tiles/{'{year}'}/{'{z}'}/{'{x}'}/{'{y}'}.png</code>) uses{' '}
            <Ref href={LINKS.rioTiler}>rio-tiler</Ref> to read the matching window from the COG,
            applies the Bortle color ramp, and returns a PNG. The Sky Glow layer is the one heavy
            computation, so it's precomputed offline by convolving the emission raster with a
            Falchi/Garstang distance-falloff kernel (<Ref href={LINKS.scipy}>SciPy</Ref>),
            processed in latitude bands to keep the kernel physically correct as longitudinal
            scale shrinks toward the poles, then written out as its own COG served through the
            same path.
          </p>
          <p className={styles.text}>
            In the browser, <Ref href={LINKS.maplibre}>MapLibre GL JS</Ref> composites three
            layers: <Ref href={LINKS.cartoDarkMatter}>Carto Dark Matter</Ref> base tiles
            underneath, the VIIRS raster in the middle, and Carto's label-only tiles on top so
            place names stay legible above the glow. The whole project is open source.
          </p>
        </section>

        <a
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.githubLink}
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0016 8c0-4.42-3.58-8-8-8z" />
          </svg>
          View the project on GitHub
        </a>
      </div>
    </div>
  )
}
