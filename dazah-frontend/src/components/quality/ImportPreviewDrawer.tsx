"use client"

import PlatformNotice from '@/components/shared/PlatformNotice'

import { useState, useRef } from "react"
import { Button, Checkbox, Drawer } from "antd"
import { getUserErrorMessage } from '@/lib/user-error'

export interface ImportPreviewResult {
  total_rows: number
  valid_rows: number
  error_rows?: { row_number: number; error_message: string }[]
}

export interface ImportResultCounts {
  success_count: number
  update_count: number
  skip_count: number
  error_count: number
  error_details?: { row: number; error: string }[]
}

interface ImportPreviewDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  /** 抽屉标题，如“导入偏差数据” */
  title: string
  /** Word 模板表头字段说明 */
  headers: string[]
  /** 文件输入框唯一 id */
  fileInputId: string
  /** 模板下载接口（系统导出） */
  templateDownloadUrl: string
  /** 模板下载文件名 */
  templateFilename: string
  /** 预览 action */
  previewAction: (formData: FormData) => Promise<ImportPreviewResult>
  /** 确认导入 action */
  confirmAction: (
    formData: FormData,
    skipDuplicates: boolean,
    updateExisting: boolean
  ) => Promise<ImportResultCounts>
  /** 跳过文案后缀，默认“（重复）” */
  skipSuffix?: string
  /** 成功后自动关闭延时（毫秒） */
  closeDelayMs?: number
}

/**
 * 质量模块通用 Word 导入抽屉：预览 → 确认导入流程。
 * 偏差/CAPA/变更台账导入共用，差异通过 props 注入。
 */
export function ImportPreviewDrawer({
  isOpen,
  onClose,
  onSuccess,
  title,
  headers,
  fileInputId,
  templateDownloadUrl,
  templateFilename,
  previewAction,
  confirmAction,
  skipSuffix = "（重复）",
  closeDelayMs = 2000,
}: ImportPreviewDrawerProps) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreviewResult | null>(null)
  const [rowErrors, setRowErrors] = useState<{ row: number; error: string }[]>([])
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")
  const [successMsg, setSuccessMsg] = useState("")
  const [skipDuplicates, setSkipDuplicates] = useState(true)
  const [updateExisting, setUpdateExisting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  function resetState() {
    setFile(null)
    setPreview(null)
    setPreviewing(false)
    setImporting(false)
    setErrorMsg("")
    setSuccessMsg("")
    setRowErrors([])
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  function handleClose() {
    resetState()
    onClose()
  }

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0]
    if (!selected) return
    if (!selected.name.endsWith(".docx")) {
      setErrorMsg("请上传 Word 文件（.docx）")
      return
    }
    setErrorMsg("")
    setFile(selected)
    setPreview(null)
    setSuccessMsg("")
    setRowErrors([])
  }

  async function handlePreview() {
    if (!file) { setErrorMsg("请先选择文件"); return }
    setPreviewing(true)
    setErrorMsg("")
    try {
      const formData = new FormData()
      formData.append("file", file)
      const data = await previewAction(formData)
      setPreview(data)
    } catch (err) {
      setErrorMsg(getUserErrorMessage(err, "预览失败，请稍后重试"))
    } finally {
      setPreviewing(false)
    }
  }

  async function handleConfirm() {
    if (!file) { setErrorMsg("请先选择文件"); return }
    setImporting(true)
    setErrorMsg("")
    setSuccessMsg("")
    setRowErrors([])
    try {
      const formData = new FormData()
      formData.append("file", file)
      const d = await confirmAction(formData, skipDuplicates, updateExisting)
      let msg = `导入完成：${d.success_count} 条成功`
      if (d.update_count > 0) msg += `，${d.update_count} 条已更新`
      if (d.skip_count > 0) msg += `，${d.skip_count} 条跳过${skipSuffix}`
      if (d.error_count > 0) msg += `，${d.error_count} 条失败`
      setSuccessMsg(msg)
      if (d.error_count > 0) {
        setRowErrors(d.error_details ?? [])
        setErrorMsg("部分数据未导入，请查看失败行，修正文档后重新预览；已成功的数据已保存")
        if (d.success_count > 0 || d.update_count > 0) onSuccess()
        setPreview(null)
        return
      }
      setTimeout(() => { handleClose(); onSuccess() }, closeDelayMs)
    } catch (err) {
      setErrorMsg(getUserErrorMessage(err, "导入失败，请先刷新核对是否已保存"))
    } finally {
      setImporting(false)
    }
  }

  async function handleDownloadTemplate() {
    setErrorMsg("")
    try {
      const res = await fetch(templateDownloadUrl)
      if (!res.ok) throw new Error("下载模板失败")
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = templateFilename
      a.click()
      URL.revokeObjectURL(url)
    } catch (err) {
      setErrorMsg((err instanceof Error ? err.message : '') || "下载模板失败")
    }
  }

  return (
    <Drawer
      open={isOpen}
      onClose={handleClose}
      size={480}
      title={title}
      footer={
        <div className="flex flex-wrap gap-3">
          <Button onClick={handleClose} disabled={importing}>取消</Button>
          <Button type={preview ? "default" : "primary"} onClick={handlePreview} disabled={!file || previewing || importing}>
            {previewing ? "预览中..." : "预览数据"}
          </Button>
          {preview && preview.total_rows > 0 && (
            <Button type="primary" onClick={handleConfirm} disabled={importing}>
              {importing ? "导入中..." : "确认导入"}
            </Button>
          )}
        </div>
      }
    >
      <div className="space-y-5">
        <PlatformNotice type="info" title="导入前请核对文档表头与模板" description={<><div className="text-sm font-medium text-[var(--color-info)] mb-2">Word 文档表头字段</div><div className="text-xs text-[var(--color-info)] mb-3">{headers.join("、")}</div></>} action={<><button onClick={handleDownloadTemplate} className="text-xs text-[var(--color-primary)] underline hover:text-[var(--color-primary-hover)]">
            下载导入模板（从系统导出）
          </button></>} />

        <div>
          <label className="block text-sm font-medium text-[var(--color-slate)] mb-2">选择文件</label>
          <div className="border-2 border-dashed border-[var(--color-hairline-strong)] rounded-lg p-6 text-center hover:border-[var(--color-primary-border)] transition-colors">
            <input ref={fileInputRef} type="file" accept=".docx" onChange={handleFileChange} className="hidden" id={fileInputId} />
            <label htmlFor={fileInputId} className="cursor-pointer">
              <div className="text-3xl mb-2">📄</div>
              <div className="text-sm text-[var(--color-slate)]">{file ? file.name : "点击选择 Word 文件 (.docx)"}</div>
            </label>
          </div>
        </div>

        <Checkbox checked={skipDuplicates} onChange={(e) => setSkipDuplicates(e.target.checked)}>
          跳过重复记录（按编号去重）
        </Checkbox>
        <Checkbox checked={updateExisting} onChange={(e) => setUpdateExisting(e.target.checked)}>
          重复时更新已有记录
        </Checkbox>

        {errorMsg && <PlatformNotice type="error" title={<>{errorMsg}</>} />}
        {successMsg && <PlatformNotice type="success" title={<>{successMsg}</>} />}

        {rowErrors.map((rowError, index) => (
          <PlatformNotice key={index} type="error" title={`第${rowError.row}行：${rowError.error}`} />
        ))}
        {preview && (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-[var(--color-ink)]">导入预览</h3>
            <div className="bg-[var(--color-surface-soft)] rounded-lg p-4 space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-[var(--color-steel)]">总行数</span><span className="font-medium">{preview.total_rows}</span></div>
              <div className="flex justify-between"><span className="text-[var(--color-steel)]">可导入</span><span className="font-bold text-[var(--color-success)]">{preview.valid_rows}</span></div>
              {preview.error_rows && preview.error_rows.length > 0 && (
                <div className="flex justify-between"><span className="text-[var(--color-steel)]">错误/重复行</span><span className="font-bold text-[var(--color-error)]">{preview.error_rows.length}</span></div>
              )}
            </div>
            {preview.error_rows && preview.error_rows.length > 0 && (
              <div className="max-h-40 overflow-y-auto">
                {preview.error_rows.map((e, i) => (
                  <PlatformNotice type="error" key={i} title={<>第{e.row_number}行: {e.error_message}</>} />
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </Drawer>
  )
}
