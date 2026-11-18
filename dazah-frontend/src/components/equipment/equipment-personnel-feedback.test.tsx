/* @vitest-environment happy-dom */

import { act, type ReactNode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { App, ConfigProvider } from 'antd'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { PersonnelDrawer } from './PersonnelDrawer'
import { PersonnelCategoryDrawer } from './PersonnelCategoryDrawer'
import { PersonnelPage } from './PersonnelPage'
import { RoleManagePanel } from './RoleManagePanel'
import type { Personnel } from '@/types/equipment-personnel'

const actions = vi.hoisted(() => ({
  addPersonnel: vi.fn(), createRole: vi.fn(), updateRole: vi.fn(), deleteRole: vi.fn(),
  assignCategories: vi.fn(), assignRoles: vi.fn(), refreshFeishu: vi.fn(),
}))
vi.mock('@/actions/equipment-personnel', () => actions)
vi.mock('@/lib/api/equipment-personnel', () => ({ fetchRoles: vi.fn(async () => []) }))
vi.mock('@/lib/api/equipment-client', () => ({ fetchCategoriesClient: vi.fn(async () => []) }))
vi.mock('./PersonnelTable', () => ({
  PersonnelTable: ({ onRoleClick }: { onRoleClick: (personnel: Personnel) => void }) => (
    <button type="button" onClick={() => onRoleClick({
      id: 'person-1', name: '维修员甲', roles: [{ id: 'role-1', name: '维修员', code: 'repair', scope: 'maintenance' }],
    } as Personnel)}>分配角色</button>
  ),
}))

let root: Root
let host: HTMLDivElement
let client: QueryClient
const close = vi.fn()

beforeEach(() => {
  vi.resetAllMocks()
  client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } })
  client.setQueryData(['identity-users-search', ''], [
    { value: 'user-1', label: '维修员甲', dept: '设备部', eno: 'E-01', avatar: null },
    { value: 'user-2', label: '维修员乙', dept: '设备部', eno: 'E-02', avatar: null },
  ])
  vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(Response.json({ data: { items: [] } }))))
  host = document.createElement('div')
  document.body.append(host)
  root = createRoot(host)
})

afterEach(async () => {
  await act(async () => root.unmount())
  client.clear()
  host.remove()
  vi.unstubAllGlobals()
})

async function render(element: ReactNode) {
  await act(async () => root.render(
    <ConfigProvider theme={{ token: { motion: false } }}>
      <App>
        <QueryClientProvider client={client}>
          {element}
        </QueryClientProvider>
      </App>
    </ConfigProvider>,
  ))
}

async function selectPersonnel(...names: string[]) {
  await render(<PersonnelDrawer open onClose={close} roles={[]} workshopCode="201-3" />)
  const search = document.querySelector<HTMLInputElement>('input[role="combobox"]')
  expect(search).not.toBeNull()
  await act(async () => search?.dispatchEvent(new MouseEvent('mousedown', { bubbles: true })))
  for (const name of names) {
    await vi.waitFor(() => expect(Array.from(document.querySelectorAll('.ant-select-item-option-content'))
      .some(item => item.textContent?.includes(name))).toBe(true))
    const option = Array.from(document.querySelectorAll<HTMLElement>('.ant-select-item-option-content'))
      .find(item => item.textContent?.includes(name))
    await act(async () => option?.click())
  }
}

async function click(label: string, scope: ParentNode = document) {
  const button = Array.from(scope.querySelectorAll('button'))
    .find(el => el.textContent?.replace(/\s/g, '') === label)
  expect(button?.disabled).toBe(false)
  await act(async () => button?.click())
}

it('retries only the failed personnel after partial success and closes after a successful retry', async () => {
  actions.addPersonnel.mockResolvedValueOnce({
    ok: true,
    data: {
      added: [{ user_id: 'user-1' }],
      skipped: [],
      errors: [{ user_id: 'user-2', error_code: 'EQUIPMENT_PERSONNEL_USER_UNAVAILABLE' }],
    },
  }).mockResolvedValueOnce({ ok: true, data: { added: [{ user_id: 'user-2' }] } })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await selectPersonnel('维修员甲', '维修员乙')
  await click('确认添加')

  expect(actions.addPersonnel).toHaveBeenNthCalledWith(1, { user_ids: ['user-1', 'user-2'], workshop_code: '201-3' })
  expect(document.body.textContent).toContain('已添加 1 人，跳过 0 人，失败 1 人')
  expect(document.body.textContent).toContain('已选 1 人')
  expect(close).not.toHaveBeenCalled()
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['equipment-personnel'] })

  await click('确认添加')
  expect(actions.addPersonnel).toHaveBeenNthCalledWith(2, { user_ids: ['user-2'], workshop_code: '201-3' })
  expect(document.body.textContent).toContain('人员添加成功')
  expect(close).toHaveBeenCalledOnce()
})

it('shows the denied action message and keeps the selection and query cache', async () => {
  actions.addPersonnel.mockResolvedValue({ ok: false, message: '没有执行此操作的权限，请联系管理员' })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await selectPersonnel('维修员甲')
  await click('确认添加')

  expect(document.body.textContent).toContain('没有执行此操作的权限，请联系管理员')
  expect(document.body.textContent).toContain('已选 1 人')
  expect(invalidate).not.toHaveBeenCalled()
  expect(close).not.toHaveBeenCalled()
})

const role = {
  id: 'role-1', name: '维修员', code: 'repair', description: null,
  scope: 'maintenance', is_active: true, created_at: '', updated_at: '',
}

it('validates role inputs and preserves them after a duplicate code response', async () => {
  const warning = '角色编码已存在，请换一个编码后重试'
  actions.createRole.mockResolvedValue({ ok: false, message: warning })
  await render(<RoleManagePanel roles={[]} />)
  await click('新增角色')
  await click('创建')
  expect(actions.createRole).not.toHaveBeenCalled()
  await vi.waitFor(() => expect(document.body.textContent).toContain('请输入角色名称'))

  const text = { name: role.name, code: role.code }
  await act(async () => {
    for (const [field, value] of Object.entries(text)) {
      const input = document.querySelector<HTMLInputElement>(`#${field}`)
      expect(input).not.toBeNull()
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
      input?.dispatchEvent(new Event('input', { bubbles: true }))
    }
  })
  await click('创建')
  expect(actions.createRole).toHaveBeenCalledWith(expect.objectContaining(text))
  expect(document.body.textContent).toContain(warning)
  expect(document.querySelector<HTMLInputElement>('#code')?.value).toBe(role.code)
  expect(document.querySelector('[role="dialog"]')).not.toBeNull()
})

it('changes role details only after saving and invalidates the role list on success', async () => {
  actions.updateRole.mockResolvedValue({ ok: true, data: {} })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await render(<RoleManagePanel roles={[role]} />)
  await click('编辑')
  const input = document.querySelector<HTMLInputElement>('#name')
  expect(input?.value).toBe(role.name)
  await act(async () => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, '设备维修员')
    input?.dispatchEvent(new Event('input', { bubbles: true }))
  })
  expect(actions.updateRole).not.toHaveBeenCalled()
  await click('保存')
  expect(actions.updateRole).toHaveBeenCalledWith(role.id, { name: '设备维修员' })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['equipment-roles'] })
  expect(document.body.textContent).toContain('角色已更新')
})

it('keeps a role when deletion is denied and refreshes after a confirmed retry', async () => {
  const denied = '没有执行此操作的权限，请联系管理员'
  actions.deleteRole.mockResolvedValueOnce({ ok: false, message: denied }).mockResolvedValueOnce({ ok: true, data: {} })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await render(<RoleManagePanel roles={[role]} />)
  async function confirmDelete() {
    await click('删除')
    const confirmation = document.querySelector<HTMLButtonElement>('.ant-popconfirm button.ant-btn-primary')
    expect(confirmation?.disabled).toBe(false)
    await act(async () => confirmation?.click())
  }
  await confirmDelete()
  expect(actions.deleteRole).toHaveBeenCalledWith(role.id)
  expect(document.body.textContent).toContain(denied)
  expect(host.textContent).toContain(role.name)
  expect(invalidate).not.toHaveBeenCalled()
  await confirmDelete()
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['equipment-roles'] })
  expect(document.body.textContent).toContain('角色已删除')
})

it('retains role assignments after a failed save and refreshes only on success', async () => {
  const denied = '没有执行此操作的权限，请联系管理员'
  actions.assignRoles.mockResolvedValueOnce({ ok: false, message: denied }).mockResolvedValueOnce({ ok: true, data: {} })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  client.setQueryData(['equipment-roles'], [role])
  await render(<PersonnelPage workshopCode="201-3" />)
  await click('分配角色')
  await click('保存')
  expect(actions.assignRoles).toHaveBeenCalledWith('person-1', { role_ids: [role.id] })
  expect(document.body.textContent).toContain(denied)
  expect(document.querySelector('[role="dialog"]')?.textContent).toContain('维修员甲')
  expect(invalidate).not.toHaveBeenCalled()
  await click('保存')
  expect(actions.assignRoles).toHaveBeenLastCalledWith('person-1', { role_ids: [role.id] })
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['equipment-personnel'] })
})

it('shows an uncertain result when the Feishu refresh fails and makes no redundant refresh', async () => {
  actions.refreshFeishu.mockRejectedValueOnce(new Error('TypeError: internal department lookup'))
    .mockResolvedValueOnce({ ok: true, data: {} })
  const invalidate = vi.spyOn(client, 'invalidateQueries')
  await render(<PersonnelPage workshopCode="201-3" />)
  await click('刷新飞书')
  expect(document.body.textContent).toContain('暂未确认设备人员飞书信息刷新结果')
  expect(invalidate).not.toHaveBeenCalled()
  await click('刷新飞书')
  expect(actions.refreshFeishu).toHaveBeenCalledTimes(2)
  expect(invalidate).toHaveBeenCalledWith({ queryKey: ['equipment-personnel'] })
})

it('keeps category assignments selected until the server confirms the save', async () => {
  actions.assignCategories.mockResolvedValueOnce({ ok: false, message: '数据已发生变化，请刷新后重试' })
    .mockResolvedValueOnce({ ok: true, data: {} })
  await render(<PersonnelCategoryDrawer
    open onClose={close} personnelId="person-1" personnelName="维修员甲" roles={[role]}
    existingCategories={[{ role_id: role.id, role_name: role.name, category_id: 'cat-1', category_name: '压力设备' }]}
  />)
  await click('保存约束')
  expect(actions.assignCategories).toHaveBeenCalledWith('person-1', {
    categories: [{ role_id: role.id, category_id: 'cat-1' }],
  })
  expect(document.body.textContent).toContain('数据已发生变化，请刷新后重试')
  expect(close).not.toHaveBeenCalled()
  await click('保存约束')
  expect(actions.assignCategories.mock.calls[1]).toEqual(actions.assignCategories.mock.calls[0])
  expect(close).toHaveBeenCalledOnce()
})
