/* @vitest-environment happy-dom */
import React from 'react'
import { App } from 'antd'
import { renderToStaticMarkup } from 'react-dom/server'
import { afterEach, expect, it, vi } from 'vitest'
import { useAuthStore } from '@/stores/auth'

vi.mock('@/actions/purchasing', () => ({ importSupplierTable: vi.fn() }))
vi.mock('@/lib/api/purchasing', () => ({ fetchSuppliers: vi.fn() }))
import { SupplierManagementClient } from './SupplierManagementClient'

afterEach(() => useAuthStore.getState().clearUser())

it('explains and disables importing when page operation permission is absent', () => {
  useAuthStore.getState().setUser({ id: 'reader', name: '只读用户',
    page_permission_rollouts: { procurement: 'enforced' }, page_permissions: [] })
  const html = renderToStaticMarkup(<App><SupplierManagementClient initialRecords={[]}
    initialTotal={0} initialColumns={[]} /></App>)
  expect(html).toContain('未获得批量导入权限，仅可查询供应商清单')
  expect(html).toContain('ant-upload-disabled')
})
