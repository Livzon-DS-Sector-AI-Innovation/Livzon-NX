import { describe, expect, it } from 'vitest'
import { batchWorkshopOptions } from './BatchWorkshopField'
import type { AuthUser } from '@/stores/auth'

const user: AuthUser = {
  id: 'acceptance', name: '验收人员', role: 'user',
  page_permissions: [{
    page_key: 'production:batches:workshop-101-1', module_code: 'production',
    permissions: ['access', 'query', 'operate'], sensitive_actions: [],
    data_scope: { scope_type: 'not_applicable', department_ids: [] }, source: 'user', source_role_names: [],
  }],
}

describe('batch ownership choices', () => {
  it('offers only writable workshops in the overview', () => {
    expect(batchWorkshopOptions(user, 'production:overview')).toEqual([{ value: '101-1', label: '101-1车间' }])
    expect(batchWorkshopOptions(null, 'production:overview')).toEqual([])
  })
  it('does not use overview query access as workshop write access', () => {
    expect(batchWorkshopOptions({ ...user, page_permissions: [] }, 'production:overview')).toEqual([])
  })
  it('keeps a workshop page within its workshop and merges the two 103 product pages', () => {
    const admin = { ...user, role: 'admin' }
    expect(batchWorkshopOptions(admin, 'production:batches:workshop-201-3')).toEqual([{ value: '201-3', label: '201-3车间' }])
    const codes = batchWorkshopOptions(admin, 'production:overview').map(option => option.value)
    expect(codes.filter(code => code === '103')).toHaveLength(1)
    expect(codes.every(code => !code.includes(':'))).toBe(true)
  })
})
