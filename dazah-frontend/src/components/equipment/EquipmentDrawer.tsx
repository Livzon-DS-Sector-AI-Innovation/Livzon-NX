'use client'

import { useState, useEffect, useRef } from 'react'
import { App, Drawer, Form, Input, Select, DatePicker, Button, Space } from 'antd'
import dayjs from 'dayjs'
import { useEquipmentStore } from '@/stores/equipment'
import { EquipmentStatus, EquipmentImportance, EquipmentCategory, Location } from '@/types/equipment'
import { createEquipment, updateEquipment } from '@/actions/equipment'

const { TextArea } = Input

const importanceOptions: { label: string; value: EquipmentImportance }[] = [
  { label: '高', value: '高' },
  { label: '中', value: '中' },
  { label: '低', value: '低' },
]

const statusOptions: { label: string; value: EquipmentStatus }[] = [
  { label: '在用', value: '在用' },
  { label: '备用', value: '备用' },
  { label: '维修中', value: '维修中' },
  { label: '停用', value: '停用' },
  { label: '报废', value: '报废' },
]

// 技术参数 JSON 对象 → 表单文本（每行“参数名：参数值”）
export function formatTechParams(
  params: Record<string, unknown> | null | undefined,
): string | undefined {
  if (!params || Object.keys(params).length === 0) return undefined
  return Object.entries(params)
    .map(([key, value]) => `${key}：${String(value)}`)
    .join('\n')
}

// 技术参数文本（每行“参数名：值”）→ JSON 对象；空文本返回 undefined
export function parseTechParams(text?: string): Record<string, string> | undefined {
  if (!text?.trim()) return undefined
  const result: Record<string, string> = {}
  for (const [index, line] of text.split('\n').entries()) {
    const trimmed = line.trim()
    if (!trimmed) continue
    const match = trimmed.match(/^([^:=：]+)[:：=](.*)$/)
    if (!match) {
      throw new Error(`技术参数第 ${index + 1} 行格式不正确，请按“参数名：参数值”逐行填写`)
    }
    result[match[1].trim()] = match[2].trim()
  }
  return Object.keys(result).length > 0 ? result : undefined
}

// 扁平化树结构
function flattenCategories(categories: EquipmentCategory[], prefix = ''): { label: string; value: string }[] {
  const result: { label: string; value: string }[] = []
  for (const cat of categories) {
    const label = prefix ? `${prefix} / ${cat.name}` : cat.name
    result.push({ label, value: cat.id })
    if (cat.children?.length) {
      result.push(...flattenCategories(cat.children, label))
    }
  }
  return result
}

function flattenLocations(locations: Location[], prefix = ''): { label: string; value: string }[] {
  const result: { label: string; value: string }[] = []
  for (const loc of locations) {
    const label = prefix ? `${prefix} / ${loc.name}` : loc.name
    result.push({ label, value: loc.id })
    if (loc.children?.length) {
      result.push(...flattenLocations(loc.children, label))
    }
  }
  return result
}

interface StaffOption {
  id: string
  name: string
  employee_no: string | null
  department: string | null
}

interface EquipmentDrawerProps {
  onRefresh?: () => void
}

export function EquipmentDrawer({ onRefresh }: EquipmentDrawerProps) {
  const [form] = Form.useForm()
  const { message } = App.useApp()
  const [submitting, setSubmitting] = useState(false)
  const [staffKeyword, setStaffKeyword] = useState('')
  const [staffOptions, setStaffOptions] = useState<{ label: string; value: string }[]>([])
  const [staffLoading, setStaffLoading] = useState(false)
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const {
    equipmentDrawerOpen,
    editingEquipment,
    closeEquipmentDrawer,
    categories,
    locations,
    departments,
  } = useEquipmentStore()

  const categoryOptions = flattenCategories(categories)
  const locationOptions = flattenLocations(locations)

  // 搜索员工：输入关键字后延迟 300ms 从 identity/personnel 查询
  const handleStaffSearch = (value: string) => {
    setStaffKeyword(value)
    if (searchTimer.current) clearTimeout(searchTimer.current)
    if (!value.trim()) {
      setStaffOptions([])
      return
    }
    searchTimer.current = setTimeout(async () => {
      setStaffLoading(true)
      try {
        const params = new URLSearchParams({ limit: '50', keyword: value.trim() })
        const resp = await fetch(`/api/v1/identity/personnel?${params}`)
        if (!resp.ok) { setStaffOptions([]); return }
        const json = await resp.json()
        const items = (json.data?.items ?? []) as Record<string, unknown>[]
        setStaffOptions(items.map(u => ({
          label: `${String(u.name ?? '')}${u.department ? ` - ${String(u.department)}` : ''}${u.employee_no ? ` (${String(u.employee_no)})` : ''}`,
          value: String(u.id),
        })))
      } catch {
        setStaffOptions([])
      } finally {
        setStaffLoading(false)
      }
    }, 300)
  }

  useEffect(() => {
    if (equipmentDrawerOpen) {
      if (editingEquipment) {
        // 编辑模式：用后端返回的 responsible_person_name 直接构造初始选项
        const initialOptions: { label: string; value: string }[] = []
        if (editingEquipment.responsible_person_id && editingEquipment.responsible_person_name) {
          initialOptions.push({
            label: editingEquipment.responsible_person_name,
            value: editingEquipment.responsible_person_id,
          })
        }
        setStaffOptions(initialOptions)

        form.setFieldsValue({
          name: editingEquipment.name,
          equipment_no: editingEquipment.equipment_no,
          category_ids: editingEquipment.category_ids || [],
          location_id: editingEquipment.location_id,
          status: editingEquipment.status,
          model: editingEquipment.model ?? undefined,
          manufacturer: editingEquipment.manufacturer ?? undefined,
          production_date: editingEquipment.production_date ? dayjs(editingEquipment.production_date) : undefined,
          factory_no: editingEquipment.factory_no ?? undefined,
          arrival_date: editingEquipment.arrival_date ? dayjs(editingEquipment.arrival_date) : undefined,
          technical_params_text: formatTechParams(editingEquipment.technical_params),
          description: editingEquipment.description ?? undefined,
          department_id: editingEquipment.department_id ?? undefined,
          responsible_person_id: editingEquipment.responsible_person_id ?? undefined,
          importance: editingEquipment.importance ?? '低',
        })
      } else {
        form.resetFields()
        setStaffOptions([])
      }
    }
  }, [equipmentDrawerOpen, editingEquipment, form])

  // 选择部门后自动填入负责人（默认为部门负责人，但可手动修改）
  const handleDepartmentChange = (deptId: string | undefined) => {
    if (!deptId) {
      form.setFieldsValue({ responsible_person_id: undefined })
      return
    }
    const dept = departments.find(d => d.id === deptId)
    if (dept?.leader_id) {
      form.setFieldsValue({ responsible_person_id: dept.leader_id })
      // 同时确保 leader_id 在 staffOptions 中可见
      if (!staffOptions.some(o => o.value === dept.leader_id)) {
        setStaffOptions(prev => [...prev, {
          label: `${dept.leader_name ?? ''}${dept.name ? ` - ${dept.name}` : ''}`,
          value: dept.leader_id!,
        }])
      }
    } else {
      form.setFieldsValue({ responsible_person_id: undefined })
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      setSubmitting(true)
      const submitData = {
        ...values,
        production_date: values.production_date
          ? values.production_date.format('YYYY-MM-DD')
          : undefined,
        arrival_date: values.arrival_date
          ? values.arrival_date.format('YYYY-MM-DD')
          : undefined,
        technical_params: parseTechParams(values.technical_params_text),
        // 人工编辑保存后清除导入时记录的待修正标记
        data_issue_note: null,
      }
      delete (submitData as Record<string, unknown>).technical_params_text

      if (editingEquipment) {
        await updateEquipment(editingEquipment.id, submitData)
        message.success('更新设备成功')
      } else {
        await createEquipment(submitData)
        message.success('创建设备成功')
      }
      closeEquipmentDrawer()
      onRefresh?.()
    } catch (err) {
      // Ant Design validation errors have an errorFields property
      if ((typeof err === 'object' && err !== null && 'errorFields' in err)) return
      message.error((err as { message?: string })?.message || '操作失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Drawer
      title={editingEquipment ? '编辑设备' : '新增设备'}
      size={480}
      open={equipmentDrawerOpen}
      onClose={closeEquipmentDrawer}
      destroyOnHidden
      styles={{
        header: { borderBottom: '1px solid #e5e3df', padding: '16px 24px' },
        body: { padding: '24px' },
      }}
      extra={
        <Space>
          <Button onClick={closeEquipmentDrawer}>取消</Button>
          <Button type="primary" loading={submitting} onClick={handleSubmit}>
            保存
          </Button>
        </Space>
      }
    >
      <Form
        form={form}
        layout="vertical"
        requiredMark="optional"
        styles={{ label: { fontWeight: 500, color: '#1a1a1a' } }}
      >
        {editingEquipment?.data_issue_note && (
          <div
            style={{
              marginBottom: 16,
              padding: '8px 12px',
              borderRadius: 8,
              border: '1px solid #f5b7b1',
              background: '#fdedec',
              color: '#c0392b',
              fontSize: 13,
              lineHeight: '20px',
            }}
          >
            <strong>数据待修正：</strong>
            {editingEquipment.data_issue_note}
            <div style={{ marginTop: 4, fontSize: 12, color: '#e74c3c' }}>
              请核对并修正上方相关字段，保存后该提示自动清除。
            </div>
          </div>
        )}
        <Form.Item
          name="name"
          label="设备名称"
          rules={[{ required: true, message: '请输入设备名称' }]}
        >
          <Input placeholder="请输入设备名称" />
        </Form.Item>
        <Form.Item
          name="equipment_no"
          label="设备编号"
          rules={[{ required: true, message: '请输入设备编号' }]}
        >
          <Input placeholder="请输入唯一设备编号" disabled={!!editingEquipment} />
        </Form.Item>
        <Form.Item
          name="category_ids"
          label="设备分类"
          rules={[{ required: true, type: 'array', min: 1, message: '请至少选择一个设备分类' }]}
        >
          <Select
            mode="multiple"
            placeholder="请选择设备分类（支持多选）"
            showSearch
            optionFilterProp="label"
            options={categoryOptions}
          />
        </Form.Item>
        <Form.Item
          name="location_id"
          label="安装地点"
          rules={[{ required: true, message: '请选择安装地点' }]}
        >
          <Select
            placeholder="请选择安装地点"
            showSearch
            optionFilterProp="label"
            options={locationOptions}
          />
        </Form.Item>
        <Form.Item name="department_id" label="归属部门">
          <Select
            placeholder="请选择归属部门"
            allowClear
            showSearch
            optionFilterProp="label"
            options={departments.map(d => ({ label: d.name, value: d.id }))}
            onChange={handleDepartmentChange}
          />
        </Form.Item>
        <Form.Item name="responsible_person_id" label="负责人">
          <Select
            placeholder="选择部门后默认填入部门负责人，也可搜索修改"
            allowClear
            showSearch
            filterOption={false}
            onSearch={handleStaffSearch}
            loading={staffLoading}
            notFoundContent={staffLoading ? '搜索中...' : staffKeyword ? '无匹配人员' : '输入姓名搜索员工'}
            options={staffOptions}
          />
        </Form.Item>
        <Form.Item
          name="status"
          label="设备状态"
          rules={[{ required: true, message: '请选择设备状态' }]}
        >
          <Select placeholder="请选择设备状态" options={statusOptions} />
        </Form.Item>
        <Form.Item
          name="importance"
          label="设备重要性"
          rules={[{ required: true, message: '请选择设备重要性' }]}
        >
          <Select placeholder="请选择设备重要性" options={importanceOptions} />
        </Form.Item>
        <Form.Item name="model" label="规格型号">
          <Input placeholder="请输入规格型号" />
        </Form.Item>
        <Form.Item
          name="technical_params_text"
          label="技术参数"
          rules={[
            {
              validator: (_: unknown, value: string | undefined) => {
                if (!value?.trim()) return Promise.resolve()
                for (const line of value.split('\n')) {
                  if (!line.trim()) continue
                  if (!/^([^:=：]+)[:：=](.*)$/.test(line.trim())) {
                    return Promise.reject(new Error('每行请按“参数名：参数值”格式填写'))
                  }
                }
                return Promise.resolve()
              },
            },
          ]}
        >
          <TextArea
            rows={4}
            placeholder={'每行一条，格式“参数名：参数值”，例如：\n功率：3kW\n容积：500L'}
          />
        </Form.Item>
        <Form.Item name="manufacturer" label="生产厂家">
          <Input placeholder="请输入生产厂家" />
        </Form.Item>
        <Form.Item name="production_date" label="出厂日期">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="factory_no" label="出厂编号">
          <Input placeholder="请输入出厂编号" />
        </Form.Item>
        <Form.Item name="arrival_date" label="入厂日期">
          <DatePicker style={{ width: '100%' }} />
        </Form.Item>
        <Form.Item name="description" label="备注">
          <TextArea rows={4} placeholder="请输入备注" />
        </Form.Item>
      </Form>
    </Drawer>
  )
}