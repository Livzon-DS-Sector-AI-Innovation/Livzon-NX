import { describe, expect, it } from 'vitest'
import { getFeishuMappedMenuTarget, getFeishuModuleDefinition } from './feishu-data-source'

describe('native energy pages remain independent of archived Wiki mappings', () => {
  it.each(['/energy', '/energy/entry', '/energy/reports', '/energy/analysis', '/energy/data-quality', '/energy/settings', '/energy/sources', '/energy/data', '/energy/sync-runs'])(
    'does not gate %s on a mapped sheet lookup', path => {
      expect(getFeishuMappedMenuTarget('energy', path, new URLSearchParams('source=feishu&task=example'))).toBeUndefined()
    },
  )
  it('does not offer native reporting pages as spreadsheet mapping targets', () => {
    const energyPages = getFeishuModuleDefinition('energy').pages
    expect(energyPages.some(page => page.value === 'energy.drinking_water')).toBe(true)
    expect(energyPages.every(page => page.label.startsWith('历史来源 / '))).toBe(true)
  })
})
