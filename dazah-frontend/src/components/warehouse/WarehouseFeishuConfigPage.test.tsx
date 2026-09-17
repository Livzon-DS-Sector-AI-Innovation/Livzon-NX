/* @vitest-environment happy-dom */

import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { WarehouseFeishuConfigPage } from './WarehouseFeishuConfigPage'

const permissions = vi.hoisted(() => ({ canSync: false }))
vi.mock('@/hooks/usePagePermissions', () => ({ usePagePermissions: () => permissions }))
vi.mock('@/actions/warehouse', () => ({ updateWarehousePageFeishuConfigAction: vi.fn() }))
vi.mock('@/lib/api/client/warehouse', () => ({ fetchWarehousePageFeishuConfigs: vi.fn() }))

describe('warehouse configuration action grants', () => {
  let root: Root
  let container: HTMLDivElement
  afterEach(() => {
    act(() => root.unmount())
    container.remove()
  })

  it.each([false, true])('requires sync_config to edit configuration: %s', async (canSync) => {
    permissions.canSync = canSync
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
    await act(async () => {
      root.render(<App><WarehouseFeishuConfigPage initialConfigs={[{
        page_key: 'acceptance-page', app_token: 'test-base', table_id: 'test-table', table_name: '验收表',
      }]} /></App>)
    })
    const input = container.querySelector<HTMLInputElement>('input')
    expect(input?.disabled).toBe(!canSync)
    const header = container.querySelector<HTMLElement>('.ant-collapse-header')
    expect(header).not.toBeNull()
    await act(async () => { header!.click() })
    const edit = Array.from(container.querySelectorAll('button')).find(button => button.textContent?.replace(/\s/g, '') === '编辑')
    expect(edit?.disabled).toBe(!canSync)
  })
})
