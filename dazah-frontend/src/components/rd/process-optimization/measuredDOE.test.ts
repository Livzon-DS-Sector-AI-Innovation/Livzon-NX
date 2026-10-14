import { describe, expect, it } from 'vitest'
import type { DOEFactor, DOEResponse, DOERun } from '@/types/rd'
import { buildMeasuredDOEOption, completeMeasuredRuns } from './measuredDOE'

const factors: DOEFactor[] = [
  { name: '温度', symbol: 'T', type: 'numeric', levels: { lower: 20, upper: 80 }, unit: '℃' },
  { name: '时间', symbol: 't', type: 'numeric', levels: { lower: 0, upper: 6 }, unit: 'h' },
]
const responses: DOEResponse[] = [{ name: '收率', unit: '%', target: 'maximize', weight: 100 }]
const run = (overrides: Partial<DOERun> = {}): DOERun => ({ run_no: 1, status: 'completed', factor_values: { T: 60, t: 0 }, response_values: { 收率: 0 }, ...overrides })

describe('measured DOE', () => {
  it('plots exact recorded values including zero, with units and experiment identity', () => {
    const runs = [run(), run({ run_no: 2, factor_values: { T: 75, t: 4 }, response_values: { 收率: 93.5 } })]
    const original = JSON.stringify(runs)
    const option = buildMeasuredDOEOption(factors, responses, runs)
    expect(option?.series[0]).toMatchObject({ type: 'scatter3D', data: [{ name: '实验 1', value: [60, 0, 0] }, { name: '实验 2', value: [75, 4, 93.5] }] })
    expect(option?.zAxis3D.name).toBe('收率（%）')
    expect(buildMeasuredDOEOption(factors, responses, runs)).toEqual(option)
    expect(JSON.stringify(runs)).toBe(original)
  })
  it('excludes missing, non-finite, failed and planned measurements without inventing zeros', () => {
    const invalid = [run({ status: 'planned' }), run({ status: 'failed' }), run({ response_values: {} }), run({ response_values: { 收率: NaN } }), run({ factor_values: { T: Infinity, t: 4 } })]
    expect(buildMeasuredDOEOption(factors, responses, invalid)).toBeNull()
    expect(completeMeasuredRuns(factors, responses, invalid)).toEqual([])
    expect(completeMeasuredRuns(factors, responses, [run()])).toHaveLength(1)
  })
  it('switches the response and requires all responses for completion', () => {
    const multiple = [...responses, { name: '纯度', unit: '%', target: 'maximize' as const, weight: 50 }]
    const runs = [run({ response_values: { 收率: 92, 纯度: 99.5 } })]
    expect(buildMeasuredDOEOption(factors, multiple, runs, '纯度')?.series[0].data[0].value).toEqual([60, 0, 99.5])
    expect(completeMeasuredRuns(factors, multiple, [run()])).toEqual([])
    expect(completeMeasuredRuns(factors, multiple, runs)).toHaveLength(1)
    expect(buildMeasuredDOEOption(factors.slice(0, 1), multiple, runs)).toBeNull()
  })
})
