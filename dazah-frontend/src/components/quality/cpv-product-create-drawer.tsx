"use client"

import { useState } from "react"
import { createCpvProduct } from "@/lib/api/quality-cpv"
import { CreateCpvProductInput } from "@/types/quality-cpv"

interface CpvProductCreateDrawerProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
}

export function CpvProductCreateDrawer({ isOpen, onClose, onSuccess }: CpvProductCreateDrawerProps) {
  const [formData, setFormData] = useState<CreateCpvProductInput>({
    name: "",
    specification: "",
    process_version: "V1.0",
    status: "active",
    description: "",
  })
  const [saving, setSaving] = useState(false)
  const [errorMsg, setErrorMsg] = useState("")
  const [successMsg, setSuccessMsg] = useState("")

  function resetForm() {
    setFormData({
      name: "",
      specification: "",
      process_version: "V1.0",
      status: "active",
      description: "",
    })
    setErrorMsg("")
    setSuccessMsg("")
  }

  function handleClose() {
    resetForm()
    onClose()
  }

  async function handleSubmit() {
    // 校验必填字段
    if (!formData.name.trim()) {
      setErrorMsg("产品名称不能为空")
      return
    }
    if (!formData.specification?.trim()) {
      setErrorMsg("规格不能为空")
      return
    }
    if (!formData.process_version?.trim()) {
      setErrorMsg("工艺版本不能为空")
      return
    }

    setSaving(true)
    setErrorMsg("")
    setSuccessMsg("")

    try {
      const product = await createCpvProduct(formData)
      setSuccessMsg(`产品「${product.name}」创建成功`)
      setTimeout(() => {
        handleClose()
        onSuccess()
      }, 1500)
    } catch (err: any) {
      setErrorMsg(err.message || "创建失败，请稍后重试")
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/30 z-40 transition-opacity" onClick={handleClose} />
      )}

      {/* Drawer */}
      <div className={`fixed top-0 right-0 h-full w-[480px] bg-white shadow-2xl z-50 transform transition-transform duration-300 ${isOpen ? "translate-x-0" : "translate-x-full"}`}>
        <div className="flex flex-col h-full">
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">新增 CPV 产品</h2>
            <button onClick={handleClose} className="text-gray-400 hover:text-gray-600 text-xl leading-none">&times;</button>
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
            {/* 产品名称 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                产品名称 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="请输入产品名称"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                disabled={saving}
              />
            </div>

            {/* 规格 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                规格 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.specification}
                onChange={(e) => setFormData({ ...formData, specification: e.target.value })}
                placeholder="请输入规格"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                disabled={saving}
              />
            </div>

            {/* 工艺版本 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                工艺版本 <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={formData.process_version}
                onChange={(e) => setFormData({ ...formData, process_version: e.target.value })}
                placeholder="请输入工艺版本"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                disabled={saving}
              />
            </div>

            {/* 状态 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">状态</label>
              <select
                value={formData.status}
                onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                disabled={saving}
              >
                <option value="active">启用</option>
                <option value="inactive">停用</option>
              </select>
            </div>

            {/* 描述 */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">描述</label>
              <textarea
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="请输入产品描述（选填）"
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-purple-500 focus:border-purple-500"
                disabled={saving}
              />
            </div>

            {/* Error Message */}
            {errorMsg && (
              <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-lg p-3">
                {errorMsg}
              </div>
            )}

            {/* Success Message */}
            {successMsg && (
              <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded-lg p-3">
                {successMsg}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-6 py-4 border-t border-gray-200 flex gap-3">
            <button
              onClick={handleClose}
              className="px-4 py-2 border border-gray-300 text-gray-700 rounded-lg hover:bg-gray-50 text-sm font-medium"
              disabled={saving}
            >
              取消
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              className="flex-1 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? "保存中..." : "保存"}
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
