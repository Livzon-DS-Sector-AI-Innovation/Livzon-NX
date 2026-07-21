export const ENERGY_SOURCES_UPDATED_EVENT = 'energy-sources-updated'

export function notifyEnergySourcesUpdated() {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(ENERGY_SOURCES_UPDATED_EVENT))
  }
}
