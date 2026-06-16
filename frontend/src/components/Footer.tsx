import styles from './Footer.module.css'

export default function Footer() {
  return (
    <div className={styles.footer}>
      © Eidetic Studios 2026 · © CARTO ·{' '}
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
