"use client"

import { useEffect, useRef, useState } from "react"
import { Alert, App, Button, DatePicker, Drawer, Empty, Input, Select, Space, Table, Tag, Typography } from "antd"
import type { Dayjs } from "dayjs"
import {
  exportRolePagePermissionHistory, getRolePagePermissionHistory,
  previewRolePagePermissionRollback, rollbackRolePagePermissions,
  type PagePermissionHistoryItemOut, type PagePermissionHistoryQuery,
  type PagePermissionRollbackPreviewOut,
} from "@/actions/admin"
import {
  exportUserPagePermissionHistory, getUserPagePermissionHistory,
  previewUserPagePermissionRollback, rollbackUserPagePermissions,
} from "@/actions/users"

const sourceLabels = {
  manual: { label: "手工调整", color: "blue" },
  rollback: { label: "历史回滚", color: "orange" },
  health_remediation: { label: "健康修复", color: "purple" },
} as const
const changeLabels = {
  grant: { label: "新增", color: "green" }, expand: { label: "扩大", color: "orange" },
  restrict: { label: "收紧", color: "gold" }, revoke: { label: "移除", color: "red" },
  mixed: { label: "混合", color: "purple" },
} as const

function downloadCsv(filename: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/csv;charset=utf-8" }))
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

function grantSummary(value?: Record<string, unknown> | null) {
  if (!value) return "无授权"
  const list = (key: string) => Array.isArray(value[key])
    ? (value[key] as unknown[]).map(String).join("、") || "无"
    : "无"
  const scope = typeof value.scope_type === "string" ? value.scope_type : "—"
  const expiry = typeof value.sensitive_actions_expires_at === "string"
    ? new Date(value.sensitive_actions_expires_at).toLocaleString("zh-CN") : "—"
  return `权限：${list("permissions")}；高风险动作：${list("sensitive_actions")}；数据范围：${scope}（${list("department_ids")}）；到期：${expiry}`
}

function SnapshotTable({ item }: { item: PagePermissionHistoryItemOut }) {
  return <Table rowKey="page_key" size="small" pagination={false}
    dataSource={item.grants || []} scroll={{ x: 760, y: 420 }} columns={[
      { title: "页面键", dataIndex: "page_key", width: 220 },
      { title: "权限", dataIndex: "permissions", width: 150,
        render: (value?: string[]) => value?.join("、") || "无" },
      { title: "高风险动作", dataIndex: "sensitive_actions", width: 180,
        render: (value?: string[]) => value?.join("、") || "无" },
      { title: "数据范围", dataIndex: "scope_type", width: 130 },
      { title: "指定部门", dataIndex: "department_ids", width: 180,
        render: (value?: string[]) => value?.join("、") || "—" },
      { title: "高风险到期", dataIndex: "sensitive_actions_expires_at", width: 180,
        render: (value?: string | null) => value ? new Date(value).toLocaleString("zh-CN") : "—" },
    ]} />
}

function RollbackPreview({ preview }: { preview: PagePermissionRollbackPreviewOut }) {
  return <div className="space-y-3">
    <Alert showIcon type={preview.affected_user_count ? "warning" : "info"}
      title={`将产生 ${preview.changes?.length ?? 0} 项页面变化，影响 ${preview.affected_user_count} 人`}
      description={`权限扩大 ${preview.expanded_user_count} 人，权限收紧 ${preview.restricted_user_count} 人，混合变化 ${preview.mixed_user_count} 人；涉及用户覆盖 ${preview.users_with_overrides} 人。`} />
    <Table rowKey="page_key" size="small" pagination={false} dataSource={preview.changes || []}
      scroll={{ y: 320 }} columns={[
        { title: "页面", dataIndex: "page_name", width: 180 },
        { title: "变化", dataIndex: "kind", width: 90,
          render: (value: keyof typeof changeLabels) => <Tag color={changeLabels[value].color}>{changeLabels[value].label}</Tag> },
        { title: "当前值", dataIndex: "before", width: 260,
          render: (value?: Record<string, unknown> | null) => grantSummary(value) },
        { title: "回滚后", dataIndex: "after", width: 260,
          render: (value?: Record<string, unknown> | null) => grantSummary(value) },
        { title: "说明", dataIndex: "summary", width: 180 },
      ]} />
    {!!preview.affected_user_samples?.length && <Typography.Text type="secondary">
      影响样例：{preview.affected_user_samples.map((item) => `${item.user_name}（${item.impact}）`).join("、")}
    </Typography.Text>}
  </div>
}

export function PagePermissionHistoryDrawer({ targetType, targetId, targetName,
  grantVersion, open, onClose, onRolledBack }: {
  targetType: "role" | "user"
  targetId: string
  targetName: string
  grantVersion: number
  open: boolean
  onClose: () => void
  onRolledBack: () => void | Promise<void>
}) {
  const { message, modal } = App.useApp()
  const loadVersion = useRef(0)
  const [items, setItems] = useState<PagePermissionHistoryItemOut[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [actorOptions, setActorOptions] = useState<{ value: string; label: string }[]>([])
  const [isTruncated, setIsTruncated] = useState(false)
  const [loading, setLoading] = useState(false)
  const [rollingBack, setRollingBack] = useState<string>()
  const [previewing, setPreviewing] = useState<string>()
  const [exporting, setExporting] = useState(false)
  const [reason, setReason] = useState("")
  const [source, setSource] = useState<PagePermissionHistoryQuery["source"]>()
  const [changeKind, setChangeKind] = useState<PagePermissionHistoryQuery["change_kind"]>()
  const [pageKey, setPageKey] = useState("")
  const [actorId, setActorId] = useState<string>()
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const load = async (overrides: PagePermissionHistoryQuery = {}) => {
    const version = ++loadVersion.current
    setLoading(true)
    const query: PagePermissionHistoryQuery = {
      source, change_kind: changeKind, actor_user_id: actorId, page_key: pageKey.trim() || undefined,
      date_from: dateRange?.[0]?.startOf("day").toISOString(),
      date_to: dateRange?.[1]?.endOf("day").toISOString(), page, page_size: pageSize,
      ...overrides,
    }
    try {
      const next = targetType === "role"
        ? await getRolePagePermissionHistory(targetId, query)
        : await getUserPagePermissionHistory(targetId, query)
      if (version === loadVersion.current) {
        setItems(next.items || [])
        setTotal(next.total)
        setPage(next.page)
        setPageSize(next.page_size)
        setActorOptions((next.actor_options || []).map((actor) => ({
          value: actor.user_id, label: actor.user_name,
        })))
        setIsTruncated(Boolean(next.is_truncated))
      }
    } catch (error) {
      if (version === loadVersion.current) message.error(error instanceof Error ? error.message : "授权历史加载失败")
    } finally {
      if (version === loadVersion.current) setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    const task = window.setTimeout(() => {
      setReason(""); setSource(undefined); setChangeKind(undefined); setPageKey(""); setActorId(undefined); setDateRange(null); setPage(1)
      void load({ source: undefined, change_kind: undefined, actor_user_id: undefined, page_key: undefined, date_from: undefined, date_to: undefined, page: 1 })
    }, 0)
    return () => { window.clearTimeout(task); loadVersion.current += 1 }
  // target identity is intentionally the reload boundary.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, targetId, targetType])

  const rollback = async (item: PagePermissionHistoryItemOut, idempotencyKey: string) => {
    const version = loadVersion.current
    setRollingBack(item.id)
    try {
      const payload = { audit_id: item.id, expected_grant_version: grantVersion,
        reason: reason.trim(), idempotency_key: idempotencyKey }
      const response = targetType === "role"
        ? await rollbackRolePagePermissions(targetId, payload)
        : await rollbackUserPagePermissions(targetId, payload)
      if (version !== loadVersion.current) return
      if (!response.ok) throw new Error(response.message)
      message.success("授权已恢复到所选历史版本")
      setReason("")
      await onRolledBack()
      onClose()
    } catch (error) {
      if (version === loadVersion.current) message.error(error instanceof Error ? error.message : "授权回滚失败")
      throw error
    } finally {
      if (version === loadVersion.current) setRollingBack(undefined)
    }
  }

  const previewRollback = async (item: PagePermissionHistoryItemOut) => {
    if (!reason.trim()) { message.warning("请填写回滚原因"); return }
    setPreviewing(item.id)
    try {
      const request = { audit_id: item.id, expected_grant_version: grantVersion }
      const preview = targetType === "role"
        ? await previewRolePagePermissionRollback(targetId, request)
        : await previewUserPagePermissionRollback(targetId, request)
      const idempotencyKey = crypto.randomUUID()
      modal.confirm({ title: `确认恢复到 v${item.grant_version ?? "历史"}？`, width: 880,
        content: <RollbackPreview preview={preview} />, okText: "确认回滚", cancelText: "返回历史",
        onOk: () => rollback(item, idempotencyKey) })
    } catch (error) {
      message.error(error instanceof Error ? error.message : "回滚影响预演失败")
    } finally { setPreviewing(undefined) }
  }

  const exportHistory = async () => {
    setExporting(true)
    try {
      const result = targetType === "role"
        ? await exportRolePagePermissionHistory(targetId)
        : await exportUserPagePermissionHistory(targetId)
      downloadCsv(result.filename, result.content)
      message.success("授权历史已导出")
    } catch (error) {
      message.error(error instanceof Error ? error.message : "授权历史导出失败")
    } finally { setExporting(false) }
  }

  return <Drawer title={`${targetName} · 授权历史`} open={open} onClose={onClose}
    size="min(1080px, 100vw)">
    <Alert className="mb-4" showIcon type="info"
      title="回滚前会预演字段变化与用户影响"
      description="系统会校验当前授权版本，回滚会创建新版本并保留完整审计链。重复提交使用同一幂等键，不会生成重复版本。" />
    <Input className="mb-3" value={reason} maxLength={500}
      onChange={(event) => setReason(event.target.value)} placeholder="填写回滚原因" />
    <Space wrap className="mb-4">
      <Select allowClear value={source} placeholder="变更来源" style={{ width: 130 }}
        onChange={setSource} options={Object.entries(sourceLabels).map(([value, item]) => ({ value, label: item.label }))} />
      <Select allowClear value={changeKind} placeholder="变化类型" style={{ width: 120 }}
        onChange={setChangeKind} options={Object.entries(changeLabels).map(([value, item]) => ({ value, label: item.label }))} />
      <Select allowClear showSearch value={actorId} placeholder="操作人" style={{ width: 150 }}
        onChange={setActorId} options={actorOptions} optionFilterProp="label" />
      <Input value={pageKey} onChange={(event) => setPageKey(event.target.value)}
        placeholder="页面键" style={{ width: 190 }} onPressEnter={() => void load()} />
      <DatePicker.RangePicker value={dateRange} onChange={(value) => setDateRange(value)} />
      <Button type="primary" onClick={() => { setPage(1); void load({ page: 1 }) }} loading={loading}>查询</Button>
      <Button onClick={() => { setSource(undefined); setChangeKind(undefined); setActorId(undefined); setPageKey(""); setDateRange(null); setPage(1); void load({ source: undefined, change_kind: undefined, actor_user_id: undefined, page_key: undefined, date_from: undefined, date_to: undefined, page: 1 }) }}>重置</Button>
      <Button loading={exporting} onClick={() => void exportHistory()}>导出历史（最多 5000 条）</Button>
    </Space>
    {isTruncated && <Alert className="mb-3" type="warning" showIcon
      title="当前精细筛选仅扫描最近 5000 条历史" description="请增加时间或操作人条件以缩小范围，导出文件同样最多包含最近 5000 条。" />}
    <Table rowKey="id" loading={loading} dataSource={items} pagination={{
      current: page, pageSize, total, showSizeChanger: true,
      pageSizeOptions: [10, 20, 50, 100], showTotal: (count) => `共 ${count} 条`,
      onChange: (nextPage, nextPageSize) => {
        setPage(nextPage); setPageSize(nextPageSize)
        void load({ page: nextPage, page_size: nextPageSize })
      },
    }}
      scroll={{ x: 920 }} locale={{ emptyText: <Empty description="当前筛选没有授权历史" /> }} columns={[
        { title: "时间", dataIndex: "created_at", width: 170,
          render: (value: string) => new Date(value).toLocaleString("zh-CN") },
        { title: "版本", dataIndex: "grant_version", width: 80,
          render: (value?: number) => value == null ? <Tag>历史</Tag> : <Tag color="blue">v{value}</Tag> },
        { title: "来源 / 操作人", key: "source", width: 170,
          render: (_: unknown, item: PagePermissionHistoryItemOut) => <div>
            <Tag color={sourceLabels[item.source].color}>{sourceLabels[item.source].label}</Tag>
            <Typography.Text className="block mt-1">{item.actor_name || "系统"}</Typography.Text>
          </div> },
        { title: "变更", key: "change", render: (_: unknown, item: PagePermissionHistoryItemOut) => <div>
          <Typography.Text>{item.reason || "未记录原因"}</Typography.Text>
          <div className="mt-1">{(item.changes || []).slice(0, 3).map((change) => <Tag key={change.page_key}
            color={changeLabels[change.kind].color}>{change.page_name} · {changeLabels[change.kind].label}</Tag>)}</div>
          <Typography.Text type="secondary" className="mt-1 block text-xs">
            {item.grants?.length || 0} 个页面授权 · {item.changes?.length ?? 0} 项变化{item.rollback_of ? " · 回滚产生" : ""}
          </Typography.Text>
        </div> },
        { title: "操作", key: "action", width: 180, fixed: "right" as const,
          render: (_: unknown, item: PagePermissionHistoryItemOut) => <Space>
            <Button size="small" onClick={() => modal.info({ title: `v${item.grant_version ?? "历史"} 完整快照`, width: 980, content: <SnapshotTable item={item} /> })}>查看快照</Button>
            <Button size="small" loading={previewing === item.id || rollingBack === item.id}
              disabled={Boolean(previewing || rollingBack)} onClick={() => void previewRollback(item)}>恢复</Button>
          </Space> },
      ]} />
    <Typography.Text type="secondary">当前授权版本 v{grantVersion}</Typography.Text>
  </Drawer>
}
