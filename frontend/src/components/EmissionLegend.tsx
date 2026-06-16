import { BORTLE_SCALE } from '../lib/bortleScale'
import styles from './BortleLegend.module.css'

function formatRange(min: number, max: number | null): string {
  if (max === null) return `${min}+`
  return `${min} – ${max}`
}

export default function EmissionLegend({ open = false }: { open?: boolean }) {
  return (
    <div className={`${styles.legend} ${open ? styles.open : ''}`}>
      <h3 className={styles.title}>Radiance</h3>
      <div className={styles.scale}>
        {BORTLE_SCALE.map((entry) => (
          <div key={entry.class} className={styles.row}>
            <span className={styles.swatch} style={{ background: entry.color }} />
            <span className={styles.label}>
              {formatRange(entry.minRadiance, entry.maxRadiance)} nW/cm²/sr
            </span>
          </div>
        ))}
      </div>
      <p className={styles.attribution}>NASA Black Marble VIIRS</p>
    </div>
  )
}
