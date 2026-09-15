'use client'

import { useEffect, useMemo, useState } from 'react'
import { Alert, App, Form, Modal, Select, Space, Spin, Tag } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { createInspectionFeishuRecord } from '@/actions/quality-inspection'
import {
  fetchInspectionFeishuFields,
  fetchInspectionMaterials,
} from '@/lib/api/client/quality'
import type { InspectionFeishuFieldMeta, InspectionMaterialItem } from '@/types/quality'
import { FieldControl, toApiValue } from './inspectionFeishuFormFields'

export interface InspectionMaterialCreated {
  entityCode: string
  recordId: string
  module: string
  groupKey: string
}

interface InspectionCreateByMaterialModalProps {
  open: boolean
  onClose: () => void
  onCreated: (result: InspectionMaterialCreated) => void
  /** 限定可选物料范围：固体页只列固体、液体页只列液体；不传则固体+液体全部 */
  module?: 'solid' | 'liquid'
}

/** label 形如「YS001 食用葡萄糖」：首位空格前为代码，其余为名称。 */
function parseMaterialLabel(label: string): { code: string; name: string } {
  const idx = label.indexOf(' ')
  if (idx <= 0) return { code: '', name: label }
  return { code: label.slice(0, idx), name: label.slice(idx + 1) }
}

const MODULE_LABELS: Record<string, string> = { solid: '固体物料', liquid: '液体物料' }

/**
 * 「新增检验」单弹窗：按物料名称/代码模糊搜索选择物料（代码自动关联），
 * 选中后同一弹窗展开该物料检验表字段填写提交。
 */
export function InspectionCreateByMaterialModal({
  open,
  onClose,
  onCreated,
  module,
}: InspectionCreateByMaterialModalProps) {
  const { message } = App.useApp()
  const [form] = Form.useForm()
  const [selectedEntityCode, setSelectedEntityCode] = useState<string>()
  const [fieldsMeta, setFieldsMeta] = useState<InspectionFeishuFieldMeta[]>([])
  const [fieldsLoading, setFieldsLoading] = useState(false)
  const [fieldsError, setFieldsError] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const { data: allMaterials = [], isFetching: materialsLoading, refetch: refetchMaterials } =
    useQuery<InspectionMaterialItem[]>({
      queryKey: ['quality-inspection', 'materials'],
      queryFn: fetchInspectionMaterials,
      enabled: open,
    })

  // 随页面模块分开：固体页只列固体、液体页只列液体
  const materials = useMemo(
    () => (module ? allMaterials.filter((item) => item.module === module) : allMaterials),
    [allMaterials, module]
  )

  const selectedMaterial = useMemo(
    () => materials.find((item) => item.entity_code === selectedEntityCode),
    [materials, selectedEntityCode]
  )

  useEffect(() => {
    if (!open) return
    setSelectedEntityCode(undefined)
    setFieldsMeta([])
    setFieldsError(false)
    form.resetFields()
  }, [open, form])

  const loadFields = async (entityCode: string) => {
    setFieldsLoading(true)
    setFieldsError(false)
    setFieldsMeta([])
    form.resetFields()
    try {
      const res = await fetchInspectionFeishuFields(entityCode)
      const meta = res?.fields ?? []
      setFieldsMeta(meta)
      const material = materials.find((item) => item.entity_code === entityCode)
      if (material) {
        const { code, name } = parseMaterialLabel(material.label)
        const values: Record<string, unknown> = {}
        for (const f of meta) {
          if (!f.editable) continue
          if (code && /物料代码/.test(f.field_name)) values[f.field_name] = code
          else if (name && /物料名称/.test(f.field_name)) values[f.field_name] = name
        }
        form.setFieldsValue(values)
      }
    } catch {
      setFieldsError(true)
    } finally {
      setFieldsLoading(false)
    }
  }

  const handleSelectMaterial = (entityCode: string) => {
    setSelectedEntityCode(entityCode)
    void loadFields(entityCode)
  }

  const editableFields = useMemo(() => fieldsMeta.filter((f) => f.editable), [fieldsMeta])

  const handleOk = async () => {
    if (!selectedEntityCode || !selectedMaterial) return
    try {
      const raw = await form.validateFields()
      const fields: Record<string, unknown> = {}
      for (const f of editableFields) {
        const v = raw[f.field_name]
        if (v === undefined || v === null || v === '') continue
        fields[f.field_name] = toApiValue(f, v)
      }
      setSubmitting(true)
      const result = await createInspectionFeishuRecord(selectedEntityCode, fields)
      message.success('创建成功，已同步飞书')
      onCreated({
        entityCode: selectedEntityCode,
        recordId: String(result?.record_id ?? ''),
        module: selectedMaterial.module,
        groupKey: selectedMaterial.group_key,
      })
      onClose()
    } catch (err) {
      if (err instanceof Error) message.error(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  // 选项按分组归组（模块内用分组名；跨模块时前缀模块名避免同名分组合并）
  // 纯字符串 label，保证 showSearch 的 filterOption 可按名称/代码模糊匹配
  const materialOptions = useMemo(() => {
    const grouped = new Map<string, { label: string; items: InspectionMaterialItem[] }>()
    for (const item of materials) {
      const groupLabel = item.group_label || item.group_key || '其他'
      const key = module
        ? groupLabel
        : `${MODULE_LABELS[item.module] ?? item.module} / ${groupLabel}`
      const entry = grouped.get(key) ?? { label: key, items: [] }
      entry.items.push(item)
      grouped.set(key, entry)
    }
    return Array.from(grouped.values()).map(({ label, items }) => ({
      label,
      options: items.map((item) => ({
        value: item.entity_code,
        label: item.label,
      })),
    }))
  }, [materials, module])

  return (
    <Modal
      open={open}
      title="新增检验记录"
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={submitting}
      okText="提交"
      cancelText="取消"
      width={680}
      destroyOnHidden
    >
      <Space orientation="vertical" style={{ width: '100%' }} size={16}>
        <div>
          <div style={{ marginBottom: 8, fontWeight: 500 }}>物料名称</div>
          <Space wrap>
            <Select
              showSearch
              placeholder="输入物料名称或代码搜索，同名多代码时请选择具体物料"
              style={{ width: 440 }}
              loading={materialsLoading}
              value={selectedEntityCode}
              onChange={handleSelectMaterial}
              filterOption={(input, option) =>
                String(option?.label ?? '').includes(input)
              }
              notFoundContent={materialsLoading ? <Spin size="small" /> : '未匹配到物料'}
              options={materialOptions}
            />
            {selectedMaterial && (
              <Tag color="blue">
                物料代码：{parseMaterialLabel(selectedMaterial.label).code || '-'}
              </Tag>
            )}
          </Space>
          {!materialsLoading && materials.length === 0 && (
            <Alert
              style={{ marginTop: 8 }}
              type="warning"
              showIcon
              message="暂无可用物料"
              description="未获取到固体/液体原辅料列表，请稍后重试。"
              action={<a onClick={() => void refetchMaterials()}>重试</a>}
            />
          )}
        </div>

        <div
          style={{
            maxHeight: '60vh',
            overflowY: 'auto',
            border: '1px solid rgba(0, 0, 0, 0.08)',
            borderRadius: 8,
            padding: '0 16px 8px',
          }}
        >
          {!selectedEntityCode && (
            <div style={{ padding: 16, textAlign: 'center', color: 'rgba(0, 0, 0, 0.45)' }}>
              请先选择物料
            </div>
          )}
          {selectedEntityCode && fieldsLoading && (
            <div style={{ padding: 24, textAlign: 'center' }}>
              <Spin description="正在加载检验表..." />
            </div>
          )}
          {selectedEntityCode && fieldsError && (
            <Alert
              style={{ marginTop: 16 }}
              type="error"
              showIcon
              message="检验表加载失败"
              description="请检查该物料的飞书数据源配置后重试。"
              action={<a onClick={() => void loadFields(selectedEntityCode)}>重试</a>}
            />
          )}
          {/* Form 始终挂载以连接 useForm 实例；未选物料/加载/错误时不渲染字段 */}
          <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
            {selectedEntityCode && !fieldsLoading && !fieldsError &&
              editableFields.map((f) => (
                <FieldControl key={f.field_name} field={f} />
              ))}
          </Form>
        </div>
      </Space>
    </Modal>
  )
}
