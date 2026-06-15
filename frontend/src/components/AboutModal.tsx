import { useEffect, useRef } from 'react'
import { BORTLE_SCALE } from '../lib/bortleScale'
import styles from './AboutModal.module.css'

type AboutModalProps = {
  onClose: () => void
}

const GITHUB_URL = 'https://github.com/samrichards/dark-finder'

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
        <p className={styles.subtitle}>A free, open-source dark sky mapping project</p>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>What this is</h3>
          <p className={styles.text}>
            DarkFinder turns NASA VIIRS nighttime satellite imagery into an interactive
            light-pollution heat map of the entire planet. Brighter colors mean there's
            more light pollution, while darker ones indicate darker skies — so you can
            find the nearest place to escape the glow and see the stars.
          </p>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>The data</h3>
          <p className={styles.text}>
            The map is built from the <strong>VIIRS VNL V2.2</strong> annual nighttime-lights
            composite for <strong>2023</strong>, produced by the Earth Observation Group at the
            Colorado School of Mines and accessed through Google Earth Engine. It uses the
            cloud- and moonlight-corrected <code>average_masked</code> band at roughly 500&nbsp;m
            (15 arc-second) resolution, with brightness measured in radiance
            (nW/cm²/sr). The dataset is public domain.
          </p>
          <p className={styles.text}>
            If the live data backend isn't reachable, DarkFinder falls back to NASA's
            pre-rendered Black Marble (2016) nighttime imagery so the map still works.
          </p>
        </section>

        <section className={styles.section}>
          <h3 className={styles.sectionTitle}>The Bortle scale</h3>
          <p className={styles.text}>
            The Bortle scale is a nine-step rating of how dark the night sky is, from
            Class&nbsp;1 (pristine skies far from any city) up to Class&nbsp;9 (the washed-out
            glow of an inner city). Here, each satellite radiance value is binned into one of
            those nine classes and drawn in its own color. It's an approximation derived from
            satellite brightness rather than a ground-based sky-quality reading, but it gives a
            reliable picture of where the dark skies are.
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
          <h3 className={styles.sectionTitle}>How it's built</h3>
          <p className={styles.text}>
            Map tiles are rendered on the fly from a cloud-optimized GeoTIFF by a Python
            (FastAPI + rio-tiler) backend, then drawn with MapLibre GL JS over the Carto Dark
            Matter basemap — with place labels layered above the overlay so they stay readable.
            You can switch between the sky-glow view (Bortle classes) and the raw light-emission
            view. The whole project is open source.
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
