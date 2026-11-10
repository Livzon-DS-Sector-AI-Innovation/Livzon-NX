import { useId, useState } from 'react'
import { Button, ConfigProvider, Input, Select, theme } from 'antd'
import { SearchOutlined } from '@ant-design/icons'
import type { EmployeeFilterOptions } from '@/lib/api/hr'
import { readEmployeeProfileFilters, type EmployeeProfileFilters } from './employeeProfileQuery'

interface EmployeeProfileFilterBarProps {
  filters: EmployeeProfileFilters
  options: EmployeeFilterOptions
  loadingOptions: boolean
  optionsFailed: boolean
  onRetryOptions: () => void
  onSubmit: (filters: EmployeeProfileFilters) => void
}

const textFields = [
  { name: 'keyword', label: '姓名 / 工号', placeholder: '输入姓名或工号' },
  { name: 'position', label: '职务 / 岗位', placeholder: '输入职务或岗位' },
] as const

function selectOptions(values: readonly (string | null)[], sort: boolean) {
  const items = [...new Set(values)].flatMap(value => value ? [{ label: value, value }] : [])
  return sort ? items.sort((a, b) => a.label.localeCompare(b.label, 'zh-CN')) : items
}

export default function EmployeeProfileFilterBar({
  filters,
  options,
  loadingOptions,
  optionsFailed,
  onRetryOptions,
  onSubmit,
}: EmployeeProfileFilterBarProps) {
  const id = useId()
  const { token } = theme.useToken()
  const [draft, setDraft] = useState(filters)
  const departmentPairs = options.departments.filter(
    pair => !draft.department || pair.department === draft.department,
  )
  const selectFields = [
    { name: 'department', label: '一级部门', values: options.departments.map(pair => pair.department), dynamic: true },
    { name: 'sub_department', label: '二级部门', values: departmentPairs.map(pair => pair.sub_department), dynamic: true },
    { name: 'gender', label: '性别', values: ['男', '女'], dynamic: false },
    { name: 'level', label: '职级', values: options.levels, dynamic: true },
    { name: 'education', label: '学历', values: options.educations, dynamic: true },
    { name: 'status', label: '在职状态', values: ['在职', '正式', '试用期', '实习生', '转正实习生', '离职', '待审批'], dynamic: false },
  ] as const
  const labelClass = 'mb-1 block text-sm font-medium text-[var(--color-charcoal)]'

  const updateDraft = (name: keyof EmployeeProfileFilters, value?: string) => {
    setDraft(previous => ({
      ...previous,
      [name]: value,
      ...(name === 'department' && previous.department !== value ? { sub_department: undefined } : {}),
    }))
  }

  return (
    <ConfigProvider theme={{ token: { colorTextPlaceholder: token.colorTextSecondary } }}>
      <form
        aria-label="员工档案筛选"
        className="grid grid-cols-2 items-end gap-3 @3xl:grid-cols-5 @7xl:grid-cols-[repeat(8,minmax(0,1fr))_auto]"
        onSubmit={event => {
          event.preventDefault()
          const applied = readEmployeeProfileFilters(key => draft[key])
          setDraft(applied)
          onSubmit(applied)
        }}
      >
        {textFields.map(({ name, label, placeholder }) => (
          <div key={name} className="min-w-0">
            <label htmlFor={`${id}-${name}`} className={labelClass}>{label}</label>
            <Input
              id={`${id}-${name}`}
              placeholder={placeholder}
              value={draft[name] ?? ''}
              maxLength={64}
              onChange={event => updateDraft(name, event.target.value)}
              allowClear
            />
          </div>
        ))}
        {selectFields.map(({ name, label, values, dynamic }) => (
          <div key={name} className="min-w-0">
            <label htmlFor={`${id}-${name}`} className={labelClass}>{label}</label>
            <Select<string | undefined>
              id={`${id}-${name}`}
              aria-label={label}
              className="w-full"
              placeholder={name === 'status' ? '默认状态' : '不限'}
              value={draft[name]}
              onChange={value => updateDraft(name, value)}
              options={selectOptions(values, dynamic)}
              showSearch={dynamic ? { optionFilterProp: 'label' } : false}
              popupMatchSelectWidth={dynamic ? false : undefined}
              loading={dynamic && loadingOptions}
              notFoundContent={dynamic && loadingOptions ? '加载中…' : '暂无可选项'}
              allowClear
            />
          </div>
        ))}
        <div className="col-span-2 flex flex-wrap gap-2 @7xl:col-span-1">
          <Button htmlType="submit" icon={<SearchOutlined />}>查询</Button>
          <Button onClick={() => {
            setDraft({})
            onSubmit(readEmployeeProfileFilters(() => undefined))
          }}>重置</Button>
        </div>
        {optionsFailed && (
          <Button className="col-span-full justify-self-start" type="link" onClick={onRetryOptions}>
            重试加载筛选选项
          </Button>
        )}
      </form>
    </ConfigProvider>
  )
}
