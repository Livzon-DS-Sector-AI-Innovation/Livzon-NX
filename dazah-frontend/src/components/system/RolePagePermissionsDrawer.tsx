"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Alert, App, Button, Checkbox, ConfigProvider, Drawer, Input, Segmented, Select, Space, Table, Typography } from "antd"
import {
  getRolePagePermissions,
  replaceRolePagePermissions,
  type RolePagePermissionsOut,
} from "@/actions/admin"
import type { RoleItem } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { getPermissionModuleName } from "@/lib/menu-config"
import { changePageLevels, highRiskPageKeys, PAGE_DATA_SCOPE_VISIBLE, pageGrantChanges } from "@/lib/page-permission-editor"
import type { ColumnsType } from "antd/es/table"
import type { components } from "@/types/generated/schema"
import { PagePermissionDiff } from "@/components/shared/PagePermissionDiff"

type Level = "access" | "query" | "operate"
type Grant = {
  permissions: Level[]
  sensitiveActions: string[]
  scopeType: "not_applicable" | "department_tree" | "departments" | "all" | "self"
  departmentIds: string[]
}
const order: Level[] = ["access", "query", "operate"]
const labels = { access: "访问", query: "查询", operate: "操作" }
const scopeNames: Record<string, string> = {
  not_applicable: "不适用", department_tree: "本部门及下级",
  departments: "指定部门及下级", all: "全部部门", self: "仅本人",
}

function normalize(values: Level[]): Level[] {
  const selected = new Set(values)
  if (selected.has("operate")) selected.add("query")
  if (selected.has("query")) selected.add("access")
  if (!selected.has("access")) selected.clear()
  else if (!selected.has("query")) selected.delete("operate")
  return order.filter((value) => selected.has(value))
}

function editableState(result: RolePagePermissionsOut): Record<string, Grant> {
  const existing = new Map((result.grants || []).map((grant) => [grant.page_key, grant]))
  return Object.fromEntries((result.definitions || []).map((definition) => {
    const grant = existing.get(definition.page_key)
    return [definition.page_key, {
      permissions: normalize((grant?.permissions || []) as Level[]),
      sensitiveActions: grant?.sensitive_actions || [],
      scopeType: grant?.data_scope.scope_type || definition.supported_scope_types?.[0] || "not_applicable",
      departmentIds: grant?.data_scope.department_ids || [],
    }]
  }))
}

export function RolePagePermissionsDrawer({ role, departments, open, onClose }: {
  role: RoleItem | null
  departments: DepartmentItem[]
  open: boolean
  onClose: () => void
}) {
  const { message, modal } = App.useApp()
  const loadVersion = useRef(0)
  const savingVersion = useRef<number | null>(null)
  const roleId = role?.id
  const [result, setResult] = useState<RolePagePermissionsOut | null>(null)
  const [editable, setEditable] = useState<Record<string, Grant>>({})
  const [moduleCode, setModuleCode] = useState("hr")
  const [reason, setReason] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [errorMessage, setErrorMessage] = useState("")
  const [refreshVersion, setRefreshVersion] = useState(0)
  const [authorizedOnly, setAuthorizedOnly] = useState(false)
  const [expandedKeys, setExpandedKeys] = useState<string[]>([])

  useEffect(() => {
    const version = ++loadVersion.current
    if (!open || !roleId) return
    queueMicrotask(() => {
      if (version !== loadVersion.current) return
      setLoading(true)
      setSaving(false)
      savingVersion.current = null
      setResult(null)
      setReason("")
      setErrorMessage("")
      void getRolePagePermissions(roleId).then((next) => {
        if (version !== loadVersion.current) return
        if (next.role_id !== roleId) throw new Error("角色授权返回对象不一致，请重新加载")
        setResult(next)
        setEditable(editableState(next))
        setExpandedKeys(highRiskPageKeys(next.definitions || []))
        if (next.definitions?.[0]) setModuleCode(next.definitions[0].module_code)
        setReason("")
        setErrorMessage("")
      }).catch((error) => { if (version === loadVersion.current) setErrorMessage(error instanceof Error ? error.message : "加载角色页面权限失败") })
        .finally(() => { if (version === loadVersion.current) setLoading(false) })
    })
    return () => { loadVersion.current += 1 }
  }, [open, roleId, refreshVersion])

  const modules = useMemo(() => Array.from(new Set(
    (result?.definitions || []).map((definition) => definition.module_code),
  )), [result])
  const definitions = (result?.definitions || []).filter(
    (definition) => result?.role_id === role?.id && definition.module_code === moduleCode
      && (!authorizedOnly || Boolean(editable[definition.page_key]?.permissions.length)),
  )
  const update = (pageKey: string, patch: Partial<Grant>) => setEditable((current) => ({
    ...current, [pageKey]: { ...current[pageKey], ...patch },
  }))
  const changes = result ? pageGrantChanges(result.definitions || [], editableState(result), editable,
    new Map(departments.map((department) => [department.feishu_department_id, department.name]))) : []
  const inCurrentSession = (action: () => void | Promise<void>) => {
    const version = loadVersion.current
    return () => { if (version === loadVersion.current) return action() }
  }
  const close = () => {
    if (!changes.length) return onClose()
    modal.confirm({ title: "放弃未保存的角色授权？", content: "当前更改尚未保存，继续后将丢失。",
      okText: "放弃更改", cancelText: "继续编辑", onOk: inCurrentSession(onClose) })
  }

  const save = async () => {
    if (!open || !role || !result || result.role_id !== role.id || loading || saving) return
    const version = loadVersion.current
    if (savingVersion.current === version) return
    if (!reason.trim()) {
      message.warning("请填写本次角色授权调整原因")
      return
    }
    savingVersion.current = version
    setSaving(true)
    try {
      const grants = Object.entries(editable).flatMap(([pageKey, grant]) =>
        grant.permissions.length || grant.sensitiveActions.length ? [{
          page_key: pageKey,
          mode: "custom" as const,
          permissions: grant.permissions,
          sensitive_actions: grant.sensitiveActions,
          data_scope: {
            scope_type: grant.scopeType,
            department_ids: grant.scopeType === "departments" ? grant.departmentIds : [],
          },
        }] : [],
      )
      const response = await replaceRolePagePermissions(role.id, {
        expected_grant_version: result.grant_version,
        grants,
        reason: reason.trim(),
      })
      if (version !== loadVersion.current) return
      if (!response.ok) throw new Error(response.message)
      const next = response.data
      if (next.role_id !== role.id) throw new Error("角色授权返回对象不一致，请重新加载")
      setResult(next)
      setEditable(editableState(next))
      setReason("")
      setErrorMessage("")
      message.success("角色页面权限已保存")
    } catch (error) {
      if (version !== loadVersion.current) return
      setErrorMessage(`${error instanceof Error ? error.message : "保存角色页面权限失败"}。本地修改已保留；如版本冲突，请刷新最新授权后重新调整。`)
    } finally {
      if (version === loadVersion.current) {
        savingVersion.current = null
        setSaving(false)
      }
    }
  }

  const previewSave = () => {
    if (!reason.trim()) { message.warning("请填写本次角色授权调整原因"); return }
    if (!changes.length) { message.info("没有需要保存的权限调整"); return }
    modal.confirm({ title: `确认调整${role?.name || "角色"}的页面权限`, width: 900,
      content: <PagePermissionDiff changes={changes} />, okText: "确认保存", cancelText: "返回修改", onOk: inCurrentSession(save) })
  }

  return <Drawer title={`${role?.name || "角色"} · 页面权限基线`} open={open} onClose={close}
    loading={loading} size="min(1080px, 100vw)" footer={<div className="flex gap-3">
      <Input disabled={loading || saving} value={reason} onChange={(event) => setReason(event.target.value)}
        placeholder="填写角色授权调整原因" maxLength={500} />
      <Button type="primary" loading={saving} onClick={previewSave}
        disabled={loading || !result || result.role_id !== role?.id}>预览并保存基线</Button>
    </div>}>
    <Typography.Paragraph type="secondary">
      这里只配置可访问模块内的菜单页面、查询和操作权限，不会开启一级模块入口；用户有精确覆盖时，以用户覆盖为准。
    </Typography.Paragraph>
    {errorMessage && <Alert className="mb-4" type="error" showIcon title={errorMessage}
      action={<Button size="small" onClick={() => modal.confirm({ title: "重新加载最新角色授权？",
        content: "刷新会放弃未保存的本地调整，请先核对需要保留的更改。", okText: "重新加载", cancelText: "继续编辑",
        onOk: inCurrentSession(() => { setLoading(true); setRefreshVersion((version) => version + 1) }),
      })}>重新加载</Button>} />}
    <ConfigProvider componentDisabled={loading || saving || result?.role_id !== roleId}>
    <Segmented className="mb-4" value={moduleCode} onChange={(value) => setModuleCode(String(value))}
      options={modules.map((code) => ({ value: code, label: getPermissionModuleName(code) }))} />
    <Space wrap className="mb-4">
      <Checkbox checked={authorizedOnly} onChange={(event) => setAuthorizedOnly(event.target.checked)}>只看已授权页面</Checkbox>
      <Typography.Text type="secondary">当前模块内页面批量设置：</Typography.Text>
      {(['access', 'query', 'operate', 'none'] as const).map((level) => <Button key={level} size="small"
        danger={level === 'none'} onClick={() => setEditable((current) => ({ ...current,
          ...Object.fromEntries((result?.definitions || []).filter((definition) => definition.module_code === moduleCode)
            .map((definition) => [definition.page_key, { ...current[definition.page_key],
              permissions: level === 'none' ? [] : normalize([level]), sensitiveActions: [] }])) }))}>
        {level === 'none' ? '清空基线' : level === 'access' ? '仅访问' : level === 'query' ? '只读' : '可操作'}
      </Button>)}
    </Space>
    <Table rowKey="page_key" dataSource={definitions} pagination={{ pageSize: 20 }} scroll={{ x: 850 }}
      columns={([
        { title: "菜单页面", dataIndex: "page_name", key: "page_name", width: 200 },
        { title: "权限", key: "permissions", width: 260, render: (_, definition) => {
          const state = editable[definition.page_key]
          return <Checkbox.Group value={state?.permissions || []} onChange={(values) => {
            const permissions = changePageLevels(state?.permissions || [], values as Level[])
            update(definition.page_key, { permissions, sensitiveActions: permissions.includes("operate") ? state.sensitiveActions : [] })
          }}><Space>{order.map((level) => <Checkbox key={level} value={level}>{labels[level]}</Checkbox>)}</Space></Checkbox.Group>
        } },
        { title: "数据范围", key: "scope", render: (_, definition) => {
          const state = editable[definition.page_key]
          return <div className="flex gap-2"><Select className="min-w-40" value={state?.scopeType}
            options={(definition.supported_scope_types || []).map((value) => ({ value, label: scopeNames[value] || value }))}
            onChange={(scopeType) => update(definition.page_key, { scopeType, departmentIds: [] })} />
            {state?.scopeType === "departments" && <Select mode="multiple" className="min-w-56"
              value={state.departmentIds} options={departments.map((department) => ({
                value: department.feishu_department_id, label: department.name,
              }))} onChange={(departmentIds) => update(definition.page_key, { departmentIds })} />}</div>
        } },
      ] satisfies ColumnsType<components['schemas']['PagePermissionDefinitionOut']>).filter((column) => PAGE_DATA_SCOPE_VISIBLE || column.key !== 'scope')}
      expandable={{ expandedRowKeys: expandedKeys, onExpandedRowsChange: (keys) => setExpandedKeys(keys.map(String)),
        rowExpandable: (definition) => Boolean(definition.sensitive_actions?.length), expandedRowRender: (definition) => {
        const actions = definition.sensitive_actions || []
        const state = editable[definition.page_key]
        return actions.length ? <Checkbox.Group value={state?.sensitiveActions || []}
          onChange={(values) => update(definition.page_key, {
            sensitiveActions: values as string[],
            permissions: values.length ? normalize([...(state?.permissions || []), "operate"]) : state?.permissions || [],
          })}>{actions.map((action) => <Checkbox key={action.key} value={action.key}
            title={action.description}>{action.name}</Checkbox>)}</Checkbox.Group>
          : <Typography.Text type="secondary">此页面没有独立高风险动作。</Typography.Text>
      } }} />
    </ConfigProvider>
  </Drawer>
}
