import { SKYGLOW_SCALE } from '../lib/skyglowScale'
import styles from './SkyglowLegend.module.css'

const gradient = SKYGLOW_SCALE.map((s) => s.color).join(', ')

export default function SkyglowLegend() {
  return (
    <div className={styles.legend}>
      <h3 className={styles.title}>Sky Glow</h3>
      <div className={styles.bar} style={{ background: `linear-gradient(to right, ${gradient})` }} />
      <div className={styles.labels}>
        <span>{SKYGLOW_SCALE[0].label}</span>
        <span>{SKYGLOW_SCALE[Math.floor(SKYGLOW_SCALE.length / 2)].label} nW</span>
        <span>{SKYGLOW_SCALE[SKYGLOW_SCALE.length - 1].label}</span>
      </div>
      <p className={styles.attribution}>Modeled from VIIRS emission · nW/cm²/sr</p>
    </div>
  )
}
