/** Role identity colors; gray is reserved for unassigned or unknown roles. */
export function roleTagColor(code: string, isSystem = false): string {
  if (code === 'super_admin') return 'purple'
  if (code === 'ordinary_admin') return 'blue'
  return isSystem ? 'gold' : 'green'
}
