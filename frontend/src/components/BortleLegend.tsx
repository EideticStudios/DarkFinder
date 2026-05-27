import { BORTLE_SCALE } from '../lib/bortleScale'
import styles from './BortleLegend.module.css'

export default function BortleLegend() {
  return (
    <div className={styles.legend}>
      <h3 className={styles.title}>Bortle Scale</h3>
      <div className={styles.scale}>
        {BORTLE_SCALE.map((entry) => (
          <div key={entry.class} className={styles.row}>
            <span className={styles.swatch} style={{ background: entry.color }} />
            <span className={styles.label}>{entry.description}</span>
          </div>
        ))}
      </div>
      <p className={styles.attribution}>NASA Black Marble VIIRS · 2016</p>
    </div>
  )
}
