/* @vitest-environment happy-dom */

// antd v6 Space orientation API 迁移回归：本模块组件（ProcurementMaterialSourceSettingsClient）已从
// direction 切换到 orientation，此处固化 API 契约。
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { Space } from 'antd'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

describe('Space orientation（antd v6 迁移契约）', () => {
  let root: Root
  let container: HTMLElement

  beforeEach(() => {
    container = document.createElement('div')
    document.body.append(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container?.remove()
  })

  it('orientation=vertical 渲染垂直布局类', () => {
    act(() => {
      root.render(<Space orientation="vertical">a</Space>)
    })
    expect(container.querySelector('.ant-space-vertical')).toBeTruthy()
    expect(container.querySelector('.ant-space-horizontal')).toBeNull()
  })

  it('缺省 orientation 渲染水平布局类', () => {
    act(() => {
      root.render(<Space>a</Space>)
    })
    expect(container.querySelector('.ant-space-horizontal')).toBeTruthy()
  })
})
