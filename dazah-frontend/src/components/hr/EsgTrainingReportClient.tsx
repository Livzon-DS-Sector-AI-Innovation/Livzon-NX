'use client'

import { useCallback, useEffect, useState, type Key } from 'react'
import { App, Button, Form, Input, InputNumber, Modal, Popconfirm, Select, Space, Table, DatePicker } from 'antd'
import { EditOutlined, DeleteOutlined, FilterOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { HR_DISPLAY_DATE_FORMAT } from '@/lib/dayjs-config'
import type { EsgTrainingRecord } from '@/types/hr'
import { fetchEsgRecordsByDept, fetchEsgFilterOptions, type EsgRecordFilters } from '@/lib/api/hr'
import { updateEsgTrainingRecord, deleteEsgTrainingRecord } from '@/actions/hr'

interface Props {
  department: string
  dateFrom: string
  dateTo: string
  periodLabel: string
  printRequest: number
}

// 与后端导出 Excel 一致的列（17 列，对齐 ESG 培训报表模板；IS_INSIDE 系统无数据，打印留空）
const PRINT_HEADERS = [
  '培训日期', '培训名称', '培训方式', '口径', '培训类型', '姓名',
  '员工账号', '身份所属地', '部门', '层级', '性别', '年龄',
  '培训时长(h)', '是否通过本次培训成功实现晋升', '备注', '单位名称', '单位编码',
]
const PRINT_FIELDS: (keyof EsgTrainingRecord | null)[] = [
  'training_date', 'training_name', 'training_method', 'caliber',
  'training_type', 'employee_name', 'employee_account', 'location_address',
  'department', 'employee_level', 'gender', 'age', 'duration',
  null, // IS_INSIDE（是否通过本次培训成功实现晋升）系统无数据，打印留空
  'remarks', 'apply_company', 'apply_company_no',
]
// 模板培训类型下拉 9 项（与后端导出 _ESG_TRAINING_TYPES 一致）
const TRAINING_TYPE_OPTIONS = [
  'EHS类', '质量类', '商业道德反贪腐', '负责任营销', '数据安全、隐私保护',
  '领导力', '管理类', '多元化', '女性领导力发展计划',
]

// 拉取某部门筛选范围内的全量 ESG 记录（循环分页直到取完），供打印使用
async function fetchAllEsgRecords(
  dept: string,
  dateFrom: string,
  dateTo: string,
  filters?: EsgRecordFilters
): Promise<EsgTrainingRecord[]> {
  const all: EsgTrainingRecord[] = []
  const pageSize = 1000
  let p = 1
  for (;;) {
    const res = await fetchEsgRecordsByDept(
      dept,
      p,
      pageSize,
      dateFrom || undefined,
      dateTo || undefined,
      filters
    )
    const rows = res.data || []
    all.push(...rows)
    const total = res.meta?.total ?? all.length
    if (all.length >= total || rows.length === 0) break
    p += 1
  }
  return all
}

// ── 列头筛选面板公共类型 ──
interface FilterDropdownRenderProps {
  selectedKeys: Key[]
  setSelectedKeys: (keys: Key[]) => void
  confirm: () => void
  clearFilters?: () => void
}

export default function EsgTrainingReportClient({ department, dateFrom, dateTo, periodLabel, printRequest }: Props) {
  const { message } = App.useApp()
  const [records, setRecords] = useState<EsgTrainingRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [editingRecord, setEditingRecord] = useState<EsgTrainingRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(50)
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState<EsgRecordFilters>({})
  const [filterOptions, setFilterOptions] = useState<Record<string, string[]>>({})
  const [form] = Form.useForm()

  const activeFilterCount = Object.values(filters).filter(
    (v) => v !== undefined && v !== ''
  ).length

  const applyFilters = useCallback((patch: EsgRecordFilters) => {
    setFilters((prev) => ({ ...prev, ...patch }))
  }, [])

  const loadData = useCallback(async (p = 1) => {
    setLoading(true)
    try {
      const res = await fetchEsgRecordsByDept(
        department,
        p,
        pageSize,
        dateFrom || undefined,
        dateTo || undefined,
        filters
      )
      setRecords(res.data || [])
      setTotal(res.meta?.total ?? (res.data?.length || 0))
      setPage(p)
    } catch (e) {
      message.error('加载失败: ' + ((e instanceof Error ? e.message : '') || '未知错误'))
    } finally {
      setLoading(false)
    }
  }, [department, dateFrom, dateTo, pageSize, filters, message])

  // 枚举列筛选选项：部门/日期范围内去重
  useEffect(() => {
    fetchEsgFilterOptions(department, dateFrom || undefined, dateTo || undefined)
      .then((opts) => setFilterOptions(opts))
      .catch(() => setFilterOptions({}))
  }, [department, dateFrom, dateTo])

  // 部门或筛选日期变化 → 回到第一页重新加载（服务端分页 + 服务端日期过滤）
  useEffect(() => {
    // 依赖变化时同步回到第一页加载：loadData 内部 setLoading 为首个同步步骤
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadData(1)
  }, [loadData])

  // 按导出内容打印：新窗口渲染与导出 Excel 一致的表格后调起打印（含当前列筛选）
  const doPrint = async () => {
    const all = await fetchAllEsgRecords(department, dateFrom, dateTo, filters)
    if (all.length === 0) {
      message.warning('当前筛选范围内没有数据')
      return
    }
    const title = `${department} ESG培训报表${periodLabel ? `（${periodLabel}）` : ''}`
    const esc = (v: unknown) =>
      String(v ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const headerHtml = PRINT_HEADERS.map((h) => `<th>${esc(h)}</th>`).join('')
    const bodyHtml = all
      .map((r) => `<tr>${PRINT_FIELDS.map((f) => `<td>${esc(f ? r[f] ?? '' : '')}</td>`).join('')}</tr>`)
      .join('')
    const w = window.open('', '_blank')
    if (!w) {
      message.error('浏览器拦截了弹出窗口，请允许后重试')
      return
    }
    w.document.write(`<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>${esc(title)}</title>
<style>
  @page { size: A4 landscape; margin: 10mm; }
  body { font-family: "Microsoft YaHei", sans-serif; font-size: 11px; }
  h2 { text-align: center; font-size: 16px; margin: 0 0 10px; }
  table { width: 100%; border-collapse: collapse; }
  th, td { border: 1px solid #000; padding: 4px 5px; text-align: center; word-break: break-all; }
  th { background: #f0f0f0; font-weight: bold; }
</style></head><body>
<h2>${esc(title)}</h2>
<table><thead><tr>${headerHtml}</tr></thead><tbody>${bodyHtml}</tbody></table>
</body></html>`)
    w.document.close()
    w.focus()
    w.print()
  }

  useEffect(() => {
    if (printRequest > 0) void doPrint()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [printRequest])

  const handleEdit = (record: EsgTrainingRecord) => {
    setEditingRecord(record)
    form.setFieldsValue({ ...record, training_date: record.training_date ? dayjs(record.training_date) : null })
  }

  const handleSave = async () => {
    const values = await form.validateFields()
    setSaving(true)
    try {
      const payload = {
        ...editingRecord,
        ...values,
        training_date: values.training_date ? values.training_date.format('YYYY-MM-DD') : undefined,
      }
      await updateEsgTrainingRecord(editingRecord!.id, payload)
      message.success('更新成功')
      setEditingRecord(null)
      loadData(page)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteEsgTrainingRecord(id)
      message.success('删除成功')
      loadData(page)
    } catch (e) {
      message.error((e instanceof Error ? e.message : '') || '删除失败')
    }
  }

  // ── 列头筛选：文本包含 / 枚举单选 / 数值区间（均走服务端查询）──
  const isActive = (v: unknown) => v !== undefined && v !== ''

  const textFilter = (field: keyof EsgRecordFilters, placeholder: string) => ({
    filterDropdown: ({ selectedKeys, setSelectedKeys, confirm }: FilterDropdownRenderProps) => (
      <div style={{ padding: 8 }} onKeyDown={(e) => e.stopPropagation()}>
        <Input
          value={(selectedKeys[0] as string) || ''}
          placeholder={placeholder}
          allowClear
          style={{ width: 180, marginBottom: 8, display: 'block' }}
          onChange={(e) => setSelectedKeys(e.target.value ? [e.target.value] : [])}
          onPressEnter={() => {
            applyFilters({ [field]: (selectedKeys[0] as string) || undefined })
            confirm()
          }}
        />
        <Space>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              applyFilters({ [field]: (selectedKeys[0] as string) || undefined })
              confirm()
            }}
          >
            筛选
          </Button>
          <Button
            size="small"
            onClick={() => {
              setSelectedKeys([])
              applyFilters({ [field]: undefined })
              confirm()
            }}
          >
            清除
          </Button>
        </Space>
      </div>
    ),
    filterIcon: () => <FilterOutlined style={{ color: isActive(filters[field]) ? '#1677ff' : undefined }} />,
  })

  const enumFilter = (field: keyof EsgRecordFilters, options: string[]) => ({
    filterDropdown: ({ selectedKeys, setSelectedKeys, confirm }: FilterDropdownRenderProps) => (
      <div style={{ padding: 8 }} onKeyDown={(e) => e.stopPropagation()}>
        <Select
          style={{ width: 180, marginBottom: 8, display: 'block' }}
          placeholder="选择"
          allowClear
          showSearch
          optionFilterProp="label"
          value={(selectedKeys[0] as string) || undefined}
          options={options.map((o) => ({ value: o, label: o }))}
          onChange={(v) => setSelectedKeys(v ? [v] : [])}
        />
        <Space>
          <Button
            type="primary"
            size="small"
            onClick={() => {
              applyFilters({ [field]: (selectedKeys[0] as string) || undefined })
              confirm()
            }}
          >
            筛选
          </Button>
          <Button
            size="small"
            onClick={() => {
              setSelectedKeys([])
              applyFilters({ [field]: undefined })
              confirm()
            }}
          >
            清除
          </Button>
        </Space>
      </div>
    ),
    filterIcon: () => <FilterOutlined style={{ color: isActive(filters[field]) ? '#1677ff' : undefined }} />,
  })

  const numberRangeFilter = (field: 'age' | 'duration', label: string) => {
    const minField = `${field}_min` as keyof EsgRecordFilters
    const maxField = `${field}_max` as keyof EsgRecordFilters
    const active = isActive(filters[minField]) || isActive(filters[maxField])
    return {
      filterDropdown: ({ selectedKeys, setSelectedKeys, confirm }: FilterDropdownRenderProps) => {
        const [minStr, maxStr] = String(selectedKeys[0] ?? '').split(',')
        const toNum = (v: string) => (v === '' || v === undefined ? undefined : Number(v))
        return (
          <div style={{ padding: 8 }} onKeyDown={(e) => e.stopPropagation()}>
            <div className="mb-2 flex items-center gap-1">
              <InputNumber
                size="small"
                min={0}
                placeholder="最小"
                style={{ width: 82 }}
                value={minStr ? Number(minStr) : undefined}
                onChange={(v) => setSelectedKeys([`${v ?? ''},${maxStr ?? ''}`])}
              />
              <span className="text-gray-400">~</span>
              <InputNumber
                size="small"
                min={0}
                placeholder="最大"
                style={{ width: 82 }}
                value={maxStr ? Number(maxStr) : undefined}
                onChange={(v) => setSelectedKeys([`${minStr ?? ''},${v ?? ''}`])}
              />
            </div>
            <Space>
              <Button
                type="primary"
                size="small"
                onClick={() => {
                  applyFilters({ [minField]: toNum(minStr), [maxField]: toNum(maxStr) })
                  confirm()
                }}
              >
                筛选
              </Button>
              <Button
                size="small"
                onClick={() => {
                  setSelectedKeys([])
                  applyFilters({ [minField]: undefined, [maxField]: undefined })
                  confirm()
                }}
              >
                清除
              </Button>
            </Space>
            <span className="sr-only">{label}</span>
          </div>
        )
      },
      filterIcon: () => <FilterOutlined style={{ color: active ? '#1677ff' : undefined }} />,
    }
  }

  const clearAllFilters = () => setFilters({})

  const columns = [
    { title: '培训日期', dataIndex: 'training_date', width: 110, render: (v: string) => v ? dayjs(v).format(HR_DISPLAY_DATE_FORMAT) : '-' },
    {
      title: '培训名称', dataIndex: 'training_name', width: 300,
      ...textFilter('training_name', '搜索培训名称'),
    },
    {
      title: '培训方式', dataIndex: 'training_method', width: 90,
      ...enumFilter('training_method', filterOptions.training_method?.length ? filterOptions.training_method : ['线上', '线下']),
    },
    {
      title: '口径', dataIndex: 'caliber', width: 80,
      ...enumFilter('caliber', filterOptions.caliber?.length ? filterOptions.caliber : ['公司组织', '部门组织']),
    },
    {
      title: '培训类型', dataIndex: 'training_type', width: 90,
      ...enumFilter('training_type', filterOptions.training_type?.length ? filterOptions.training_type : TRAINING_TYPE_OPTIONS),
    },
    {
      title: '姓名', dataIndex: 'employee_name', width: 80,
      ...textFilter('employee_name', '搜索姓名'),
    },
    {
      title: '员工账号', dataIndex: 'employee_account', width: 100,
      ...textFilter('employee_account', '搜索员工账号'),
    },
    {
      title: '身份所属地', dataIndex: 'location_address', width: 100,
      ...enumFilter('location_address', filterOptions.location_address?.length ? filterOptions.location_address : ['中国大陆']),
    },
    { title: '部门', dataIndex: 'department', width: 120 },
    {
      title: '层级', dataIndex: 'employee_level', width: 80,
      ...enumFilter('employee_level', filterOptions.employee_level ?? []),
    },
    {
      title: '性别', dataIndex: 'gender', width: 60,
      ...enumFilter('gender', filterOptions.gender?.length ? filterOptions.gender : ['男', '女']),
    },
    {
      title: '年龄', dataIndex: 'age', width: 60,
      ...numberRangeFilter('age', '年龄'),
    },
    {
      title: '培训时长(h)', dataIndex: 'duration', width: 80,
      ...numberRangeFilter('duration', '时长'),
    },
    { title: '是否通过本次培训成功实现晋升', dataIndex: 'is_inside', width: 140, render: () => '-' },
    {
      title: '备注', dataIndex: 'remarks', width: 150, ellipsis: true,
      ...textFilter('remarks', '搜索备注'),
    },
    {
      title: '单位名称', dataIndex: 'apply_company', width: 120, ellipsis: true,
      ...textFilter('apply_company', '搜索单位名称'),
    },
    {
      title: '单位编码', dataIndex: 'apply_company_no', width: 100,
      ...textFilter('apply_company_no', '搜索单位编码'),
    },
    {
      title: '操作', width: 140, fixed: 'right' as const,
      render: (_: unknown, record: EsgTrainingRecord) => (
        <div className="no-print flex gap-2">
          <Button size="small" icon={<EditOutlined />} onClick={() => handleEdit(record)}>编辑</Button>
          <Popconfirm title="删除?" onConfirm={() => handleDelete(record.id)}>
            <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
          </Popconfirm>
        </div>
      ),
    },
  ]

  return (
    <>
      {activeFilterCount > 0 && (
        <div className="no-print mb-2 flex items-center gap-2 text-sm text-gray-600">
          <FilterOutlined style={{ color: '#1677ff' }} />
          <span>已启用 {activeFilterCount} 项列筛选</span>
          <Button size="small" onClick={clearAllFilters}>清空筛选</Button>
        </div>
      )}
      <Table
        rowKey="id"
        dataSource={records}
        columns={columns}
        loading={loading}
        scroll={{ x: 2000 }}
        size="small"
        pagination={{
        current: page,
        pageSize,
        total,
        showTotal: (t: number) => `共 ${t} 条`,
        showSizeChanger: false,
        onChange: (p: number) => loadData(p),
      }} />

      <Modal title="编辑ESG培训记录" open={!!editingRecord} onCancel={() => setEditingRecord(null)} onOk={handleSave} confirmLoading={saving} width={640}>
        <Form form={form} layout="vertical">
          <Form.Item name="training_name" label="培训名称" rules={[{ required: true }]}>
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="training_date" label="培训日期">
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="training_method" label="培训方式">
            <Select options={[
              { value: '线上', label: '线上' }, { value: '线下', label: '线下' },
            ]} />
          </Form.Item>
          <Form.Item name="caliber" label="口径">
            <Select options={[
              { value: '公司组织', label: '公司组织' }, { value: '部门组织', label: '部门组织' },
            ]} />
          </Form.Item>
          <Form.Item name="training_type" label="培训类型">
            <Select options={TRAINING_TYPE_OPTIONS.map((v) => ({ value: v, label: v }))} />
          </Form.Item>
          <Form.Item name="employee_name" label="姓名" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="employee_account" label="员工账号"><Input /></Form.Item>
          <Form.Item name="location_address" label="身份所属地"><Input /></Form.Item>
          <Form.Item name="department" label="部门"><Input /></Form.Item>
          <Form.Item name="employee_level" label="层级"><Input /></Form.Item>
          <Form.Item name="gender" label="性别">
            <Select options={[{ value: '男', label: '男' }, { value: '女', label: '女' }]} />
          </Form.Item>
          <Form.Item name="age" label="年龄"><InputNumber min={0} max={200} /></Form.Item>
          <Form.Item name="duration" label="培训时长"><InputNumber min={0} step={0.5} /></Form.Item>
          <Form.Item name="remarks" label="备注"><Input.TextArea rows={2} /></Form.Item>
          <Form.Item name="apply_company" label="单位名称"><Input /></Form.Item>
          <Form.Item name="apply_company_no" label="单位编码"><Input /></Form.Item>
        </Form>
      </Modal>
    </>
  )
}
