"use client"

import { previewDeviationImport, confirmDeviationImport } from "@/actions/quality-deviation"
import { ImportPreviewDrawer } from "./ImportPreviewDrawer"

interface DeviationImportDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

const deviationHeaders = [
  "序号", "偏差编号", "产品名称/批号", "偏差简要描述", "偏差是否曾发生",
  "根本原因", "偏差等级", "调查完成时间", "纠正预防措施",
  "产品/物料处理结果", "是否关闭",
]

export function DeviationImportDrawer({ isOpen, onClose, onSuccess }: DeviationImportDrawerProps) {
  return (
    <ImportPreviewDrawer
      isOpen={isOpen}
      onClose={onClose}
      onSuccess={onSuccess}
      title="导入偏差数据"
      headers={deviationHeaders}
      fileInputId="deviation-file-input"
      templateDownloadUrl="/api/v1/quality/deviations/export"
      templateFilename="偏差登记表_模板.docx"
      previewAction={previewDeviationImport}
      confirmAction={confirmDeviationImport}
    />
  )
}
