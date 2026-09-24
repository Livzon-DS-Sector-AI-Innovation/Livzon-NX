/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import type { ProjectLedgerSheetDetail } from '@/types/registration'

vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh: vi.fn() }) }))

import ProjectLedgerSheetPage from './ProjectLedgerSheetPage'

let root: Root
let container: HTMLElement

beforeEach(() => {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})

afterEach(() => {
  act(() => root.unmount())
  container.remove()
})

it('opens the new ledger entry form with usable fields and drawer width', () => {
  const detail = {
    sheet_key: 'project-test',
    sheet_name: '申报台账测试表',
    title: '申报台账测试表',
    summary: {
      sheet_key: 'project-test', sheet_name: '申报台账测试表', title: '申报台账测试表',
      total_records: 0, records_with_history: 0, total_history_versions: 0,
    },
    columns: [{ key: 'sequence', label: '序号' }, { key: 'project', label: '项目名称' }],
    records: [],
  } satisfies ProjectLedgerSheetDetail
  act(() => root.render(<App><ProjectLedgerSheetPage detail={detail} /></App>))

  const createButton = [...container.querySelectorAll('button')].find((button) => button.textContent?.includes('新增主记录'))
  expect(createButton).toBeTruthy()
  act(() => createButton?.click())

  const drawer = document.body.querySelector('.ant-drawer-content-wrapper')
  expect(drawer?.getAttribute('style')).toContain('width: 560px')
  expect(drawer?.textContent).toContain('新增申报台账主记录')
  expect(drawer?.querySelectorAll('input')).toHaveLength(2)
})
