'use client'

import { App, Descriptions, Drawer } from 'antd'
import type { QcValidationFieldMeta, QcValidationRecord } from '@/types/quality'
import {
  renderFeishuValue,
  type FeishuAttachmentUrlBuilder,
} from './inspection/renderFeishuValue'

/** 飞书表「ALL」视图的列顺序：方案名称 → 人员 为列表列，其余进详情 */
export const QC_LIST_FIELD_ORDER = [
  '方案名称',
  '方案编码',
  '方案批准时间',
  '报告批准时间',
  '验证原因',
  '偏差情况',
  '验证结果',
  '再验证周期（年）',
  '产品',
  '人员',
]

const QC_DETAIL_FIELD_ORDER = [
  ...QC_LIST_FIELD_ORDER,
  '状态',
  '方案提交',
  '报告提交',
  '封面照片',
  '设备/房间编码',
  '备注',
]

/** 按钮类字段是飞书自动化动作，不作为数据展示 */
const QC_HIDDEN_UI_TYPES = new Set(['Button'])

interface QcValidationDetailDrawerProps {
  open: boolean
  record: QcValidationRecord | null
  fieldMetas?: QcValidationFieldMeta[]
  attachmentUrlBuilder?: FeishuAttachmentUrlBuilder
  onClose: () => void
}

function buildDetailFields(fieldMetas: QcValidationFieldMeta[]): string[] {
  const known = QC_DETAIL_FIELD_ORDER.filter((name) =>
    fieldMetas.length === 0
      ? true
      : fieldMetas.some((meta) => meta.field_name === name),
  )
  const extras = fieldMetas
    .filter(
      (meta) =>
        !QC_DETAIL_FIELD_ORDER.includes(meta.field_name) &&
        !QC_HIDDEN_UI_TYPES.has(meta.ui_type),
    )
    .map((meta) => meta.field_name)
  return fieldMetas.length === 0 ? QC_DETAIL_FIELD_ORDER : [...known, ...extras]
}

/** QC验证记录详情抽屉：展示全部字段（附件可点击下载、人员显示头像姓名）。 */
export function QcValidationDetailDrawer({
  open,
  record,
  fieldMetas = [],
  attachmentUrlBuilder,
  onClose,
}: QcValidationDetailDrawerProps) {
  const { message } = App.useApp()
  const fields = buildDetailFields(fieldMetas)

  return (
    <Drawer open={open} title="QC验证记录详情" width={680} onClose={onClose}>
      {record && (
        <Descriptions bordered size="small" column={1} styles={{ label: { width: 150 } }}>
          {fields.map((field) => {
            const meta = fieldMetas.find((item) => item.field_name === field)
            return (
              <Descriptions.Item key={field} label={field}>
                {renderFeishuValue(record[field], record, undefined, message, {
                  uiType: meta?.ui_type,
                  attachmentUrlBuilder,
                })}
              </Descriptions.Item>
            )
          })}
        </Descriptions>
      )}
    </Drawer>
  )
}
