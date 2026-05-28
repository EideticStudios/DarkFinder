import styles from './YearSelector.module.css'

interface YearSelectorProps {
  year: number
  years: number[]
  onChange: (year: number) => void
}

export default function YearSelector({ year, years, onChange }: YearSelectorProps) {
  if (years.length === 0) return null

  return (
    <div className={styles.wrapper}>
      <span className={styles.label}>Year</span>
      <select
        className={styles.select}
        value={year}
        onChange={(e) => onChange(Number(e.target.value))}
      >
        {years.map((y) => (
          <option key={y} value={y}>{y}</option>
        ))}
      </select>
    </div>
  )
}
