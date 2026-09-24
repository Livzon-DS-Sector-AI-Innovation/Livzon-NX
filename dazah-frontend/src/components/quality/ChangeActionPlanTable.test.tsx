/* @vitest-environment happy-dom */
import React from 'react'
import { createRoot } from 'react-dom/client'
import { act } from 'react'
import { describe, expect, it, vi } from 'vitest'
import type { ChangeActionPlanListItem } from '@/types/quality'
import { ChangeActionPlanTable } from './ChangeActionPlanTable'

function mockBrowserApis() {
  window.matchMedia = window.matchMedia ?? (() => ({
    matches: false,
    media: '',
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
  if (!(globalThis as { ResizeObserver?: unknown }).ResizeObserver) {
    ;(globalThis as { ResizeObserver?: unknown }).ResizeObserver = class {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
  }
}

const baseItem: ChangeActionPlanListItem = {
  id: '0b9a7c1e-0000-4000-8000-000000000001',
  change_id: null,
  change_code: 'BG-2601004',
  project_name: '修订检验规程',
  related_work: '跟踪残留溶剂检测',
  owner_name: '李文昊',
  owner_user_id: 'on_45aff2627b8d',
  owner_avatar_url: 'https://example.feishucdn.com/a.jpeg',
  director_name: '王经理',
  director_user_id: 'on_director_001',
  director_avatar_url: null,
  deadline_date: '2026-03-15',
  status: '已完成',
  delay_flag: '否',
  delayed_deadline_date: null,
  feishu_record_id: 'rec_create_001',
  sync_status: 'synced',
  sync_error: null,
  last_synced_at: '2026-09-24T00:00:00+00:00',
  reminder_enabled: true,
  reminder_status: 'pending',
  last_reminded_at: null,
  reminder_confirmed_at: null,
  reminder_confirmed_by: null,
  reminder_message_id: null,
  created_at: '2026-09-24T00:00:00+00:00',
  updated_at: '2026-09-24T00:00:00+00:00',
}

function renderTable(item: ChangeActionPlanListItem): HTMLElement {
  const container = document.createElement('div')
  document.body.append(container)
  const root = createRoot(container)
  act(() => {
    root.render(
      <ChangeActionPlanTable
        items={[item]}
        total={1}
        loading={false}
        page={1}
        pageSize={20}
        filters={{ change_code: '', project_name: '', related_work: '', owner_name: '', status: '' }}
        onFilterChange={() => {}}
        onPageChange={() => {}}
        onRefresh={() => {}}
        onSyncAll={() => {}}
        onEdit={() => {}}
        onSyncSingle={() => {}}
        onDelete={() => {}}
      />
    )
  })
  return container
}

describe('ChangeActionPlanTable', () => {
  it('部门负责人列按飞书叫法展示，且带头像 URL 的人员渲染头像+姓名', () => {
    mockBrowserApis()
    const el = renderTable(baseItem)
    const headers = Array.from(el.querySelectorAll('th')).map((th) => th.textContent || '')
    expect(headers).toContain('部门负责人')
    expect(headers).not.toContain('部门总监')

    // PersonCell：总负责人有 avatar_url → 渲染图片头像并显示姓名
    const ownerAvatar = el.querySelector('img[src="https://example.feishucdn.com/a.jpeg"]')
    expect(ownerAvatar).toBeTruthy()
    expect(el.textContent).toContain('李文昊')
    expect(el.textContent).toContain('王经理')
  })
})
