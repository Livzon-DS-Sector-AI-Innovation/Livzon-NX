'use client'

import { useState } from 'react'
import { App, Button, Modal, Select, Upload } from 'antd'
import { DownloadOutlined, InboxOutlined } from '@ant-design/icons'
import type { UploadFile } from 'antd'
import { useEquipmentStore } from '@/stores/equipment'
import type {
  EquipmentCategory,
  EquipmentImportResult,
  Location,
} from '@/types/equipment'

function flattenCategories(
  categories: EquipmentCategory[],
  prefix = '',
): { label: string; value: string }[] {
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

function flattenLocations(
  locations: Location[],
  prefix = '',
): { label: string; value: string }[] {
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

interface EquipmentImportModalProps {
  open: boolean
  onClose: () => void
  /** 导入产生新建/更新后回调，用于刷新台账列表 */
  onImported: () => void
}

// 组装导入请求体（导出便于单测校验字段契约）
export function buildImportFormData(
  rawFile: File,
  defaultCategoryId?: string,
  defaultLocationId?: string,
): FormData {
  const formData = new FormData()
  formData.append('file', rawFile)
  if (defaultCategoryId) {
    formData.append('default_category_id', defaultCategoryId)
  }
  if (defaultLocationId) {
    formData.append('default_location_id', defaultLocationId)
  }
  return formData
}

export function EquipmentImportModal({ open, onClose, onImported }: EquipmentImportModalProps) {
  const { message } = App.useApp()
  const { categories = [], locations = [] } = useEquipmentStore()
  const [rawFile, setRawFile] = useState<File | null>(null)
  const [fileList, setFileList] = useState<UploadFile[]>([])
  const [defaultCategoryId, setDefaultCategoryId] = useState<string>()
  const [defaultLocationId, setDefaultLocationId] = useState<string>()
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<EquipmentImportResult | null>(null)

  const reset = () => {
    setRawFile(null)
    setFileList([])
    setDefaultCategoryId(undefined)
    setDefaultLocationId(undefined)
    setResult(null)
  }

  const handleClose = () => {
    reset()
    onClose()
  }

  const handleSubmit = async () => {
    if (!rawFile) {
      message.warning('请先选择台账 .xlsx 文件')
      return
    }
    setSubmitting(true)
    try {
      const formData = buildImportFormData(rawFile, defaultCategoryId, defaultLocationId)
      const response = await fetch('/api/v1/equipment/equipments/import', {
        method: 'POST',
        body: formData,
      })
      const json = await response.json()
      if (!response.ok || json.code !== 200) {
        message.error(json?.message || '导入失败，请检查文件格式')
        return
      }
      const summary = json.data as EquipmentImportResult
      setResult(summary)
      if (summary.created + summary.updated > 0) onImported()
    } catch {
      message.error('导入失败，请稍后重试')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="导入设备台账"
      open={open}
      onCancel={handleClose}
      width={560}
      destroyOnHidden
      footer={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <a
            href="/api/v1/equipment/equipments/import-template"
            download="equipment-ledger-template.xlsx"
            style={{ fontSize: 13 }}
          >
            <DownloadOutlined /> 下载导入模板
          </a>
          <div style={{ display: 'flex', gap: 8 }}>
            <Button onClick={handleClose}>关闭</Button>
            <Button type="primary" loading={submitting} onClick={handleSubmit}>
              开始导入
            </Button>
          </div>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Upload.Dragger
          accept=".xlsx"
          maxCount={1}
          fileList={fileList}
          beforeUpload={(selected) => {
            setRawFile(selected)
            setFileList([
              { uid: 'ledger-upload', name: selected.name, status: 'done' },
            ])
            setResult(null)
            return false
          }}
          onRemove={() => {
            setRawFile(null)
            setFileList([])
          }}
        >
          <p style={{ fontSize: 28, color: '#8c8c8c', marginBottom: 8 }}>
            <InboxOutlined />
          </p>
          <p style={{ margin: 0 }}>点击或拖拽选择台账 Excel（.xlsx，≤2MB，最多 1000 行）</p>
          <p style={{ margin: '4px 0 0', fontSize: 12, color: '#8c8c8c' }}>
            按模板列填写：设备编号、设备名称、规格型号、技术参数、生产厂家、出厂日期、出厂编号、入厂日期、安装地点、备注
          </p>
        </Upload.Dragger>
        <Select
          placeholder="默认设备分类（可选，暂不分类可留空）"
          value={defaultCategoryId}
          onChange={setDefaultCategoryId}
          allowClear
          showSearch
          optionFilterProp="label"
          options={flattenCategories(categories)}
        />
        <Select
          placeholder="默认安装地点（可选，Excel 安装地点匹配不上时使用）"
          value={defaultLocationId}
          onChange={setDefaultLocationId}
          allowClear
          showSearch
          optionFilterProp="label"
          options={flattenLocations(locations)}
        />
        <p style={{ margin: 0, fontSize: 12, color: '#8c8c8c' }}>
          按设备编号增量导入：编号已存在则更新台账字段，不存在则新建；「安装地点」按名称匹配已有位置，匹配不上自动新建位置；「-」等占位符视为无日期。
        </p>
        {result && (
          <div
            style={{
              border: '1px solid #e5e3df',
              borderRadius: 8,
              padding: '12px 16px',
              background: '#fafaf8',
              fontSize: 13,
            }}
          >
            <div style={{ fontWeight: 600 }}>
              共 {result.total_rows} 行：新建 {result.created} 台、更新 {result.updated} 台、
              失败 {result.failed} 行
              {result.flagged ? `、待修正 ${result.flagged} 台` : ''}
              {result.locations_created ? `、新建位置 ${result.locations_created} 处` : ''}
            </div>
            {result.flagged ? (
              <div style={{ marginTop: 4, color: '#c0392b' }}>
                待修正的设备在台账列表中对问题字段标红（鼠标悬停行可看原因），编辑保存后标记自动清除。
              </div>
            ) : null}
            {result.failures.length > 0 && (
              <ul style={{ margin: '8px 0 0', paddingLeft: 18, color: '#c0392b' }}>
                {result.failures.map((failure) => (
                  <li key={`${failure.row}-${failure.equipment_no ?? ''}`}>
                    第 {failure.row} 行
                    {failure.equipment_no ? `（${failure.equipment_no}）` : ''}：{failure.reason}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}
