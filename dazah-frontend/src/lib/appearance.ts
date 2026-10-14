export type AppearanceMode = 'light' | 'dark' | 'system'
export type ColorMode = 'light' | 'dark'
export const APPEARANCE_STORAGE_KEY = 'dazah-appearance'
export const DARK_MODE_QUERY = '(prefers-color-scheme: dark)'

export function parseAppearance(value: string | null): AppearanceMode {
  return value === 'light' || value === 'dark' ? value : 'system'
}

export function resolveAppearance(mode: AppearanceMode, systemDark: boolean): ColorMode {
  return mode === 'system' ? (systemDark ? 'dark' : 'light') : mode
}

// Runs before the first paint; only a fixed script is injected, never user content.
export const appearanceInitScript = `(() => {
  let mode = 'system';
  try { const saved = localStorage.getItem('${APPEARANCE_STORAGE_KEY}');
    if (saved === 'light' || saved === 'dark') mode = saved;
  } catch {}
  const dark = mode === 'dark' || (mode === 'system' && window.matchMedia('${DARK_MODE_QUERY}').matches);
  document.documentElement.dataset.appearance = mode;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
})();`
