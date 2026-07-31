import { describe, expect, it } from 'vitest'

import { getTrainingRecordErrorMessage } from './TrainingRecordClient.logic'

describe('getTrainingRecordErrorMessage', () => {
  it('preserves a safe Error message', () => {
    expect(
      getTrainingRecordErrorMessage(new Error('服务暂不可用'), '导出失败'),
    ).toBe('服务暂不可用')
  })

  it('uses the fallback for unknown rejection values', () => {
    expect(getTrainingRecordErrorMessage({ detail: 'internal' }, '导出失败')).toBe(
      '导出失败',
    )
  })
})
