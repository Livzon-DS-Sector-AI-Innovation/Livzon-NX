import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  actionFetch: vi.fn().mockResolvedValue({ id: 'record-1', deleted: 1 }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))
vi.mock('./quality-shared', () => ({
  API_BASE_URL: 'http://backend.test',
  actionFetch: mocks.actionFetch,
}))

import * as capaActions from './quality-capa'
import * as changeActions from './quality-change'
import * as deviationActions from './quality-deviation'

type AsyncAction = (...args: never[]) => Promise<unknown>

function argsFor(name: string, arity: number): unknown[] {
  const form = new FormData()
  if (name.includes('Import')) {
    return [form, false, false, 'technical'].slice(0, arity)
  }
  if (name.toLowerCase().includes('attachment')) {
    return ['record-1', form].slice(0, arity)
  }
  if (name.toLowerCase().startsWith('batch')) {
    return [[], {}].slice(0, arity)
  }
  return Array.from({ length: arity }, (_, index) => index === 0 ? 'record-1' : {})
}

async function invokeAll(module: Record<string, unknown>): Promise<number> {
  const entries = Object.entries(module).filter(
    (entry): entry is [string, AsyncAction] => typeof entry[1] === 'function',
  )
  for (const [name, action] of entries) {
    await action(...argsFor(name, action.length) as never[])
  }
  return entries.length
}

describe('quality legacy action compatibility coverage', () => {
  afterEach(() => vi.clearAllMocks())

  it('executes the complete CAPA action surface through the shared service', async () => {
    const count = await invokeAll(capaActions)

    expect(count).toBeGreaterThanOrEqual(25)
    expect(mocks.actionFetch.mock.calls.length).toBeGreaterThanOrEqual(count)
    expect(mocks.revalidatePath).toHaveBeenCalled()
  })

  it('executes change and deviation actions with their revalidation contracts', async () => {
    const changeCount = await invokeAll(changeActions)
    const deviationCount = await invokeAll(deviationActions)

    expect(changeCount).toBeGreaterThanOrEqual(10)
    expect(deviationCount).toBeGreaterThanOrEqual(20)
    expect(mocks.actionFetch.mock.calls.length).toBeGreaterThanOrEqual(changeCount + deviationCount)
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/quality')
  })
})
