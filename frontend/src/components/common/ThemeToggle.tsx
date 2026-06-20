import { useTheme } from '../../hooks/useTheme'

export function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  return (
    <button
      type="button"
      className="btn btn-link app-header__icon-btn"
      onClick={toggleTheme}
      aria-label="Toggle theme"
      title={isDark ? 'Switch to light theme' : 'Switch to dark theme'}
    >
      <i className={`bi ${isDark ? 'bi-sun' : 'bi-moon-stars'}`} aria-hidden="true" />
    </button>
  )
}
