import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  actionFetch: vi.fn().mockResolvedValue({ id: 'record-1' }),
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))
vi.mock('./quality-shared', () => ({
  API_BASE_URL: 'http://backend.test',
  actionFetch: mocks.actionFetch,
}))

import {
  aiExtractHistoricalDeviation,
  analyzeDeviationWorkbench,
  createHistoricalDeviation,
  deleteDeviationWorkbenchReport,
  deleteHistoricalDeviation,
  deleteHistoricalDeviationAttachment,
  updateDeviationWorkbenchSettings,
  updateHistoricalDeviation,
  uploadDeviationWorkbenchAttachment,
  uploadHistoricalDeviationAttachment,
} from './quality-deviation-workbench'

describe('quality deviation workbench server actions', () => {
  afterEach(() => vi.clearAllMocks())

  it('keeps historical deviation CRUD on the right endpoints', async () => {
    await createHistoricalDeviation({ deviation_event: '灌装压塞压力超上限' })
    await updateHistoricalDeviation('record-1', { root_cause: '未定期校准' })
    await deleteHistoricalDeviation('record-1')

    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/quality/historical-deviations',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/quality/historical-deviations/record-1',
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      3,
      'http://backend.test/api/v1/quality/historical-deviations/record-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('routes attachment upload/delete and ai-extract for historical deviations', async () => {
    await uploadHistoricalDeviationAttachment('record-1', new FormData())
    await deleteHistoricalDeviationAttachment('record-1', 'attach-1')
    await aiExtractHistoricalDeviation('record-1')

    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/quality/historical-deviations/record-1/attachments',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/quality/historical-deviations/record-1/attachments/attach-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      3,
      'http://backend.test/api/v1/quality/historical-deviations/record-1/ai-extract',
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('routes workbench settings, attachment, analyze and report delete', async () => {
    await updateDeviationWorkbenchSettings('从 5M1E 分析')
    await uploadDeviationWorkbenchAttachment(new FormData())
    await analyzeDeviationWorkbench({
      source_type: 'manual',
      manual_text: '灌装压塞压力超上限',
      attachments: [],
    })
    await deleteDeviationWorkbenchReport('report-1')

    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      1,
      'http://backend.test/api/v1/quality/deviation-workbench/settings',
      expect.objectContaining({ method: 'PUT' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      2,
      'http://backend.test/api/v1/quality/deviation-workbench/attachments',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      3,
      'http://backend.test/api/v1/quality/deviation-workbench/analyze',
      expect.objectContaining({ method: 'POST' }),
    )
    expect(mocks.actionFetch).toHaveBeenNthCalledWith(
      4,
      'http://backend.test/api/v1/quality/deviation-workbench/reports/report-1',
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('revalidates the new deviation sub-pages after writes', async () => {
    await createHistoricalDeviation({})
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/quality/deviations/history')
    expect(mocks.revalidatePath).toHaveBeenCalledWith('/quality/deviations/workbench')
  })
})
