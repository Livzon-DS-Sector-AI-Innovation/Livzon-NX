/* @vitest-environment happy-dom */
import React, { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AntdApp } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  fetchTrainingDepartments: vi.fn(),
  fetchEmployeeTrainingMembers: vi.fn(),
  fetchEmployeeTrainingRecords: vi.fn(),
  importFeishuMembers: vi.fn(),
  addEmployeeTrainingMember: vi.fn(),
  removeEmployeeTrainingMember: vi.fn(),
  updateEmployeeTrainingMember: vi.fn(),
}))

vi.mock('@/lib/api/client/hr', () => ({
  fetchTrainingDepartments: mocks.fetchTrainingDepartments,
  fetchEmployeeTrainingMembers: mocks.fetchEmployeeTrainingMembers,
  fetchEmployeeTrainingRecords: mocks.fetchEmployeeTrainingRecords,
}))

vi.mock('@/actions/hr', () => ({
  importFeishuMembers: mocks.importFeishuMembers,
  addEmployeeTrainingMember: mocks.addEmployeeTrainingMember,
  removeEmployeeTrainingMember: mocks.removeEmployeeTrainingMember,
  updateEmployeeTrainingMember: mocks.updateEmployeeTrainingMember,
}))

import EmployeeTrainingListClient from './EmployeeTrainingListClient'

let root: Root
let container: HTMLDivElement
let client: QueryClient

beforeEach(() => {
  mocks.fetchTrainingDepartments.mockReset().mockResolvedValue(['质量部'])
  mocks.fetchEmployeeTrainingMembers.mockReset().mockResolvedValue([
    { id: 'u1', name: '张三', position: 'QA' },
  ])
  mocks.fetchEmployeeTrainingRecords.mockReset().mockResolvedValue([])
  mocks.importFeishuMembers.mockReset()
  mocks.addEmployeeTrainingMember.mockReset()
  mocks.removeEmployeeTrainingMember.mockReset()
  mocks.updateEmployeeTrainingMember.mockReset()
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  container.remove()
  vi.unstubAllGlobals()
})

function renderPage(): void {
  act(() => {
    root.render(
      <QueryClientProvider client={client}>
        <AntdApp>
          <EmployeeTrainingListClient />
        </AntdApp>
      </QueryClientProvider>,
    )
  })
}

function findButton(text: string): HTMLButtonElement | undefined {
  return Array.from(document.querySelectorAll('button')).find((b) =>
    b.textContent?.includes(text),
  ) as HTMLButtonElement | undefined
}

it('导出失败时把后端原因透出到错误提示（单导出与一键导出共用下载封装）', async () => {
  renderPage()
  await vi.waitFor(() => {
    const btn = findButton('一键导出全部')
    expect(btn).toBeTruthy()
    expect(btn?.disabled).toBe(false)
  })

  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ code: 500, message: '导出模板缺失：HR-QD-01' }), {
        status: 500,
        headers: { 'content-type': 'application/json' },
      }),
    ),
  )

  // 一键导出全部：下载封装抛出后端 message，进入 catch 提示
  await act(async () => {
    findButton('一键导出全部')?.click()
  })
  await vi.waitFor(() => {
    expect(document.body.textContent).toContain('导出模板缺失：HR-QD-01')
  })

  // 选中人员后单导出：共用同一下载封装，错误同样透出
  await act(async () => {
    ;(Array.from(document.querySelectorAll('li')).find((li) =>
      li.textContent?.includes('张三'),
    ) as HTMLElement | undefined)?.click()
  })
  await act(async () => {
    findButton('导出清单')?.click()
  })
  await vi.waitFor(() => {
    const errors = Array.from(document.querySelectorAll('.ant-message')).filter(
      (el) => el.textContent?.includes('导出模板缺失'),
    )
    expect(errors.length).toBeGreaterThanOrEqual(1)
  })
})
