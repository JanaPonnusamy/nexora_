import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeThemePreference, resolveTheme, THEME_PREFERENCES } from './theme.js';

test('theme preferences are dark, light, and system', () => {
  assert.deepEqual(THEME_PREFERENCES, ['dark', 'light', 'system']);
});

test('a missing preference defaults to dark and a saved choice is kept', () => {
  assert.equal(normalizeThemePreference(undefined), 'dark');
  assert.equal(normalizeThemePreference(''), 'dark');
  assert.equal(normalizeThemePreference('light'), 'light');
  assert.equal(normalizeThemePreference('dark'), 'dark');
  assert.equal(normalizeThemePreference('system'), 'system');
});

test('system follows the operating system and an explicit choice does not', () => {
  assert.equal(resolveTheme('system', true), 'dark');
  assert.equal(resolveTheme('system', false), 'light');
  assert.equal(resolveTheme('light', true), 'light');
  assert.equal(resolveTheme('dark', false), 'dark');
});
