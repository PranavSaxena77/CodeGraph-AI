export const THEME_STORAGE_KEY = 'codegraph-theme'
export const THEME_OPTIONS = ['system', 'light', 'dark']

export function getInitialTheme() {
  const savedTheme = window.localStorage.getItem(THEME_STORAGE_KEY)
  return THEME_OPTIONS.includes(savedTheme) ? savedTheme : 'system'
}

export function applyTheme(theme) {
  const resolvedTheme = theme === 'system'
    ? window.matchMedia?.('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
    : theme
  document.documentElement.dataset.theme = resolvedTheme
  document.documentElement.dataset.themePreference = theme
  document.documentElement.style.colorScheme = resolvedTheme
  window.localStorage.setItem(THEME_STORAGE_KEY, theme)
}
