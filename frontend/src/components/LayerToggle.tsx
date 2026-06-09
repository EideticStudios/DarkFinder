import { LAYERS, type LayerId } from '../lib/layers'
import styles from './LayerToggle.module.css'

interface LayerToggleProps {
  layer: LayerId
  onChange: (layer: LayerId) => void
  skyglowAvailable: boolean
}

export default function LayerToggle({ layer, onChange, skyglowAvailable }: LayerToggleProps) {
  return (
    <div className={styles.wrapper}>
      {LAYERS.map((l) => {
        const disabled = l.id === 'skyglow' && !skyglowAvailable
        return (
          <button
            key={l.id}
            className={`${styles.button} ${layer === l.id ? styles.active : ''}`}
            disabled={disabled}
            onClick={() => onChange(l.id)}
            title={disabled ? 'Sky glow not available for this year' : l.label}
          >
            {l.label}
          </button>
        )
      })}
    </div>
  )
}
