/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import LLMConfigClient from './LLMConfigClient'

const actions = vi.hoisted(() => ({
  getLLMConfigs: vi.fn(), createLLMConfig: vi.fn(), updateLLMConfig: vi.fn(),
  deleteLLMConfig: vi.fn(), testLLMConnection: vi.fn(), testLLMConfig: vi.fn(), probeLLMConfig: vi.fn(),
}))
vi.mock('@/actions/settings', () => actions)
vi.mock('next/navigation', () => ({ useRouter: () => ({ back: vi.fn() }) }))

const prior = {
  id: 'config-1', config_name: '示例配置', api_base_url: 'https://provider.example.test/v1',
  model_name: 'fixture-model', is_active: false, temperature: 0, timeout_seconds: 30, notes: '', capabilities: [],
}
const technicalError = 'TypeError: internal model adapter'
const expected = '操作未完成，请稍后重试'
let host: HTMLDivElement
let root: Root

beforeEach(async () => {
  vi.resetAllMocks()
  actions.getLLMConfigs.mockResolvedValue({ data: [prior] })
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
  await act(async () => root.render(
    <ConfigProvider theme={{ token: { motion: false } }}><App><LLMConfigClient /></App></ConfigProvider>,
  ))
})

afterEach(async () => {
  await act(async () => root.unmount())
  host.remove()
})

function button(label: string) {
  return Array.from(document.querySelectorAll('button')).find(el => el.textContent?.replace(/\s/g, '') === label)
}

async function click(element?: HTMLButtonElement | null) {
  expect(element?.disabled).toBe(false)
  await act(async () => element?.click())
}

it('reports probe and connection errors without refreshing or modifying a saved configuration', async () => {
  actions.testLLMConnection.mockRejectedValueOnce(new Error(technicalError))
  actions.testLLMConfig.mockRejectedValueOnce(new Error(technicalError))
  await click(button('测试连接'))
  expect(actions.testLLMConnection).toHaveBeenCalledOnce()
  expect(document.body.textContent).toContain(expected)
  const probe = host.querySelector('tbody [aria-label="api"]')?.closest('button')
  await click(probe)
  expect(actions.testLLMConfig).toHaveBeenCalledWith(prior.id)
  expect(actions.getLLMConfigs).toHaveBeenCalledOnce()
  expect(actions.updateLLMConfig).not.toHaveBeenCalled()
  expect(host.textContent).toContain(prior.config_name)
  expect(document.body.textContent).not.toContain(technicalError)
})

it('keeps the editor open after a rejected save and an unsuccessful draft probe', async () => {
  actions.updateLLMConfig.mockRejectedValueOnce(new Error(technicalError))
  actions.probeLLMConfig.mockRejectedValueOnce(new Error(technicalError))
  await click(host.querySelector('tbody [aria-label="edit"]')?.closest('button'))
  await click(button('保存'))
  expect(actions.updateLLMConfig).toHaveBeenCalledWith(prior.id, expect.objectContaining({ model_name: prior.model_name }))
  expect(actions.updateLLMConfig.mock.calls[0][1]).not.toHaveProperty('api_key')
  expect(document.body.textContent).toContain(expected)

  const draftValue = 'fixture-only-value'
  const key = document.querySelector<HTMLInputElement>('#api_key')
  expect(key).not.toBeNull()
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(key, draftValue)
    key?.dispatchEvent(new Event('input', { bubbles: true }))
  })
  await click(button('测试URL'))
  expect(actions.probeLLMConfig).toHaveBeenCalledWith({
    probe_type: 'url', api_base_url: prior.api_base_url, api_key: draftValue, model_name: null, timeout_seconds: 30,
  })
  expect(document.body.textContent).toContain(expected)
  expect(document.body.textContent).not.toContain(technicalError)
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('编辑 LLM 配置')
  expect(actions.getLLMConfigs).toHaveBeenCalledOnce()
})
