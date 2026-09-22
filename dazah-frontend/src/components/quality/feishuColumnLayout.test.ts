import { expect, it, vi } from 'vitest'
import { alignFeishuColumns, feishuColumnLayouts } from './feishuColumnLayout'
import { personSelectValue } from './qualityPersonSelection'

it('moves CAPA list-only fields out of the list without deleting their definitions or callbacks', () => {
  const detail = vi.fn()
  const plan = vi.fn()
  const columns = [
    { key: 'code', title: 'CAPA编号', width: 100 },
    { key: 'source', title: '来源编号', dataIndex: 'source_code' },
    { key: 'plan_count', title: '计划数', render: plan },
    { key: 'title', title: 'CAPA简述', render: detail },
    { key: 'action', title: '操作', fixed: 'right' as const, render: detail },
  ]
  const visible = alignFeishuColumns(columns, feishuColumnLayouts.capaLedger)
  expect(visible.map(column => column.title)).toEqual(['CAPA编号', 'CAPA简述', '操作'])
  expect(visible[1]).toBe(columns[3])
  expect(visible[2]).toBe(columns[4])
  expect(columns[2].render).toBe(plan)
  expect(columns[1].dataIndex).toBe('source_code')
})

it('renames and reorders CAPA due date without replacing the original date or person renderer', () => {
  const date = vi.fn()
  const person = vi.fn()
  const columns = [{ title: '责任人', key: 'owner', render: person }, { title: '完成时间', key: 'due_date', render: date, width: 130 }]
  const visible = alignFeishuColumns(columns, feishuColumnLayouts.capaPlan, { due_date: '预计完成时间' })
  expect(visible.map(column => column.title)).toEqual(['预计完成时间', '责任人'])
  expect(visible[0]).toMatchObject({ key: 'due_date', render: date, width: 130 })
  expect(visible[1]).toBe(columns[0])
})

it('does not guess between people with the same name or lose historical names', () => {
  const contacts = [{ name: '同名', department: 'QA', open_id: 'ou_1' }, { name: '同名', department: 'QC', open_id: 'ou_2' }]
  expect(personSelectValue(contacts, '同名', 'QC')).toBe('ou_2')
  expect(personSelectValue(contacts, '同名')).toBe('同名')
  expect(personSelectValue(contacts, '离职人员')).toBe('离职人员')
})
