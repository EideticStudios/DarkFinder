import { useEffect, useRef } from 'react'
import { INTRO_DESCRIPTION } from '../lib/copy'
import styles from './IntroModal.module.css'

type IntroModalProps = {
  onClose: () => void
}

export default function IntroModal({ onClose }: IntroModalProps) {
  const ctaRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    ctaRef.current?.focus()

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
        aria-labelledby="intro-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.glow} aria-hidden="true" />
        <h2 id="intro-title" className={styles.title}>
          DarkFinder
        </h2>
        <p className={styles.subtitle}>A free, open-source dark sky mapping project</p>
        <p className={styles.description}>{INTRO_DESCRIPTION}</p>
        <button ref={ctaRef} type="button" className={styles.cta} onClick={onClose}>
          Find dark skies near you!
        </button>
      </div>
    </div>
  )
}
