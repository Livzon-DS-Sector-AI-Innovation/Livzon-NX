'use client'

import { useMemo } from 'react'
import { Select } from 'antd'
import { useQuery } from '@tanstack/react-query'
import { pinyin } from 'pinyin-pro'
import { fetchValidationPersonOptions } from '@/lib/api/client/quality'

export interface FeishuPersonValue {
  /** open_id（人事管理-飞书联系人）或多维表格成员字段回显 id，提交后由后端反查写入 */
  id: string
  name: string
  /** 邮箱/手机号：跨应用 id 换算（batch_get_id）用 */
  email?: string
  mobile?: string
  /** true = id 来自飞书记录回读（对目标 Base 有效），后端无需换发 union_id */
  resolved?: boolean
}

interface FeishuPersonSelectProps {
  value?: FeishuPersonValue[] | FeishuPersonValue | null
  onChange?: (value: FeishuPersonValue[] | FeishuPersonValue | undefined) => void
  /** 多选（人员）；默认单选（负责人） */
  multiple?: boolean
  /** 编辑回显：记录里已有的人员（id 可能是多维表格成员 id，不在通讯录选项中） */
  extraOptions?: FeishuPersonValue[]
  placeholder?: string
  disabled?: boolean
}

interface LabeledValue {
  value: string
  label: string
}

interface PersonCatalogEntry {
  name: string
  department: string | null
  email: string | null
  mobile: string | null
  resolved: boolean
}

function toLabeled(selected: FeishuPersonSelectProps['value']): LabeledValue | LabeledValue[] | undefined {
  if (!selected) return undefined
  if (Array.isArray(selected)) {
    return selected.map((person) => ({ value: person.id, label: person.name }))
  }
  return { value: selected.id, label: selected.name }
}

/** 飞书人员选择器：候选来自人事管理-飞书联系人（在职），支持中文/全拼/首字母搜索 */
export function FeishuPersonSelect({
  value,
  onChange,
  multiple = false,
  extraOptions,
  placeholder,
  disabled,
}: FeishuPersonSelectProps) {
  const { data: directory = [], isLoading } = useQuery({
    queryKey: ['quality-person-directory'],
    queryFn: () => fetchValidationPersonOptions(undefined, 500),
    // 不做前端缓存：每次打开都重查，保证人事-飞书联系人同步后立刻生效
    staleTime: 0,
  })

  // id → {姓名, 部门, resolved}：选项展示带部门便于区分重名，提交时仍取纯姓名
  const catalog = useMemo(() => {
    const map = new Map<string, PersonCatalogEntry>()
    for (const person of directory) {
      if (person.open_id && !map.has(person.open_id)) {
        map.set(person.open_id, {
          name: person.name,
          department: person.department,
          email: person.email,
          mobile: person.mobile,
          resolved: false,
        })
      }
    }
    for (const person of extraOptions ?? []) {
      if (person.id && !map.has(person.id)) {
        map.set(person.id, {
          name: person.name || person.id,
          department: null,
          email: person.email ?? null,
          mobile: person.mobile ?? null,
          resolved: person.resolved ?? false,
        })
      }
    }
    return map
  }, [directory, extraOptions])

  const options = useMemo(
    () =>
      Array.from(catalog.entries()).map(([id, entry]) => {
        const py = pinyin(entry.name, { toneType: 'none' }).replace(/\s/g, '').toLowerCase()
        const pyf = pinyin(entry.name, { pattern: 'first', toneType: 'none' })
          .replace(/\s/g, '')
          .toLowerCase()
        return {
          value: id,
          label: entry.department ? `${entry.name}（${entry.department}）` : entry.name,
          name: entry.name,
          py,
          pyf,
        }
      }),
    [catalog],
  )

  const resolvePersons = (selected: LabeledValue | LabeledValue[] | undefined) => {
    if (selected === undefined) return undefined
    const toPerson = (item: LabeledValue): FeishuPersonValue => {
      const entry = catalog.get(item.value)
      return {
        id: item.value,
        name: entry?.name ?? item.label,
        email: entry?.email ?? undefined,
        mobile: entry?.mobile ?? undefined,
        resolved: entry?.resolved,
      }
    }
    return Array.isArray(selected) ? selected.map(toPerson) : toPerson(selected)
  }

  const handleLabeledChange = (selected: LabeledValue | LabeledValue[] | undefined) => {
    onChange?.(resolvePersons(selected))
  }

  return (
    <Select<LabeledValue | LabeledValue[]>
      mode={multiple ? 'multiple' : undefined}
      labelInValue
      value={toLabeled(value as FeishuPersonSelectProps['value'])}
      onChange={handleLabeledChange}
      showSearch
      allowClear
      disabled={disabled}
      loading={isLoading}
      placeholder={placeholder || '输入姓名或拼音搜索人员'}
      style={{ width: '100%' }}
      options={options}
      filterOption={(input, option) => {
        const keyword = input.trim().toLowerCase()
        if (!keyword) return true
        const label = String(option?.label ?? '')
        return (
          label.toLowerCase().includes(keyword) ||
          (option?.name as string | undefined)?.toLowerCase().includes(keyword) ||
          (option?.py as string | undefined)?.includes(keyword) ||
          (option?.pyf as string | undefined)?.includes(keyword) ||
          false
        )
      }}
    />
  )
}

export default FeishuPersonSelect
