import styles from './Footer.module.css'

export default function Footer() {
  return (
    <div className={styles.footer}>
      © Eidetic Studios 2026 ·{' '}
      <span className={styles.noWrap}>
        ©{' '}
        <a
          className={styles.link}
          href="https://carto.com/attributions/"
          target="_blank"
          rel="noreferrer"
        >
          CARTO
        </a>
      </span>{' '}
      ·{' '}
      <span className={styles.noWrap}>
        ©{' '}
        <a
          className={styles.link}
          href="https://www.openstreetmap.org/copyright"
          target="_blank"
          rel="noreferrer"
        >
          OpenStreetMap
        </a>
      </span>{' '}
      contributors
    </div>
  )
}
