import { expect, it } from 'vitest'
import { roleTagColor } from './role-tag'

it.each([
  ['super_admin', true, 'purple'],
  ['super_admin', false, 'purple'],
  ['ordinary_admin', true, 'blue'],
  ['ordinary_admin', false, 'blue'],
  ['material_qa', true, 'gold'],
  ['custom_role', false, 'green'],
  ['user', false, 'green'],
])('maps %s (built-in: %s) to a consistent identity color', (code, isSystem, color) => {
  expect(roleTagColor(code, isSystem)).toBe(color)
})
