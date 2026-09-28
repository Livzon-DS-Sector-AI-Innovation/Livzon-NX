/* @vitest-environment happy-dom */
import { act, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { expect, it, vi } from 'vitest'
import { DataScopeConfig, type DataScopeSelection } from './DataScopeConfig'

it.each([false, true])('preserves department scope semantics with segmented=%s', async (segmented) => {
  const host = document.createElement('div')
  document.body.append(host)
  const root = createRoot(host)
  const onChange = vi.fn()
  function Fixture() {
    const [value, setValue] = useState<DataScopeSelection>({ scopeType: null, departmentNames: [] })
    return <DataScopeConfig segmented={segmented} departments={[
      { id: 'qa', name: '质量部', feishu_department_id: 'qa', parent_feishu_department_id: null },
    ]} value={value} onChange={(next) => { onChange(next); setValue(next) }} />
  }
  const radio = (value: string) => host.querySelector<HTMLInputElement>(`input[type="radio"][value="${value}"]`)!
  try {
    await act(async () => root.render(<Fixture />))
    expect(radio('default').checked).toBe(true)
    expect(host.textContent).toContain(segmented ? '本部门 + 子部门' : '默认（本部门 + 子部门）')
    await act(async () => radio('departments').click())
    expect(onChange).toHaveBeenLastCalledWith({ scopeType: 'departments', departmentNames: [] })
    expect(host.textContent).toContain('质量部')
    await act(async () => host.querySelector<HTMLElement>('.ant-tree-checkbox')!.click())
    expect(onChange).toHaveBeenLastCalledWith({ scopeType: 'departments', departmentNames: ['质量部'] })
    await act(async () => radio('all').click())
    expect(onChange).toHaveBeenLastCalledWith({ scopeType: 'all', departmentNames: [] })
    expect(host.querySelector('.ant-tree')).toBeNull()
    await act(async () => radio('default').click())
    expect(onChange).toHaveBeenLastCalledWith({ scopeType: null, departmentNames: [] })
  } finally {
    await act(async () => root.unmount())
    host.remove()
  }
})
