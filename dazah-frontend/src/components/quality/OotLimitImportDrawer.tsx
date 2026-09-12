"use client"

import { useRef, useState } from "react"
import { confirmOotLimitImport, previewOotLimitImport, type OotLimitImportPreviewFile } from "@/actions/quality"

interface OotLimitImportDrawerProps {
  isOpen: boolean
  onClose: () => void
  /** 导入成功后回调（刷新产品列表） */
  onSuccess: () => void
}

function modeLabel(entry: OotLimitImportPreviewFile): string {
  if (entry.mode === "update") return `更新产品（${entry.matched_product_code || "已存在"}）`
  return "新建产品"
}

/**
 * OOT 限度告知单导入抽屉：支持一次选择多个 docx 告知单，
 * 预览逐文件解析结果（新建/更新、限度行数、错误）后确认导入。
 */
export function OotLimitImportDrawer({ isOpen, onClose, onSuccess }: OotLimitImportDrawerProps) {
  const [files, setFiles] = useState<File[]>([])
  const [previewFiles, setPreviewFiles] = useState<OotLimitImportPreviewFile[]>([])
  const [previewed, setPreviewed] = useState(false)
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")
  const [successMsg, setSuccessMsg] = useState("")
  const fileInputRef = useRef<HTMLInputElement>(null)

  function resetState() {
    setFiles([])
    setPreviewFiles([])
    setPreviewed(false)
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

  function handleFilesChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(e.target.files ?? [])
    if (selected.length === 0) return
    const invalid = selected.filter((file) => !file.name.toLowerCase().endsWith(".docx"))
    if (invalid.length > 0) {
      setErrorMsg(`以下文件不是 Word 文档（.docx）：${invalid.map((f) => f.name).join("、")}`)
      return
    }
    setErrorMsg("")
    setFiles(selected)
    setPreviewFiles([])
    setPreviewed(false)
    setSuccessMsg("")
  }

  function buildFormData(): FormData {
    const formData = new FormData()
    for (const file of files) formData.append("files", file)
    return formData
  }

  async function handlePreview() {
    if (files.length === 0) {
      setErrorMsg("请先选择告知单文件")
      return
    }
    setPreviewing(true)
    setErrorMsg("")
    try {
      const data = await previewOotLimitImport(buildFormData())
      setPreviewFiles(data.files)
      setPreviewed(true)
    } catch (err) {
      setErrorMsg((err instanceof Error ? err.message : "") || "预览失败")
    } finally {
      setPreviewing(false)
    }
  }

  async function handleConfirm() {
    if (files.length === 0) {
      setErrorMsg("请先选择告知单文件")
      return
    }
    setImporting(true)
    setErrorMsg("")
    try {
      const result = await confirmOotLimitImport(buildFormData())
      let msg = `导入完成：新建 ${result.created_count} 个产品，更新 ${result.update_count} 个产品`
      if (result.error_count > 0) msg += `，失败 ${result.error_count} 个文件`
      setSuccessMsg(msg)
      setTimeout(() => {
        handleClose()
        onSuccess()
      }, 2500)
    } catch (err) {
      setErrorMsg((err instanceof Error ? err.message : "") || "导入失败")
    } finally {
      setImporting(false)
    }
  }

  return (
    <>
      {isOpen && <div className="fixed inset-0 bg-black/30 z-40" onClick={handleClose} />}
      <div className={`fixed top-0 right-0 h-full w-[520px] bg-white shadow-2xl z-50 transform transition-transform duration-300 ${isOpen ? "translate-x-0" : "translate-x-full"}`}>
        <div className="flex flex-col h-full">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">导入OOT限度告知单</h2>
            <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
            <div className="bg-blue-50 rounded-lg p-4 text-sm text-blue-800">
              选择一个或多个「XX年 XX 产品OOT限度通知单」Word 文件（.docx）。系统按
              <span className="font-medium"> 产品名 + 年份 </span>
              匹配已有产品：命中则更新该产品全部限度明细，未命中则自动新建产品。
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">选择文件（可多选）</label>
              <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition-colors">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".docx"
                  multiple
                  onChange={handleFilesChange}
                  className="hidden"
                  id="oot-limit-import-file"
                />
                <label htmlFor="oot-limit-import-file" className="cursor-pointer">
                  <div className="text-3xl mb-2">📄</div>
                  <div className="text-sm text-gray-600">
                    {files.length > 0 ? `已选择 ${files.length} 个文件` : "点击选择 Word 告知单 (.docx)"}
                  </div>
                </label>
              </div>
              {files.length > 0 && (
                <div className="mt-2 space-y-1">
                  {files.map((file) => (
                    <div key={file.name} className="text-xs text-gray-500 truncate">· {file.name}</div>
                  ))}
                </div>
              )}
            </div>

            {errorMsg && <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">{errorMsg}</div>}
            {successMsg && <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded-lg p-3">{successMsg}</div>}

            {previewed && (
              <div className="space-y-3">
                <h3 className="text-sm font-semibold text-gray-900">导入预览</h3>
                {previewFiles.map((entry) => (
                  <div
                    key={entry.filename}
                    className={`rounded-lg p-3 text-sm border ${entry.status === "error" ? "bg-red-50 border-red-200" : "bg-gray-50 border-gray-200"}`}
                  >
                    <div className="flex justify-between gap-2">
                      <span className="font-medium text-gray-800 truncate">{entry.filename}</span>
                      {entry.status === "error" ? (
                        <span className="text-red-600 shrink-0">解析失败</span>
                      ) : (
                        <span className={entry.mode === "update" ? "text-amber-600 shrink-0" : "text-green-700 shrink-0"}>
                          {modeLabel(entry)}
                        </span>
                      )}
                    </div>
                    {entry.status === "ok" && (
                      <>
                        <div className="text-xs text-gray-500 mt-1">
                          {entry.product_name}
                          {entry.document_year ? ` · ${entry.document_year}年` : ""} · 限度 {entry.item_count} 项
                        </div>
                        {entry.warnings && entry.warnings.length > 0 && (
                          <div className="text-xs text-amber-600 mt-1">{entry.warnings.join("；")}</div>
                        )}
                        {entry.row_errors && entry.row_errors.length > 0 && (
                          <div className="mt-1 max-h-32 overflow-y-auto">
                            {entry.row_errors.map((error, index) => (
                              <div key={index} className="text-xs text-red-600 bg-red-50 p-2 rounded mb-1">{error}</div>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                    {entry.status === "error" && <div className="text-xs text-red-600 mt-1">{entry.error}</div>}
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="px-6 py-4 border-t border-gray-200 flex gap-3">
            <button onClick={handleClose} className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium" disabled={importing}>
              取消
            </button>
            <button
              onClick={handlePreview}
              disabled={files.length === 0 || previewing || importing}
              className="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium disabled:opacity-50"
            >
              {previewing ? "解析中..." : "预览解析结果"}
            </button>
            {previewed && (
              <button
                onClick={handleConfirm}
                disabled={importing || previewFiles.every((entry) => entry.status === "error")}
                className="flex-1 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 text-sm font-medium disabled:opacity-50"
              >
                {importing ? "导入中..." : "确认导入"}
              </button>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
