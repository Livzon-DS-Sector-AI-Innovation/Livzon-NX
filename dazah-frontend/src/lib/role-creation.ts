export const ROLE_NAME_MAX_LENGTH = 100
export const ROLE_CODE_MAX_LENGTH = 64

export function trimRoleWhitespace(value: string) {
  return value.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, "")
}

export function roleNameError(value: unknown) {
  const name = typeof value === "string" ? trimRoleWhitespace(value) : ""
  if (!name) return "请输入角色名称"
  if (/\p{White_Space}/u.test(name)) return "角色名称中间不能有空白"
  if (Array.from(name).length > ROLE_NAME_MAX_LENGTH) return `角色名称最多 ${ROLE_NAME_MAX_LENGTH} 个字符`
}

export function roleCodeError(value: unknown) {
  const code = typeof value === "string" ? trimRoleWhitespace(value) : ""
  if (!code) return "请输入角色标识"
  if (/\p{White_Space}/u.test(code)) return "角色标识中间不能有空白"
  if (/[^A-Za-z0-9_.:-]/u.test(code)) return "角色标识只能使用英文字母、数字和 _ . : -"
  if (code.length > ROLE_CODE_MAX_LENGTH) return `角色标识最多 ${ROLE_CODE_MAX_LENGTH} 个字符`
}
