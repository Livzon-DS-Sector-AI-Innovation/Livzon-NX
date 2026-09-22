type Contact = { open_id?: string | null; name?: string | null; department?: string | null }

/** 飞书不同应用的 open_id 不同；仅在人员目录能唯一匹配时回填选择项。 */
export function personSelectValue(contacts: Contact[], name?: string | null, department?: string | null): string {
  const matches = contacts.filter(person => person.name === name && (!department || person.department === department))
  return matches.length === 1 ? matches[0].open_id || name || '' : name || ''
}
