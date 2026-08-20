import { useTheme } from '../../hooks/useTheme'

/** Toggles between light and dark theme. */
export function ThemeToggle() {
  const { preference, theme, cycleTheme } = useTheme()
  const label = preference === 'system' ? `System (${theme})` : preference === 'dark' ? 'Dark' : 'Light'
  const next = preference === 'light' ? 'dark' : preference === 'dark' ? 'system' : 'light'
  const icon = preference === 'system' ? 'bi-circle-half' : preference === 'dark' ? 'bi-moon-stars' : 'bi-sun'

  return (
    <button
      type="button"
      className="app-iconbtn"
      onClick={cycleTheme}
      aria-label={`${label} theme. Switch to ${next} theme`}
      title={`${label} theme — click for ${next}`}
    >
      <i className={`bi ${icon}`} aria-hidden="true" />
    </button>
  )
}
