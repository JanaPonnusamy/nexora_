import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  normalizeThemePreference,
  resolveTheme,
  DEFAULT_THEME_PREFERENCE,
  THEME_IDS,
  variablesForTheme,
  nativeThemeSource,
  themeById,
} from '../src/themes/themeLogic.js';

test('normalizeThemePreference accepts the five glass themes and system', () => {
  for (const id of THEME_IDS) {
    assert.equal(normalizeThemePreference(id), id);
  }
  assert.equal(normalizeThemePreference('system'), 'system');
});

test('normalizeThemePreference maps the legacy toggle and rejects unknown values', () => {
  assert.equal(normalizeThemePreference('dark'), 'midnight-glass');
  assert.equal(normalizeThemePreference('light'), 'arctic-glass');
  assert.equal(normalizeThemePreference('neon'), DEFAULT_THEME_PREFERENCE);
  assert.equal(normalizeThemePreference(undefined), DEFAULT_THEME_PREFERENCE);
  assert.equal(normalizeThemePreference(null), DEFAULT_THEME_PREFERENCE);
});

test('resolveTheme passes an explicit theme through', () => {
  assert.equal(resolveTheme('ocean-blue', true), 'ocean-blue');
  assert.equal(resolveTheme('aurora-light', false), 'aurora-light');
});

test('resolveTheme resolves system from prefersLight', () => {
  assert.equal(resolveTheme('system', true), 'arctic-glass');
  assert.equal(resolveTheme('system', false), 'midnight-glass');
});

test('default theme is Midnight Glass', () => {
  assert.equal(DEFAULT_THEME_PREFERENCE, 'midnight-glass');
  assert.equal(themeById(DEFAULT_THEME_PREFERENCE).mode, 'dark');
});

test('every theme exposes the shared accent tokens and a near-solid table surface', () => {
  for (const id of THEME_IDS) {
    const vars = variablesForTheme(id);
    assert.ok(vars['--ntm-accent']);
    assert.ok(vars['--ntm-table-bg']);
    assert.ok(vars['--nx-accent']);
    assert.equal(vars['--bs-primary'], vars['--ntm-accent']);
    assert.equal(vars['--bs-table-bg'], vars['--ntm-table-bg']);
  }
  assert.equal(variablesForTheme('midnight-glass')['--ntm-accent'], '#2563EB');
  assert.equal(themeById('arctic-glass').mode, 'light');
  assert.equal(themeById('aurora-light').mode, 'light');
  assert.equal(nativeThemeSource('graphite-pro'), 'dark');
  assert.equal(nativeThemeSource('arctic-glass'), 'light');
  assert.equal(nativeThemeSource('system'), 'system');
});
