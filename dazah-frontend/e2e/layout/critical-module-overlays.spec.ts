import { registerModuleOverlayTests } from '../module-overlays'

for (const moduleName of ['quality', 'registration', 'warehouse', 'hr'] as const) {
  registerModuleOverlayTests(moduleName, 'critical')
}
