/* @vitest-environment happy-dom */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import PositionTrainingListClient from './PositionTrainingListClient'

const flags = vi.hoisted(() => ({
  canOperate: false,
  canDelete: false,
  canImport: false,
  canExport: false,
}))

vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => flags }))
vi.mock('@/lib/api/client/hr', () => ({
  fetchPositionTrainingLists: vi.fn(),
  fetchTrainingDepartments: vi.fn(),
}))
vi.mock('@/actions/hr', () => ({
  createPositionTrainingList: vi.fn(),
  batchUpdatePositionTrainingListItems: vi.fn(),
  importPositionTrainingLists: vi.fn(),
  clearPositionTrainingListsByDept: vi.fn(),
}))

function buttons() {
  const client = new QueryClient()
  const container = document.createElement('div')
  container.innerHTML = renderToStaticMarkup(
    <QueryClientProvider client={client}>
      <PositionTrainingListClient />
    </QueryClientProvider>,
  )
  client.clear()
  return (label: string) => Array.from(container.querySelectorAll('button')).find(
    (button) => button.textContent?.replace(/\s/g, '') === label,
  )
}

describe('position training page permissions', () => {
  it('keeps sensitive actions separate from ordinary editing', () => {
    Object.assign(flags, {
      canOperate: true,
      canDelete: false,
      canImport: false,
      canExport: false,
    })
    const button = buttons()
    expect(button('新增明细')?.disabled).toBe(false)
    expect(button('导入')?.disabled).toBe(true)
    expect(button('导出')?.disabled).toBe(true)
    expect(button('一键清除')?.disabled).toBe(true)
  })

  it('enables independently granted import and export actions', () => {
    Object.assign(flags, {
      canOperate: true,
      canDelete: true,
      canImport: true,
      canExport: true,
    })
    const button = buttons()
    expect(button('导入')?.disabled).toBe(false)
    expect(button('导出')?.disabled).toBe(false)
    // No department is selected during server rendering, so the clear button
    // remains disabled by its business precondition.
    expect(button('一键清除')?.disabled).toBe(true)
  })
})
