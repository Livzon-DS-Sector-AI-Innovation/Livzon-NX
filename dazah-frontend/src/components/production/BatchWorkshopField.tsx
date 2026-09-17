'use client'

import { Form, Select } from 'antd'
import { useAuthStore, type AuthUser } from '@/stores/auth'
import { PRODUCTION_PAGE_KEYS } from './useProductionPermissions'

const prefix = 'production:batches:workshop-'
const workshopPages = Object.values(PRODUCTION_PAGE_KEYS).filter(key => key.startsWith(prefix))
const workshopCode = (key: string) => key.slice(prefix.length).split(':')[0]

export function batchWorkshopOptions(user: AuthUser | null, pageKey: string) {
  const keys = user?.role === 'admin' ? workshopPages : workshopPages.filter(key =>
    user?.page_permissions?.some(grant => grant.page_key === key && grant.permissions?.includes('operate')),
  )
  return [...new Set(keys.map(workshopCode))]
    .filter(code => !pageKey.startsWith(prefix) || code === workshopCode(pageKey))
    .map(code => ({ value: code, label: `${code}车间` }))
}

/** Ownership is explicit; historical records remain unassigned until confirmed. */
export function BatchWorkshopField({ pageKey = PRODUCTION_PAGE_KEYS.overview }: { pageKey?: string }) {
  const user = useAuthStore(state => state.user)
  return <Form.Item name="workshop_code" label="所属车间" rules={[{ required: true, message: '请选择实际所属车间' }]}>
    <Select placeholder="待确认，请选择实际所属车间" options={batchWorkshopOptions(user, pageKey)} />
  </Form.Item>
}
