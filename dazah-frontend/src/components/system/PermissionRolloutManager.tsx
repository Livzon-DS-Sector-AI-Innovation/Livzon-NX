"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { App, Button, Card, Modal, Space, Table, Tag, Tooltip, Typography } from "antd"
import Alert from "@/components/shared/PlatformNotice"
import { getPermissionModuleName, moduleMenus } from "@/lib/menu-config"
import {
  listPagePermissionRollouts,
  previewPagePermissionRollout,
  type PermissionModuleIntegrationOut,
  type PermissionModuleRolloutPreviewOut,
} from "@/actions/admin"

const navigationModuleCodes = new Set(moduleMenus.map((module) => module.moduleCode))
const categories = ["页面", "接口", "Livzon 工具", "检查目录", "其他"] as const

function groupedGaps(gaps: string[] = []) {
  return categories.map((category) => ({
    category,
    gaps: gaps.filter((gap) => category === "其他"
      ? !categories.some((known) => gap.startsWith(`${known}｜`))
      : gap.startsWith(`${category}｜`)),
  })).filter((group) => group.gaps.length > 0)
}

function gapTargets(items: PermissionModuleIntegrationOut[]) {
  return new Set(items.flatMap((item) => (item.catalog_gaps ?? []).map((gap) =>
    `${item.module_code}/${gap.split("：", 1)[0]}`)))
}

export function PermissionRolloutManager() {
  const { message } = App.useApp()
  const [items, setItems] = useState<PermissionModuleIntegrationOut[]>([])
  const [preview, setPreview] = useState<PermissionModuleRolloutPreviewOut | null>(null)
  const [loading, setLoading] = useState(false)
  const [checking, setChecking] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [checkedAt, setCheckedAt] = useState<Date | null>(null)
  const mounted = useRef(false)
  const busy = useRef(false)
  const previewModule = useRef<string | null>(null)
  const previousTargets = useRef<Set<string> | null>(null)

  const load = useCallback(async () => {
    if (busy.current || !mounted.current) return
    busy.current = true
    setLoading(true)
    const selectedModule = previewModule.current
    try {
      const [results, nextPreview] = await Promise.all([
        listPagePermissionRollouts(),
        selectedModule ? previewPagePermissionRollout(selectedModule) : Promise.resolve(null),
      ])
      if (!mounted.current) return
      const nextItems = results.filter((item) => navigationModuleCodes.has(item.module_code))
        .map((item) => nextPreview?.module_code === item.module_code
          ? { ...item, passed: !nextPreview.catalog_gaps?.length, catalog_gaps: nextPreview.catalog_gaps ?? [] }
          : item)
      const targets = gapTargets(nextItems)
      const previous = previousTargets.current
      const added = previous ? [...targets].filter((target) => !previous.has(target)).length : 0
      previousTargets.current = targets
      setItems(nextItems)
      setLoadError(null)
      setCheckedAt(new Date())
      if (nextPreview && previewModule.current === selectedModule) setPreview(nextPreview)
      if (added) message.warning(`发现 ${added} 项新增权限接入缺口，请查看接入详情`)
    }
    catch (error) {
      if (!mounted.current) return
      const reason = error instanceof Error ? error.message : "接入检查失败"
      setItems([])
      setLoadError(reason)
      setCheckedAt(null)
      setPreview(null)
      previewModule.current = null
      message.error(reason)
    }
    finally {
      busy.current = false
      if (mounted.current) setLoading(false)
    }
  }, [message])
  useEffect(() => {
    mounted.current = true
    const task = window.setTimeout(() => void load(), 0)
    return () => {
      mounted.current = false
      window.clearTimeout(task)
    }
  }, [load])

  const openPreview = async (moduleCode: string) => {
    if (busy.current) return
    busy.current = true
    setChecking(true)
    try {
      const next = await previewPagePermissionRollout(moduleCode)
      if (!mounted.current) return
      const gaps = next.catalog_gaps ?? []
      previewModule.current = moduleCode
      setPreview(next)
      if (previousTargets.current) {
        const retained = [...previousTargets.current].filter((target) => !target.startsWith(`${moduleCode}/`))
        previousTargets.current = new Set([...retained, ...gapTargets([{
          module_code: moduleCode, passed: !gaps.length, catalog_gaps: gaps,
        }])])
      }
      setItems((previous) => previous.map((item) => item.module_code === moduleCode
        ? { ...item, passed: !gaps.length, catalog_gaps: gaps }
        : item))
    } catch (error) {
      if (mounted.current) message.error(error instanceof Error ? error.message : "接入详情加载失败")
    } finally {
      busy.current = false
      if (mounted.current) setChecking(false)
    }
  }

  const closePreview = () => {
    previewModule.current = null
    setPreview(null)
  }
  const previewGaps = preview?.catalog_gaps ?? []

  return <Card title="模块权限接入完整性" size="small" extra={<Space wrap>
    <Typography.Text type="secondary" aria-live="polite">
      {checkedAt ? `最近检查：${checkedAt.toLocaleTimeString("zh-CN", { hour12: false })}` : "尚未完成检查"}
    </Typography.Text>
    <Button size="small" loading={loading} disabled={checking} onClick={() => void load()}>重新检查</Button>
  </Space>}>
    {loadError && <Alert className="mb-4" type="error" showIcon title={`无法获取当前检查结果：${loadError}`} />}
    <Table rowKey="module_code" dataSource={items} loading={loading} pagination={false} scroll={{ x: 600 }} columns={[
      { title: "模块", dataIndex: "module_code", key: "module", render: (code: string) => getPermissionModuleName(code) },
      { title: "当前检查结果", dataIndex: "passed", key: "status", width: 160,
        render: (passed: boolean) => <Tag color={passed ? "green" : "red"}>
          {passed ? "自动检查通过" : "接入有缺口"}
        </Tag> },
      { title: "缺口数", dataIndex: "catalog_gaps", key: "gaps", width: 100,
        render: (gaps: string[] = []) => <Tooltip title={groupedGaps(gaps)
          .map((group) => `${group.category} ${group.gaps.length}`).join("；") || "未发现接入缺口"}>
          <span>{gaps.length}</span>
        </Tooltip> },
      { title: "详情", key: "action", render: (_: unknown, item: PermissionModuleIntegrationOut) =>
        <Button size="small" loading={checking} disabled={loading}
          onClick={() => void openPreview(item.module_code)}>查看接入详情</Button> },
    ]} />
    <Modal title={`${preview ? getPermissionModuleName(preview.module_code) : "模块"} · 权限接入详情`}
      open={Boolean(preview)} onCancel={closePreview} onOk={closePreview} width={800}
      styles={{ body: { maxHeight: "65vh", overflowY: "auto" } }}
      cancelButtonProps={{ style: { display: "none" } }} okText="关闭">
      {preview && <div className="space-y-2">
        <p>有效页面：{preview.page_count}；账号总数：{preview.user_count}；当前无页面访问权限：{preview.users_without_access}</p>
        {previewGaps.length ? <>
          <Alert type="error" showIcon title={`当前接入检查未通过，共 ${previewGaps.length} 项缺口`}
            description="每个页面、接口或工具分别计数，同一对象的多项问题合并展示。发现缺口不会自动授予权限。" />
          {groupedGaps(previewGaps).map((group) => <section key={group.category}>
            <Typography.Title level={5}>{group.category}（{group.gaps.length}）</Typography.Title>
            <ul className="list-disc pl-5 break-words">{group.gaps.map((gap) => <li key={gap}>{gap}</li>)}</ul>
          </section>)}
        </> : <Alert type="success" showIcon title="当前接入检查通过"
          description="当前菜单、前端页面目录、接口与 Livzon 工具契约未发现接入缺口。实际请求仍由后端逐次鉴权，本结果不替代业务权限安全验收。" />}
      </div>}
    </Modal>
  </Card>
}
