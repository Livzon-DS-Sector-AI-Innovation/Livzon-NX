'use server'

import { getServerApiBaseUrl } from '@/lib/server-api'
import { revalidatePath } from 'next/cache'
import { getAuthHeaders } from '@/lib/auth'
import { requireActionResponse, serverActionResult, type BusinessErrorMessages } from '@/lib/server-action-result'
import { uncertainWriteMessage } from '@/lib/user-error'
import type { components } from '@/types/generated/schema'
import type {
  CreateRoleInput, UpdateRoleInput, AddPersonnelInput,
  AssignRolesInput, AssignCategoriesInput,
} from '@/types/equipment-personnel'

const BASE = `${getServerApiBaseUrl()}/api/v1/equipment/personnel`
const roleConflict = {
  EQUIPMENT_ROLE_CODE_EXISTS: '角色编码已存在，请换一个编码后重试',
} satisfies Record<components['schemas']['EquipmentRoleConflictDetail']['error_code'], string>

function personnelMutation<T = unknown>(
  operation: string,
  label: string,
  path: string,
  method: 'POST' | 'PUT' | 'DELETE',
  data?: unknown,
  businessMessages?: BusinessErrorMessages,
) {
  return serverActionResult(`equipment.personnel.${operation}`, async (): Promise<T> => {
    const response = await fetch(`${BASE}${path}`, {
      method,
      headers: { 'Content-Type': 'application/json', ...await getAuthHeaders() },
      body: data === undefined ? undefined : JSON.stringify(data),
    })
    await requireActionResponse(response, businessMessages)
    const payload = await response.json()
    revalidatePath('/equipment/personnel', 'page')
    return payload.data ?? payload
  }, uncertainWriteMessage(label))
}

export async function createRole(data: CreateRoleInput) {
  return personnelMutation('createRole', '设备角色创建', '/roles', 'POST', data, { 409: roleConflict })
}

export async function updateRole(id: string, data: UpdateRoleInput) {
  return personnelMutation('updateRole', '设备角色更新', `/roles/${encodeURIComponent(id)}`, 'PUT', data)
}

export async function deleteRole(id: string) {
  return personnelMutation('deleteRole', '设备角色删除', `/roles/${encodeURIComponent(id)}`, 'DELETE')
}

export async function addPersonnel(data: AddPersonnelInput) {
  return personnelMutation<components['schemas']['PersonnelAddResult']>('add', '设备人员添加', '', 'POST', data)
}

export async function deletePersonnel(id: string) {
  return personnelMutation('delete', '设备人员移除', `/${encodeURIComponent(id)}`, 'DELETE')
}

export async function assignRoles(personnelId: string, data: AssignRolesInput) {
  return personnelMutation('assignRoles', '设备人员角色分配', `/${encodeURIComponent(personnelId)}/roles`, 'POST', data)
}

export async function assignCategories(personnelId: string, data: AssignCategoriesInput) {
  return personnelMutation('assignCategories', '设备人员分类保存', `/${encodeURIComponent(personnelId)}/categories`, 'POST', data)
}

export async function refreshFeishu() {
  return personnelMutation('refreshFeishu', '设备人员飞书信息刷新', '/refresh-feishu', 'POST')
}
