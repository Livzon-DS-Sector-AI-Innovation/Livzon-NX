import type { components } from '@/types/generated/schema'

export type User = Pick<
  components['schemas']['UserResponse'],
  | 'id'
  | 'name'
  | 'username'
  | 'role'
  | 'status'
  | 'auth_source'
  | 'email'
  | 'mobile'
  | 'avatar_url'
  | 'employee_no'
  | 'department'
  | 'position'
  | 'module_codes'
  | 'permissions'
  | 'roles'
  | 'page_permissions'
  | 'page_permission_rollouts'
  | 'grant_version'
>
