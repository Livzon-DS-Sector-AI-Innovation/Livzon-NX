"use client"

import { previewChangeImport, confirmChangeImport } from "@/actions/quality-change"
import { ImportPreviewDrawer } from "./ImportPreviewDrawer"

interface ChangeImportDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  changeType?: string
}

const changeHeaders = [
  "序号",
  "变更控制号",
  "变更申请部门",
  "变更对象",
  "变更内容",
  "变更等级",
  "变更申请日期",
  "变更计划批准日期",
  "变更正式执行日期",
  "变更关闭日期",
]

export function ChangeImportDrawer({ isOpen, onClose, onSuccess, changeType = 'technical' }: ChangeImportDrawerProps) {
  return (
    <ImportPreviewDrawer
      isOpen={isOpen}
      onClose={onClose}
      onSuccess={onSuccess}
      title="导入变更数据"
      headers={changeHeaders}
      fileInputId="change-file-input"
      templateDownloadUrl="/api/v1/quality/changes/export"
      templateFilename="技术变更台账_模板.docx"
      previewAction={(formData) => previewChangeImport(formData, changeType)}
      confirmAction={(formData, skipDuplicates, updateExisting) =>
        confirmChangeImport(formData, skipDuplicates, updateExisting, changeType)
      }
      skipSuffix=""
      closeDelayMs={1500}
    />
  )
}
