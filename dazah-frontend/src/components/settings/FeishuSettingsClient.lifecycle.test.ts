import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const lifecycle = vi.hoisted(() => ({
  effects: [] as Array<() => void | (() => void)>,
  setters: [] as Array<ReturnType<typeof vi.fn>>,
}))

const actions = vi.hoisted(() => ({
  getAgentRuntimeOverview: vi.fn(),
  getLivzonFeishuConfig: vi.fn(),
  getLivzonFeishuGatewayStatus: vi.fn(),
}))

vi.mock('react', async (importOriginal) => {
  const original = await importOriginal<typeof import('react')>()
  return {
    ...original,
    useCallback: vi.fn((callback) => callback),
    useEffect: vi.fn((effect: () => void | (() => void)) => {
      lifecycle.effects.push(effect)
    }),
    useState: vi.fn((initial: unknown) => {
      const setter = vi.fn()
      lifecycle.setters.push(setter)
      return [initial, setter]
    }),
  }
})

vi.mock('antd', () => ({
  Alert: () => null,
  App: { useApp: () => ({ message: { error: vi.fn() } }) },
  Button: () => null,
  Space: () => null,
  Tabs: () => null,
  Typography: { Text: () => null, Title: () => null },
}))

vi.mock('@/actions/settings', () => actions)

import FeishuSettingsClient from './FeishuSettingsClient'

describe('FeishuSettingsClient lifecycle', () => {
  beforeEach(() => {
    lifecycle.effects.length = 0
    lifecycle.setters.length = 0
    vi.clearAllMocks()
    actions.getLivzonFeishuConfig.mockResolvedValue({ tenant_id: 'tenant-a' })
    actions.getLivzonFeishuGatewayStatus.mockResolvedValue({
      gateway: 'connected',
    })
    actions.getAgentRuntimeOverview.mockResolvedValue({ status: 'healthy' })
    vi.stubGlobal('window', {
      setTimeout: (callback: () => void) => {
        callback()
        return 1
      },
      clearTimeout: vi.fn(),
    })
  })

  afterEach(() => vi.unstubAllGlobals())

  it('loads the management overview after mount', async () => {
    const tree = FeishuSettingsClient()

    expect(tree).toBeDefined()
    expect(lifecycle.effects).toHaveLength(1)
    const cleanup = lifecycle.effects[0]()

    await vi.waitFor(() => {
      expect(actions.getLivzonFeishuConfig).toHaveBeenCalledOnce()
      expect(actions.getLivzonFeishuGatewayStatus).toHaveBeenCalledOnce()
      expect(actions.getAgentRuntimeOverview).toHaveBeenCalledOnce()
      expect(lifecycle.setters[1]).toHaveBeenCalledWith({ tenant_id: 'tenant-a' })
      expect(lifecycle.setters[2]).toHaveBeenCalledWith({ gateway: 'connected' })
      expect(lifecycle.setters[3]).toHaveBeenCalledWith({ status: 'healthy' })
      expect(lifecycle.setters[4]).toHaveBeenLastCalledWith(false)
    })

    expect(typeof cleanup).toBe('function')
    cleanup?.()
  })
})
