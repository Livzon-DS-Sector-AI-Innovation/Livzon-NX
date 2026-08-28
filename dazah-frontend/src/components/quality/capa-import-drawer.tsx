"use client"

import { useEffect, useRef, useState } from "react"
import { Checkbox } from "antd"
import { confirmCapaImport, previewCapaImport } from "@/actions/quality"

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
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<any>(null)
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
    if (fileInputRef.current) fileInputRef.current.value = ""
  }

  function handleClose() {
    resetState()
    onClose()
  }

  useEffect(() => {
    if (!isOpen) {
      resetState()
    }
  }, [isOpen])

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
  }

  async function handlePreview() {
    if (!file) { setErrorMsg("请先选择文件"); return }
    setPreviewing(true)
    setErrorMsg("")
    try {
      const formData = new FormData()
      formData.append("file", file)
      setPreview(await previewCapaImport(formData))
    } catch (err) {
      setErrorMsg((err instanceof Error ? err.message : '') || "预览失败")
    } finally {
      setPreviewing(false)
    }
  }

  async function handleConfirm() {
    if (!file) { setErrorMsg("请先选择文件"); return }
    setImporting(true)
    setErrorMsg("")
    try {
      const formData = new FormData()
      formData.append("file", file)
      const d = await confirmCapaImport(formData, {
        skipDuplicates,
        updateExisting,
      })
      let msg = `导入完成：${d.success_count} 条成功`
      if (d.update_count > 0) msg += `，${d.update_count} 条已更新`
      if (d.skip_count > 0) msg += `，${d.skip_count} 条跳过（重复）`
      if (d.error_count > 0) msg += `，${d.error_count} 条失败`
      setSuccessMsg(msg)
      setTimeout(() => { handleClose(); onSuccess() }, 2000)
    } catch (err) {
      setErrorMsg((err instanceof Error ? err.message : '') || "导入失败")
    } finally {
      setImporting(false)
    }
  }

  async function handleDownloadTemplate() {
    // Trigger export to get a template
    const res = await fetch("/api/v1/quality/capas/export")
    if (!res.ok) throw new Error("下载模板失败")
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = "CAPA登记汇总表_模板.docx"
    a.click()
    URL.revokeObjectURL(url)
  }

  if (!isOpen) {
    return null
  }

  return (
    <>
      <div className="fixed inset-0 bg-black/30 z-40" onClick={handleClose} />
      <div className="fixed top-0 right-0 h-full w-[480px] bg-white shadow-2xl z-50 transform transition-transform duration-300 translate-x-0">
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">导入CAPA数据</h2>
            <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
            <div className="bg-blue-50 rounded-lg p-4">
              <div className="text-sm font-medium text-blue-800 mb-2">Word 文档表头字段</div>
              <div className="text-xs text-blue-600 mb-3">{capaHeaders.join("、")}</div>
              <button onClick={handleDownloadTemplate} className="text-xs text-blue-700 underline hover:text-blue-900">
                下载导入模板（从系统导出）
              </button>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">选择文件</label>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition-colors">
                <input ref={fileInputRef} type="file" accept=".docx" onChange={handleFileChange} className="hidden" id="capa-file-input" />
                <label htmlFor="capa-file-input" className="cursor-pointer">
                  <div className="text-3xl mb-2">📄</div>
                  <div className="text-sm text-gray-600">{file ? file.name : "点击选择 Word 文件 (.docx)"}</div>
                </label>
              </div>
            </div>

            <Checkbox checked={skipDuplicates} onChange={(e) => setSkipDuplicates(e.target.checked)}>
              跳过重复记录（按编号去重）
            </Checkbox>
            <Checkbox checked={updateExisting} onChange={(e) => setUpdateExisting(e.target.checked)}>
              重复时更新已有记录
            </Checkbox>

            {errorMsg && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{errorMsg}</div>}
            {successMsg && <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded-lg p-3">{successMsg}</div>}

            {preview && (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-900">导入预览</h3>
                <div className="bg-gray-50 rounded-lg p-4 space-y-2 text-sm">
                  <div className="flex justify-between"><span className="text-gray-500">总行数</span><span className="font-medium">{preview.total_rows}</span></div>
                  <div className="flex justify-between"><span className="text-gray-500">可导入</span><span className="font-bold text-green-700">{preview.valid_rows}</span></div>
                  {preview.error_rows?.length > 0 && (
                    <div className="flex justify-between"><span className="text-gray-500">错误/重复行</span><span className="font-bold text-red-600">{preview.error_rows.length}</span></div>
                  )}
                </div>
                {preview.error_rows?.length > 0 && (
                  <div className="max-h-40 overflow-y-auto">
                    {preview.error_rows.map((e: any, i: number) => (
                      <div key={i} className="text-xs text-red-600 bg-red-50 p-2 rounded mb-1">第{e.row_number}行: {e.error_message}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="px-6 py-4 border-t border-gray-200 flex gap-3">
            <button onClick={handleClose} className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium" disabled={importing}>取消</button>
            <button onClick={handlePreview} disabled={!file || previewing || importing} className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50">
              {previewing ? "预览中..." : "预览数据"}
            </button>
            {preview && preview.total_rows > 0 && (
              <button onClick={handleConfirm} disabled={importing} className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium disabled:opacity-50">
                {importing ? "导入中..." : "确认导入"}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
