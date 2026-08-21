/* @vitest-environment happy-dom */
/* eslint-disable @typescript-eslint/no-explicit-any */

import { afterEach, describe, expect, it, vi } from 'vitest'

import TraceModal from './TraceModal'
import { buildLayout } from './TraceModal'

const LAYOUT_STAGES = [
  { stage: 'refinement', label: '精制MC-F2', nodes: [{ batch_no: 'MC-F2-1', yield_rate: 88.5, quantity: 100 }] },
  { stage: 'extraction', label: '萃取批号', nodes: [] },
  { stage: 'sub_tank', label: '钠化批号', nodes: [
    { batch_no: 'MC-1', yield_rate: 90.0, quantity: 100 },
    { batch_no: 'MC-1-b', yield_rate: 85.0, quantity: 30, is_sibling: true, connects_to: 'MC-F2-1' },
  ] },
]

describe('TraceModal buildLayout', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('builds node/line/note layout for a stage graph', () => {
    const cfg: Record<string, { color: string }> = {
      refinement: { color: '#722ed1' }, extract: { color: '#fa8c16' }, sub_tank: { color: '#13c2c2' },
    }
    const layout = buildLayout(LAYOUT_STAGES, 'MC-F2-1', 'refinement', cfg, ['refinement', 'sub_tank'])
    expect(layout.nodes.length).toBeGreaterThan(0)
    expect(layout.lines).toBeInstanceOf(Array)
    expect(layout.notes).toBeInstanceOf(Array)
    // 主节点带目标标记
    const target = layout.nodes.find((n) => n.batch_no === 'MC-F2-1')
    expect(target?.is_target).toBe(true)
    expect(target?.label).toBe('精制MC-F2')
    // 兄弟节点被标记为 sibling，且带汇入连接文字
    const sib = layout.nodes.find((n) => n.batch_no === 'MC-1-b')
    expect(sib?.is_sibling).toBe(true)
    expect(String(sib?.connects_to || '')).toContain('MC-F2-1')
    // 主链节点有定位坐标
    const main = layout.nodes.find((n) => n.batch_no === 'MC-1')
    expect(main).toBeTruthy()
    expect(typeof main?.x).toBe('number')
    expect(typeof main?.y).toBe('number')
  })

  it('returns empty layout when no stages in order match', () => {
    const layout = buildLayout(LAYOUT_STAGES, 'MC-F2-1', 'refinement', { refinement: { color: '#000' } }, ['unknown_stage'])
    expect(layout.nodes).toEqual([])
    expect(layout.lines).toEqual([])
  })
})