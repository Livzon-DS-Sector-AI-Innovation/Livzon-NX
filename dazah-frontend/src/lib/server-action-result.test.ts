import { afterEach, describe, expect, it, vi } from 'vitest'
import { ActionRequestError, serverActionResult, unwrapServerActionResult } from './server-action-result'

afterEach(() => vi.restoreAllMocks())

describe('production Server Action error boundary', () => {
  it('round trips data and public business errors through JSON', async () => {
    expect(unwrapServerActionResult(JSON.parse(JSON.stringify(await serverActionResult('save', async () => ({ count: 2 }))))))
      .toEqual({ count: 2 })
    const result = await serverActionResult('save', async () => { throw new ActionRequestError(403, '未获得当前高风险业务动作授权') })
    expect(result).toEqual({ ok: false, message: '未获得当前高风险业务动作授权' })
    expect(() => unwrapServerActionResult(JSON.parse(JSON.stringify(result)))).toThrow('未获得当前高风险业务动作授权')
  })

  it.each([new ActionRequestError(500, 'private upstream body'), new Error('private token'), new DOMException('private host', 'TimeoutError')])(
    'does not throw or leak unexpected upstream failures: %s', async (error) => {
      const log = vi.spyOn(console, 'error').mockImplementation(() => {})
      const result = await serverActionResult('quality.import', async () => { throw error })
      expect(result).toMatchObject({ ok: false, reference: expect.any(String) })
      expect(JSON.stringify(result)).not.toContain('private')
      expect(JSON.stringify(log.mock.calls)).not.toContain('private')
      expect(() => unwrapServerActionResult(result)).toThrow('错误标识')
    },
  )
})
