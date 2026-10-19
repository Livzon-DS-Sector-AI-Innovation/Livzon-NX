/* @vitest-environment happy-dom */
import { act } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { getPageKeyByPath } from '@/lib/menu-config'
import { useAuthStore } from '@/stores/auth'
import type { CertificateSheetDetail, ProjectLedgerSheetDetail } from '@/types/registration'

const route = vi.hoisted(() => ({ path: '' }))
vi.mock('next/navigation', () => ({ usePathname: () => route.path, useRouter: () => ({ refresh: vi.fn() }) }))
import CertificateSheetPage from './CertificateSheetPage'
import ProjectLedgerSheetPage from './ProjectLedgerSheetPage'

let root: Root
let container: HTMLElement
function authorize(operate: boolean, actions: string[] = []) {
  act(() => useAuthStore.getState().setUser({
    id: 'tester', name: '测试用户', role: 'user', permissions: ['*', 'registration:write'],
    page_permissions: [{ page_key: getPageKeyByPath(route.path)!, module_code: 'registration',
      permissions: operate ? ['access', 'query', 'operate'] : ['access', 'query'],
      sensitive_actions: actions, data_scope: { scope_type: 'all' }, source: 'user' }],
  }))
}
function button(text: string) {
  const result = [...container.querySelectorAll('button')].find((item) => item.textContent?.replace(/\s/g, '') === text)
  expect(result, text).toBeTruthy()
  return result!
}
beforeEach(() => {
  container = document.createElement('div')
  document.body.append(container)
  root = createRoot(container)
})
afterEach(() => {
  act(() => root.unmount())
  container.remove()
  document.body.replaceChildren()
  useAuthStore.getState().clearUser()
})

it.each(['certificate', 'project'])('controls %s writes and deletion separately and closes forms after revocation', async (kind) => {
  route.path = kind === 'certificate' ? '/registration/certificate-management/international-registration'
    : '/registration/project-ledger/international-associated-review'
  expect(getPageKeyByPath(route.path)).toBeTruthy()
  authorize(false)
  const certificate: CertificateSheetDetail = {
    sheet_key: 'international-registration', sheet_name: '测试证书', title: '测试证书',
    source_file_name: 'test.xlsx', updated_at: null, columns: [],
    summary: { sheet_key: 'international-registration', sheet_name: '测试证书', title: '测试证书',
      due_90_count: 0, expired_count: 0, issuer_count: 0, product_count: 0, total_pages: 0, total_records: 1 },
    rows: [{ id: 'row1', sequence: 1, values: {}, expiry_status: 'normal', expiry_date: null, issue_date: null }],
  }
  const project: ProjectLedgerSheetDetail = {
    sheet_key: 'international-associated-review', sheet_name: '测试项目', title: '测试项目',
    summary: { sheet_key: 'international-associated-review', sheet_name: '测试项目', title: '测试项目',
      total_records: 1, records_with_history: 0, total_history_versions: 0 },
    columns: [{ key: 'project', label: '项目名称' }],
    records: [{ record_id: 'row1', record_key: 'row1', sequence: 1, history_count: 1, history_records: [], latest_values: { project: '测试项目' } }],
  }
  await act(async () => root.render(<ConfigProvider theme={{ token: { motion: false } }}><App>{kind === 'certificate'
    ? <CertificateSheetPage detail={certificate} /> : <ProjectLedgerSheetPage detail={project} />}</App></ConfigProvider>))
  if (kind === 'project') act(() => container.querySelector<HTMLElement>('tr[data-row-key="row1"]')?.click())
  const create = kind === 'certificate' ? '新增' : '新增主记录'
  const edit = kind === 'certificate' ? '编辑选中' : '编辑主记录'
  const remove = '删除选中'
  expect(button(create).disabled).toBe(true)
  expect(button(edit).disabled).toBe(true)
  expect(button(remove).disabled).toBe(true)
  authorize(true)
  expect(button(create).disabled).toBe(false)
  expect(button(edit).disabled).toBe(false)
  expect(button(remove).disabled).toBe(true)
  authorize(true, ['delete'])
  expect(button(remove).disabled).toBe(false)
  act(() => button(create).click())
  expect(document.body.querySelector('.ant-modal, .ant-drawer')).toBeTruthy()
  authorize(false, ['delete'])
  expect(button(create).disabled).toBe(true)
  expect(button(edit).disabled).toBe(true)
  expect(button(remove).disabled).toBe(true)
  await act(async () => { await new Promise((resolve) => setTimeout(resolve, 300)) })
  const modal = document.body.querySelector<HTMLElement>('.ant-modal-wrap')
  if (modal) expect(modal.style.display).toBe('none')
  expect(document.body.querySelector('.ant-drawer-open')).toBeNull()
})
