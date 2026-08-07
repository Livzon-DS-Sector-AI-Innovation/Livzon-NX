import { describe, expect, it } from 'vitest'

import { canTightenTenantMemoryPolicy, modeLabels } from './MemoryGovernanceClient'
import { agentManagementTabKeys } from './FeishuSettingsClient'

describe('MemoryGovernanceClient contracts', () => {
  it('uses the governed memory modes exposed by the backend contract', () => {
    expect(modeLabels).toEqual({
      auto: '自动记忆',
      explicit_only: '仅显式记忆',
      disabled: '禁用记忆',
    })
  })

  it('is embedded in capability policies instead of using a separate tab', () => {
    expect(agentManagementTabKeys).not.toContain('memory')
    expect(agentManagementTabKeys).toContain('tools')
  })

  it('allows only equal or stricter tenant policies', () => {
    expect(canTightenTenantMemoryPolicy('auto', 'explicit_only')).toBe(true)
    expect(canTightenTenantMemoryPolicy('explicit_only', 'disabled')).toBe(true)
    expect(canTightenTenantMemoryPolicy('disabled', 'auto')).toBe(false)
  })
})
