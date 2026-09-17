"use client"

import { useCallback, useEffect, useState } from "react"
import { Alert, App, Button, Card, Modal, Table, Tag } from "antd"
import { getPermissionModuleName, moduleMenus } from "@/lib/menu-config"
import {
  listPagePermissionRollouts,
  previewPagePermissionRollout,
  type PermissionModuleIntegrationOut,
  type PermissionModuleRolloutPreviewOut,
} from "@/actions/admin"

const navigationModuleCodes = new Set(moduleMenus.map((module) => module.moduleCode))

export function PermissionRolloutManager() {
  const { message } = App.useApp()
  const [items, setItems] = useState<PermissionModuleIntegrationOut[]>([])
  const [preview, setPreview] = useState<PermissionModuleRolloutPreviewOut | null>(null)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const results = await listPagePermissionRollouts()
      setItems(results.filter((item) => navigationModuleCodes.has(item.module_code)))
    }
    catch (error) {
      const reason = error instanceof Error ? error.message : "接入检查失败"
      setItems([])
      setLoadError(reason)
      message.error(reason)
    }
    finally { setLoading(false) }
  }, [message])
  useEffect(() => {
    const task = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(task)
  }, [load])

  const openPreview = async (moduleCode: string) => {
    setChecking(true)
    try {
      const next = await previewPagePermissionRollout(moduleCode)
      setPreview(next)
      setItems((previous) => previous.map((item) => item.module_code === moduleCode
        ? { ...item, passed: !(next.catalog_gaps?.length), catalog_gaps: next.catalog_gaps || [] }
        : item))
    } catch (error) {
      message.error(error instanceof Error ? error.message : "接入详情加载失败")
    } finally {
      setChecking(false)
    }
  }

  return <Card title="模块权限接入完整性" size="small" extra={<Button size="small" loading={loading}
    onClick={() => void load()}>重新检查</Button>}>
    {loadError && <Alert className="mb-4" type="error" showIcon title={`无法获取当前检查结果：${loadError}`} />}
    <Table rowKey="module_code" dataSource={items} loading={loading} pagination={false} columns={[
      { title: "模块", dataIndex: "module_code", key: "module", render: (code: string) => getPermissionModuleName(code) },
      { title: "当前检查结果", dataIndex: "passed", key: "status", width: 160,
        render: (passed: boolean) => <Tag color={passed ? "green" : "red"}>
          {passed ? "自动检查通过" : "接入有缺口"}
        </Tag> },
      { title: "缺口数", dataIndex: "catalog_gaps", key: "gaps", width: 100,
        render: (gaps: string[]) => gaps.length },
      { title: "详情", key: "action", render: (_: unknown, item: PermissionModuleIntegrationOut) =>
        <Button size="small" loading={checking} onClick={() => void openPreview(item.module_code)}>查看接入详情</Button> },
    ]} />
    <Modal title={`${preview ? getPermissionModuleName(preview.module_code) : "模块"} · 权限接入详情`}
      open={Boolean(preview)} onCancel={() => setPreview(null)} onOk={() => setPreview(null)}
      cancelButtonProps={{ style: { display: "none" } }} okText="关闭">
      {preview && <div className="space-y-2">
        <p>有效页面：{preview.page_count}；账号总数：{preview.user_count}；当前无页面访问权限：{preview.users_without_access}</p>
        {preview.catalog_gaps?.length ? <Alert type="error" showIcon message="当前接入检查未通过"
          description={<ul className="list-disc pl-5">{preview.catalog_gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>} />
          : <Alert type="success" showIcon message="当前接入检查通过"
            description="菜单、接口与 Livzon 工具契约已完成自动完整性检查。实际请求仍由后端逐次鉴权。" />}
      </div>}
    </Modal>
  </Card>
}
