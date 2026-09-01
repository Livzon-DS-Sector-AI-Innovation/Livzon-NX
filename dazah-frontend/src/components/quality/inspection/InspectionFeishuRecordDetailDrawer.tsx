'use client'

import { App, Descriptions, Drawer } from 'antd'

import { renderFeishuValue } from './renderFeishuValue'

interface InspectionFeishuRecordDetailDrawerProps {
  open: boolean
  entityCode?: string
  record?: Record<string, unknown>
  allFields?: string[]
  onClose: () => void
}

/** 「详情」抽屉：展示记录全部字段（含附件/链接可点击查看）。 */
export function InspectionFeishuRecordDetailDrawer({
  open,
  entityCode,
  record,
  allFields = [],
  onClose,
}: InspectionFeishuRecordDetailDrawerProps) {
  const { message } = App.useApp()
  const fields = allFields.length > 0 ? allFields : record ? Object.keys(record) : []

  return (
    <Drawer open={open} title="记录详情" size={720} onClose={onClose}>
      {record && (
        <Descriptions
          bordered
          size="small"
          column={1}
          styles={{ label: { width: 220 } }}
        >
          {fields.map((field) => (
            <Descriptions.Item key={field} label={field}>
              {renderFeishuValue(record[field], record, entityCode, message)}
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}
    </Drawer>
  )
}
