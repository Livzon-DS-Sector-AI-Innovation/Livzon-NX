"use client"

import { useEffect, useState } from "react"
import { Alert, App, Button, Card, Modal, Table } from "antd"
import { getPermissionModuleName } from "@/lib/menu-config"
import {
  listPagePermissionRollouts,
  previewPagePermissionRollout,
  type PermissionModuleRolloutOut,
  type PermissionModuleRolloutPreviewOut,
} from "@/actions/admin"

export function PermissionRolloutManager() {
  const { message } = App.useApp()
  const [items, setItems] = useState<PermissionModuleRolloutOut[]>([])
  const [preview, setPreview] = useState<PermissionModuleRolloutPreviewOut | null>(null)
  const [loading, setLoading] = useState(false)
  const load = () => void listPagePermissionRollouts().then(setItems).catch((error) =>
    message.error(error instanceof Error ? error.message : "接入模块加载失败"),
  )
  useEffect(load, [message])

  const openPreview = async (moduleCode: string) => {
    setLoading(true)
    try {
      setPreview(await previewPagePermissionRollout(moduleCode))
    } catch (error) {
      message.error(error instanceof Error ? error.message : "接入详情加载失败")
    } finally {
      setLoading(false)
    }
  }
  return <Card title="模块权限接入状态" size="small">
    <Alert className="mb-3" type="info" showIcon
      message="模块访问和页面权限保存后立即生效；此处仅检查各模块是否完整接入权限门禁。" />
    <Table rowKey="module_code" dataSource={items} pagination={false} columns={[
      { title: "模块", dataIndex: "module_code", key: "module", render: (code: string) => getPermissionModuleName(code) },
      { title: "接入检查", key: "action", render: (_: unknown, item: PermissionModuleRolloutOut) =>
        <Button size="small" loading={loading} onClick={() => openPreview(item.module_code)}>查看接入详情</Button> },
    ]} />
    <Modal title={`${preview ? getPermissionModuleName(preview.module_code) : "模块"} · 权限接入详情`}
      open={Boolean(preview)} onCancel={() => setPreview(null)} onOk={() => setPreview(null)}
      cancelButtonProps={{ style: { display: "none" } }} okText="关闭">
      {preview && <div className="space-y-2">
        <p>有效页面：{preview.page_count}；账号总数：{preview.user_count}；当前无页面访问权限：{preview.users_without_access}</p>
        {preview.catalog_gaps?.length ? <Alert type="error" showIcon message="权限接入门禁未通过"
          description={<div>
            <p className="mb-2">请完成权限登记、菜单页面绑定或接口契约接入。</p>
            <ul className="list-disc pl-5">{preview.catalog_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
          </div>} />
          : <Alert type="success" showIcon message="权限接入门禁已通过" description="菜单、接口与 Livzon 工具契约均已完成接入。" />}
      </div>}
    </Modal>
  </Card>
}
