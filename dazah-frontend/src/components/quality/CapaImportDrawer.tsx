"use client"

import { previewCapaImport, confirmCapaImport } from "@/actions/quality-capa"
import { ImportPreviewDrawer } from "./ImportPreviewDrawer"

interface CapaImportDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

const capaHeaders = [
  "CAPA编号", "启动日期", "事件部门", "涉及产品", "来源编号",
  "CAPA简述", "CAPA效果评估", "关闭日期", "QA质量员/日期",
]

export function CapaImportDrawer({ isOpen, onClose, onSuccess }: CapaImportDrawerProps) {
  return (
    <ImportPreviewDrawer
      isOpen={isOpen}
      onClose={onClose}
      onSuccess={onSuccess}
      title="导入CAPA数据"
      headers={capaHeaders}
      fileInputId="capa-file-input"
      templateDownloadUrl="/api/v1/quality/capas/export"
      templateFilename="CAPA登记汇总表_模板.docx"
      previewAction={previewCapaImport}
      confirmAction={confirmCapaImport}
    />
  )
}
