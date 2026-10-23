import { describe, expect, it } from 'vitest'
import { getFeishuMappedMenuTarget, getFeishuModuleDefinition } from './feishu-data-source'

describe('native energy pages remain independent of archived Wiki mappings', () => {
  it.each(['/energy', '/energy/entry', '/energy/reports', '/energy/analysis', '/energy/data-quality', '/energy/settings', '/energy/sources', '/energy/data', '/energy/sync-runs'])(
    'does not gate %s on a mapped sheet lookup', path => {
      expect(getFeishuMappedMenuTarget('energy', path, new URLSearchParams('source=feishu&task=example'))).toBeUndefined()
    },
  )
  it('does not offer retired historical pages as spreadsheet mapping targets', () => {
    expect(getFeishuModuleDefinition('energy').pages).toEqual([])
  })
})
