import { useTheme } from '../../hooks/useTheme'

const ICON = {
  light: 'bi-sun',
  dark: 'bi-moon-stars',
  system: 'bi-circle-half',
} as const

const LABEL = {
  light: 'Light theme',
  dark: 'Dark theme',
  system: 'Match system theme',
} as const

const NEXT = {
  light: 'dark',
  dark: 'system',
  system: 'light',
} as const

/** Cycles light -> dark -> follow system. */
export function ThemeToggle() {
  const { preference, cycleTheme } = useTheme()

  return (
    <button
      type="button"
      className="app-iconbtn"
      onClick={cycleTheme}
      aria-label={`${LABEL[preference]}. Switch to ${LABEL[NEXT[preference]].toLowerCase()}`}
      title={`${LABEL[preference]} — click for ${LABEL[NEXT[preference]].toLowerCase()}`}
    >
      <i className={`bi ${ICON[preference]}`} aria-hidden="true" />
    </button>
  )
}
