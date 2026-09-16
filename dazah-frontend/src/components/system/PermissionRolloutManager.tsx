"use client"

import { useEffect, useState } from "react"
import { Alert, App, Button, Card, Input, Modal, Table, Tag } from "antd"
import { getPermissionModuleName } from "@/lib/menu-config"
import {
  listPagePermissionRollouts,
  publishPagePermissionRollout,
  previewPagePermissionRollout,
  type PermissionModuleRolloutOut,
  type PermissionModuleRolloutPreviewOut,
} from "@/actions/admin"

const rolloutStatuses = {
  legacy: { color: "red", label: "未记录通过" },
  draft: { color: "yellow", label: "待核验" },
  enforced: { color: "green", label: "已记录通过" },
} satisfies Record<PermissionModuleRolloutOut["status"], { color: string; label: string }>

export function PermissionRolloutManager() {
  const { message } = App.useApp()
  const [items, setItems] = useState<PermissionModuleRolloutOut[]>([])
  const [preview, setPreview] = useState<PermissionModuleRolloutPreviewOut | null>(null)
  const [loading, setLoading] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [publishReason, setPublishReason] = useState("")
  const load = () => void listPagePermissionRollouts().then(setItems).catch((error) =>
    message.error(error instanceof Error ? error.message : "接入模块加载失败"),
  )
  useEffect(load, [message])

  const closePreview = () => {
    setPreview(null)
    setPublishReason("")
  }

  const openPreview = async (moduleCode: string) => {
    setLoading(true)
    setPublishReason("")
    try {
      setPreview(await previewPagePermissionRollout(moduleCode))
    } catch (error) {
      message.error(error instanceof Error ? error.message : "接入详情加载失败")
    } finally {
      setLoading(false)
    }
  }

  const publishRollout = async () => {
    if (!preview || preview.current_status === "enforced") return
    const reason = publishReason.trim()
    if (!reason) {
      message.error("请输入发布原因")
      return
    }
    setPublishing(true)
    try {
      const result = await publishPagePermissionRollout(preview, reason)
      if (!result.ok) {
        message.error(result.message)
        return
      }
      message.success("模块权限已发布")
      closePreview()
      load()
    } catch (error) {
      message.error(error instanceof Error ? error.message : "模块权限发布失败")
    } finally {
      setPublishing(false)
    }
  }

  return <Card title="模块权限接入状态" size="small">
    <Table rowKey="module_code" dataSource={items} pagination={false} columns={[
      { title: "模块", dataIndex: "module_code", key: "module", render: (code: string) => getPermissionModuleName(code) },
      { title: "接入状态", dataIndex: "status", key: "status", width: 140,
        render: (status: PermissionModuleRolloutOut["status"]) => {
          const { color, label } = rolloutStatuses[status]
          return <Tag color={color}>{label}</Tag>
        } },
      { title: "接入检查", key: "action", render: (_: unknown, item: PermissionModuleRolloutOut) =>
        <Button size="small" loading={loading} onClick={() => openPreview(item.module_code)}>查看接入详情</Button> },
    ]} />
    <Modal title={`${preview ? getPermissionModuleName(preview.module_code) : "模块"} · 权限接入详情`}
      open={Boolean(preview)} onCancel={closePreview} onOk={closePreview}
      cancelButtonProps={{ style: { display: "none" } }} okText="关闭">
      {preview && <div className="space-y-2">
        <p>有效页面：{preview.page_count}；账号总数：{preview.user_count}；当前无页面访问权限：{preview.users_without_access}</p>
        {preview.catalog_gaps?.length ? <Alert type="error" showIcon message="权限接入门禁未通过"
          description={<div>
            <p className="mb-2">请完成权限登记、菜单页面绑定或接口契约接入。</p>
            <ul className="list-disc pl-5">{preview.catalog_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
          </div>} />
          : <>
            <Alert type="success" showIcon message="权限接入门禁已通过" description="菜单、接口与 Livzon 工具契约均已完成接入。" />
            {preview.current_status !== "enforced" && <div className="space-y-2">
              <Input.TextArea value={publishReason} rows={3}
                placeholder="请输入发布原因（必填）"
                onChange={(event) => setPublishReason(event.target.value)} />
              <Button type="primary" loading={publishing} onClick={() => void publishRollout()}>
                确认发布
              </Button>
            </div>}
          </>}
      </div>}
    </Modal>
  </Card>
}
