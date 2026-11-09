/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { ConfigProvider, theme } from 'antd'
import { afterEach, expect, it } from 'vitest'
import type { ImportPreview } from '@/lib/api/energy-ledger'
import { EnergyFieldMappings } from './EnergyFieldMappings'

let root: Root | undefined
afterEach(async () => { await act(async () => root?.unmount()); root = undefined; document.body.innerHTML = '' })

it.each([false, true])('shows September field identity, E column and original formulas (dark=%s)', async dark => {
  const preview: ImportPreview = { id: 'batch', status: 'preview', payload: {
    field_mappings: [
      { business_key: 'air', business_sheet: '102-1车间', business_name: '压缩空气', source_sheet: '102-1车间', source_column: 5, source_column_letter: 'E', source_label: '压缩空气', status: 'mapped', formula_cells: ['E2'] },
      { business_key: 'copy', business_sheet: '冰水码', business_name: '补水', source_sheet: '冰水码', source_column: 27, source_column_letter: 'AA', source_label: '补水', status: 'excluded', reason: '空白分隔区后的字段须核对' },
      { business_key: 'duplicate', business_sheet: '饮用水码', business_name: '103-2车间', source_sheet: '饮用水码', source_column: 3, source_column_letter: 'C', source_label: '103-2车间', status: 'duplicate_label' },
      { business_key: 'unnamed', business_sheet: '饮用水量', business_name: '未命名计算列(F)', source_sheet: '饮用水量', source_column: 6, source_column_letter: 'F', source_label: '', status: 'missing_label' },
    ],
    sheets: [{ name: '102-1车间', source_grid: [['日期', '', '', '', '压缩空气'], ['9/1', null, null, null, '=空气量!D7']] }],
  } }
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<ConfigProvider theme={{ algorithm: dark ? theme.darkAlgorithm : theme.defaultAlgorithm }}><EnergyFieldMappings preview={preview} /></ConfigProvider>))
  const toggle = host.querySelector<HTMLElement>('[role="button"]')!
  await act(async () => toggle.click())
  expect(host.textContent).toContain('102-1车间·压缩空气')
  expect(host.textContent).toContain('102-1车间!E列')
  expect(host.textContent).toContain('冰水码!AA列')
  expect(host.textContent).toContain('不纳入能源指标')
  expect(host.textContent).toContain('同名表计，按原列区分')
  expect(host.textContent).toContain('字段名称待核对')
  await act(async () => host.querySelector<HTMLButtonElement>('.ant-table-row-expand-icon')!.click())
  expect(host.textContent).toContain('E2：=空气量!D7')
})

it.each([null, [], [null, { source_column: -1 }]])('ignores absent or invalid legacy mappings: %s', async mappings => {
  const host = document.createElement('div'); document.body.append(host); root = createRoot(host)
  await act(async () => root?.render(<EnergyFieldMappings preview={{ id: 'legacy', status: 'preview', payload: { field_mappings: mappings } }} />))
  expect(host.textContent).toBe('')
})
