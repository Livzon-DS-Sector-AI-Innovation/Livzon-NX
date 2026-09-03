"use client"

import { useEffect, useState } from "react"
import { Alert, App, Button, Card, Input, Modal, Popconfirm, Space, Table, Tag } from "antd"
import { getPermissionModuleName } from "@/lib/menu-config"
import {
  listPagePermissionRollouts,
  previewPagePermissionRollout,
  publishPagePermissionRollout,
  rollbackPagePermissionRollout,
  type PermissionModuleRolloutOut,
  type PermissionModuleRolloutPreviewOut,
} from "@/actions/admin"

const statusNames: Record<string, { text: string; color: string }> = {
  legacy: { text: "旧规则", color: "default" },
  draft: { text: "草稿", color: "warning" },
  enforced: { text: "已发布", color: "success" },
}

export function PermissionRolloutManager() {
  const { message } = App.useApp()
  const [items, setItems] = useState<PermissionModuleRolloutOut[]>([])
  const [preview, setPreview] = useState<PermissionModuleRolloutPreviewOut | null>(null)
  const [reason, setReason] = useState("")
  const [loading, setLoading] = useState(false)
  const load = () => void listPagePermissionRollouts().then(setItems).catch((error) =>
    message.error(error instanceof Error ? error.message : "发布状态加载失败"),
  )
  useEffect(load, [message])

  const openPreview = async (moduleCode: string) => {
    setLoading(true)
    try {
      setPreview(await previewPagePermissionRollout(moduleCode))
      setReason("")
    } catch (error) {
      message.error(error instanceof Error ? error.message : "发布预览失败")
    } finally {
      setLoading(false)
    }
  }
  const publish = async () => {
    if (!preview || !reason.trim()) {
      message.warning("请填写发布原因")
      return
    }
    setLoading(true)
    try {
      const response = await publishPagePermissionRollout(preview, reason.trim())
      if (!response.ok) throw new Error(response.message)
      message.success("模块页面权限已发布")
      setPreview(null)
      load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : "发布失败")
    } finally {
      setLoading(false)
    }
  }
  const rollback = async (item: PermissionModuleRolloutOut) => {
    if (!reason.trim()) {
      message.warning("请先填写紧急回退原因")
      return
    }
    try {
      const response = await rollbackPagePermissionRollout(item.module_code, item.version, reason.trim())
      if (!response.ok) throw new Error(response.message)
      message.warning("模块已紧急回退到旧规则，旧权限范围可能重新扩大")
      setReason("")
      load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : "紧急回退失败")
    }
  }

  return <Card title="页面权限发布管理" size="small">
    <Alert className="mb-3" type="warning" showIcon
      message="发布后，普通用户没有新页面权限即拒绝；不会从旧权限自动回填。" />
    <Input className="mb-3 max-w-xl" value={reason} onChange={(event) => setReason(event.target.value)}
      placeholder="填写发布或紧急回退原因" maxLength={500} />
    <Table rowKey="module_code" dataSource={items} pagination={false} columns={[
      { title: "模块", dataIndex: "module_code", key: "module", render: (code: string) => getPermissionModuleName(code) },
      { title: "状态", dataIndex: "status", key: "status", render: (status: string) =>
        <Tag color={statusNames[status]?.color}>{statusNames[status]?.text}</Tag> },
      { title: "版本", dataIndex: "version", key: "version" },
      { title: "操作", key: "action", render: (_: unknown, item: PermissionModuleRolloutOut) => <Space>
        <Button size="small" loading={loading} onClick={() => openPreview(item.module_code)}>发布预览</Button>
        {item.status === "enforced" && <Popconfirm title="确认紧急回退？旧权限范围可能重新扩大。"
          onConfirm={() => rollback(item)}><Button size="small" danger>紧急回退</Button></Popconfirm>}
      </Space> },
    ]} />
    <Modal title={`${preview ? getPermissionModuleName(preview.module_code) : "模块"} · 发布影响预览`}
      open={Boolean(preview)} onCancel={() => setPreview(null)} onOk={publish}
      okButtonProps={{ disabled: Boolean(preview?.catalog_gaps?.length), loading }} okText="二次确认并发布">
      {preview && <div className="space-y-2">
        <Input.TextArea value={reason} onChange={(event) => setReason(event.target.value)}
          placeholder="填写本次发布原因" aria-label="发布原因" maxLength={500} rows={2} />
        <p>有效页面：{preview.page_count}；影响用户：{preview.user_count}；发布后无页面访问权限：{preview.users_without_access}</p>
        {preview.catalog_gaps?.length ? <Alert type="error" showIcon message="发布门禁未通过"
          description={<div>
            <p className="mb-2">请完成权限登记、菜单页面绑定或接口契约接入后重新预览。</p>
            <ul className="list-disc pl-5">{preview.catalog_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
          </div>} />
          : <Alert type="success" showIcon message="目录与工具契约检查通过" />}
      </div>}
    </Modal>
  </Card>
}
