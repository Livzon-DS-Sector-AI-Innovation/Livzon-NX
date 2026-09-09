'use client'

import { App, Descriptions, Drawer } from 'antd'
import type {
  AnomalyReportFieldMeta,
  AnomalyReportRecord,
} from '@/types/quality'
import {
  renderFeishuValue,
  type FeishuAttachmentUrlBuilder,
  type RenderFeishuValueOptions,
} from './inspection/renderFeishuValue'

/** 按钮类字段是飞书自动化动作，不作为数据展示 */
const HIDDEN_UI_TYPES = new Set(['Button'])

interface FinishedProductAnomalyDetailDrawerProps {
  open: boolean
  record: AnomalyReportRecord | null
  fieldMetas?: AnomalyReportFieldMeta[]
  attachmentUrlBuilder?: FeishuAttachmentUrlBuilder
  onAttachmentPreview?: RenderFeishuValueOptions['onAttachmentPreview']
  onClose: () => void
}

/** 成品异常报告记录详情抽屉：按字段元数据展示全部字段（附件可下载、图片内联、人员头像姓名）。 */
export function FinishedProductAnomalyDetailDrawer({
  open,
  record,
  fieldMetas = [],
  attachmentUrlBuilder,
  onAttachmentPreview,
  onClose,
}: FinishedProductAnomalyDetailDrawerProps) {
  const { message } = App.useApp()
  const fields = fieldMetas
    .filter((meta) => !HIDDEN_UI_TYPES.has(meta.ui_type))
    .map((meta) => meta.field_name)

  return (
    <Drawer open={open} title="成品异常报告详情" size={680} onClose={onClose}>
      {record && (
        <Descriptions bordered size="small" column={1} styles={{ label: { width: 150 } }}>
          {fields.map((field) => {
            const meta = fieldMetas.find((item) => item.field_name === field)
            return (
              <Descriptions.Item key={field} label={field}>
                {renderFeishuValue(record[field], record, undefined, message, {
                  uiType: meta?.ui_type,
                  attachmentUrlBuilder,
                  onAttachmentPreview,
                })}
              </Descriptions.Item>
            )
          })}
        </Descriptions>
      )}
    </Drawer>
  )
}
