import { readFileSync } from 'node:fs'
import { expect, test } from 'vitest'
import { rootVariables } from './design-system/tokens/theme'

const CSS_FILES = [
  'src/styles/shell.css',
  'src/index.css',
  'src/design-system/styles.css',
  'src/components/mapping/mapping-ui.css',
  // Consumes the --nx-glass-* tokens, so a renamed or dropped glass token
  // fails here rather than silently rendering an unstyled Purchase Workspace.
  'src/components/procurement/purchase-manager.css',
]

function referencedTokens(): Map<string, string[]> {
  const found = new Map<string, string[]>()
  for (const file of CSS_FILES) {
    const css = readFileSync(file, 'utf8')
    for (const match of css.matchAll(/var\((--nx-[a-z0-9-]+)/g)) {
      const list = found.get(match[1]) ?? []
      if (!list.includes(file)) list.push(file)
      found.set(match[1], list)
    }
  }
  return found
}

test('every --nx-* token used in CSS is emitted by theme.ts', () => {
  const emitted = new Set(Object.keys(rootVariables('light')))
  const missing: string[] = []
  for (const [token, files] of referencedTokens()) {
    if (!emitted.has(token)) missing.push(`${token}  (used in ${files.join(', ')})`)
  }
  expect(missing, `Undefined tokens:\n${missing.join('\n')}`).toEqual([])
})

test('light and dark emit an identical set of variables', () => {
  expect(Object.keys(rootVariables('dark')).sort()).toEqual(
    Object.keys(rootVariables('light')).sort(),
  )
})

test('no token resolves to an empty or undefined value', () => {
  for (const name of ['light', 'dark'] as const) {
    for (const [key, value] of Object.entries(rootVariables(name))) {
      expect(value, `${name}: ${key}`).toBeTruthy()
    }
  }
})

test('themes actually differ — dark is not a copy of light', () => {
  const light = rootVariables('light')
  const dark = rootVariables('dark')
  const changed = Object.keys(light).filter((key) => light[key] !== dark[key])
  expect(changed.length).toBeGreaterThan(30)
})
