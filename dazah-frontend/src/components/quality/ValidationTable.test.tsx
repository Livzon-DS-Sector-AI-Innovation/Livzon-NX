/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App } from 'antd'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ValidationTable } from './ValidationTable'

let container: HTMLElement
let root: Root

const baseFilters = {
  record_code: '',
  keyword: '',
  status: '',
  department: '',
  validation_type: '',
  planned_end_date_from: '',
  planned_end_date_to: '',
  drafted_at_from: '',
  drafted_at_to: '',
  year: '',
}

function renderTable(props: Partial<Parameters<typeof ValidationTable>[0]> = {}) {
  act(() => {
    root.render(
      <App>
        <ValidationTable
          mode="child"
          validationType="process_validation"
          items={[]}
          total={0}
          loading={false}
          page={1}
          pageSize={20}
          filters={baseFilters}
          onFilterChange={vi.fn()}
          onPageChange={vi.fn()}
          onRefresh={vi.fn()}
          onCreate={vi.fn()}
          onDetail={vi.fn()}
          onEdit={vi.fn()}
          onDelete={vi.fn()}
          {...props}
        />
      </App>,
    )
  })
}

describe('ValidationTable rendering', () => {
  beforeEach(() => {
    container = document.createElement('div')
    document.body.appendChild(container)
    root = createRoot(container)
  })

  afterEach(() => {
    act(() => root.unmount())
    container.remove()
    vi.restoreAllMocks()
  })

  it('renders structured participants and owner with avatars in child mode', () => {
    renderTable({
      items: [
        {
          id: '1',
          title: '工艺验证方案A',
          participants: [
            { name: '张三', avatar_url: 'https://a/x.png', id: 'ou_1' },
            { name: '李四', id: 'ou_2' },
          ],
          owner_name: [{ name: '王五', id: 'ou_3' }],
          group_chat: [{ id: 'oc_1', name: '验证群', avatar_url: 'https://a/g.png' }],
        } as never,
      ],
      total: 1,
    })
    const text = document.body.textContent || ''
    expect(text).toContain('工艺验证方案A')
    expect(text).toContain('张三')
    expect(text).toContain('李四')
    expect(text).toContain('王五')
    expect(text).toContain('验证群')
  })

  it('joins plain string participant/group arrays and falls back to dash', () => {
    renderTable({
      items: [
        {
          id: '2',
          title: '清洁验证',
          participants: '赵六、钱七',
          group_chat: ['验证A群', '验证B群'],
          owner_name: null,
        } as never,
      ],
      total: 1,
    })
    const text = document.body.textContent || ''
    expect(text).toContain('赵六、钱七')
    expect(text).toContain('验证A群、验证B群')
  })

  it('renders detail button and triggers onDetail when provided', () => {
    const onDetail = vi.fn()
    renderTable({
      onDetail,
      items: [{ id: '3', title: '设备确认' } as never],
      total: 1,
    })
    const detailBtn = Array.from(document.body.querySelectorAll('button')).find(
      (btn) => btn.getAttribute('aria-label') || btn.querySelector('span[aria-label="eye"]'),
    )
    expect(detailBtn).toBeTruthy()
  })

  it('renders product codes as tags and year options in master mode', () => {
    renderTable({
      mode: 'master',
      items: [
        {
          id: '4',
          title: '验证主计划',
          product_codes: ['MV', 'LV'],
        } as never,
      ],
      total: 1,
    })
    const text = document.body.textContent || ''
    expect(text).toContain('MV')
    expect(text).toContain('LV')
    expect(text).toContain('总表（全部年份）')
  })
})
