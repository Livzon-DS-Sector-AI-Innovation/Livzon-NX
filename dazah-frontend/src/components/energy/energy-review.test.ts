import { expect, it } from 'vitest'
import { reviewDetails, sourceComparisonDetails } from './energy-review'

it('retains zero, original values and reasons without accepting malformed evidence', () => {
  expect(reviewDetails(null)).toEqual([])
  expect(reviewDetails({ review: [null, 'bad', { reason: 1 }] })).toEqual([])
  expect(reviewDetails({ review: [{ reason: '底码跳变', source: '飞书N31', reported_value: '28674' }, { reason: '需确认', reported_value: '0' }] })).toEqual([
    { reason: '底码跳变', source: '飞书N31', reportedValue: '28674' }, { reason: '需确认', source: '', reportedValue: '0' },
  ])
})

it('validates source comparisons and preserves a reported zero and signed difference', () => {
  expect(sourceComparisonDetails({ source_comparison: { reported_value: '0', difference: '-50000', calculation_status: 'complete', source: '日用量!H33' } })).toEqual({ reportedValue: '0', difference: '-50000', calculationStatus: 'complete', source: '日用量!H33' })
  for (const value of [null, {}, { source_comparison: [] }, { source_comparison: { reported_value: 'NaN' } }]) expect(sourceComparisonDetails(value)).toBeNull()
})
