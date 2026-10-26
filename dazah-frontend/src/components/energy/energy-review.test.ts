import { expect, it } from 'vitest'
import { reviewDetails } from './energy-review'

it('retains zero, original values and reasons without accepting malformed evidence', () => {
  expect(reviewDetails(null)).toEqual([])
  expect(reviewDetails({ review: [null, 'bad', { reason: 1 }] })).toEqual([])
  expect(reviewDetails({ review: [{ reason: '底码跳变', source: '飞书N31', reported_value: '28674' }, { reason: '需确认', reported_value: '0' }] })).toEqual([
    { reason: '底码跳变', source: '飞书N31', reportedValue: '28674' }, { reason: '需确认', source: '', reportedValue: '0' },
  ])
})
