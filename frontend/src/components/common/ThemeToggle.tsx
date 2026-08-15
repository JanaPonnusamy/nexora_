import { useTheme } from '../../hooks/useTheme'

/** Toggles between light and dark theme. */
export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      className="app-iconbtn"
      onClick={toggleTheme}
      aria-label={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
      title={isDark ? 'Dark theme — click for light theme' : 'Light theme — click for dark theme'}
    >
      <i className={`bi ${isDark ? 'bi-moon-stars' : 'bi-sun'}`} aria-hidden="true" />
    </button>
  )
}
