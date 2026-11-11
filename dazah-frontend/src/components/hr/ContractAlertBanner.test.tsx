/* @vitest-environment happy-dom */

import { App, ConfigProvider, theme } from 'antd'
import { act } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { getAntdTheme } from '@/lib/antd-theme'
import type { ColorMode } from '@/lib/appearance'
import ContractAlertBanner from './ContractAlertBanner'

vi.mock('@/actions/hr', () => ({
  getContractPushStatusAction: vi.fn().mockResolvedValue({ data: {} }),
  pushContractExpiringAction: vi.fn(),
  saveContractTemplateAction: vi.fn(),
}))

it('keeps contract rows readable when the appearance changes with the full list open', async () => {
  const employees = Array.from({ length: 21 }, (_, index) => ({
    employee_id: String(index),
    name: `测试员工 ${index + 1}`,
    department: '生产部',
    contract_end_date: '2026-11-30',
  }))
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ data: employees }) }))
  const host = document.body.appendChild(document.createElement('div'))
  const root = createRoot(host)

  const render = (mode: ColorMode) => act(async () => {
    root.render(
      <ConfigProvider theme={getAntdTheme(mode)}>
        <App><ContractAlertBanner /></App>
      </ConfigProvider>,
    )
  })

  function checkRow(container: ParentNode | null, name: string, mode: ColorMode) {
    const employee = [...(container?.querySelectorAll('strong') ?? [])]
      .find(element => element.textContent === name)
    const department = employee?.nextElementSibling
    const row = employee?.parentElement?.parentElement
    const date = row?.lastElementChild
    expect(department?.textContent).toBe('生产部')
    expect(date?.textContent).toBe('2026-11-30')

    const token = theme.getDesignToken(getAntdTheme(mode))
    const expected = document.createElement('div')
    expected.style.backgroundColor = token.colorBgLayout
    expected.style.color = token.colorText
    expect(row?.style.backgroundColor).toBe(expected.style.backgroundColor)
    expect(row?.style.color).toBe(expected.style.color)
    expect(date).toHaveProperty('style.color', expected.style.color)
    expected.style.backgroundColor = token.colorWarningBg
    expect(date).toHaveProperty('style.backgroundColor', expected.style.backgroundColor)
    expected.style.color = token.colorTextSecondary
    expect(department).toHaveProperty('style.color', expected.style.color)
  }

  try {
    await render('dark')
    const viewAll = [...host.querySelectorAll('button')].find(button => button.textContent === '查看全部')
    expect(viewAll).toBeDefined()
    expect(host.textContent).not.toContain('测试员工 21')
    await act(async () => viewAll?.click())

    checkRow(host, '测试员工 1', 'dark')
    checkRow(document.querySelector('[role="dialog"]'), '测试员工 21', 'dark')

    await render('light')
    checkRow(host, '测试员工 1', 'light')
    checkRow(document.querySelector('[role="dialog"]'), '测试员工 21', 'light')
  } finally {
    await act(async () => root.unmount())
    host.remove()
    vi.unstubAllGlobals()
  }
})
