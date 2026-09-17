"use client"

import { useEffect, useMemo, useRef, useState } from "react"
import { Alert, App, Button, Card, Select, Space, Tag, Typography } from "antd"
import { simulatePagePermission, type PagePermissionSimulationOut } from "@/actions/admin"
import {
  getUserPagePermissions,
  getUsers,
  type PagePermissionDefinitionOut,
  type UserManagementItem,
} from "@/actions/users"
import { getPermissionModuleName } from "@/lib/menu-config"
import { pagePermissionTierLabel, pageScopeSummary } from "@/lib/page-permission-editor"

const permissionOptions = [
  { value: "access", label: "进入页面" },
  { value: "query", label: "查看数据" },
  { value: "operate", label: "普通操作" },
] as const

export function PagePermissionDiagnostics() {
  const { message } = App.useApp()
  const loadVersion = useRef(0)
  const [users, setUsers] = useState<UserManagementItem[]>([])
  const [definitions, setDefinitions] = useState<PagePermissionDefinitionOut[]>([])
  const [userId, setUserId] = useState<string>()
  const [pageKey, setPageKey] = useState<string>()
  const [permission, setPermission] = useState<"access" | "query" | "operate">("query")
  const [sensitiveAction, setSensitiveAction] = useState<string>()
  const [result, setResult] = useState<PagePermissionSimulationOut>()
  const [loadingPages, setLoadingPages] = useState(false)
  const [checking, setChecking] = useState(false)

  useEffect(() => {
    let active = true
    void getUsers({ status: "active" }).then((response) => {
      if (active) setUsers(response.items || [])
    }).catch((error) => {
      if (active) message.error(error instanceof Error ? error.message : "用户列表加载失败")
    })
    return () => { active = false; loadVersion.current += 1 }
  }, [message])

  const definition = useMemo(
    () => definitions.find((item) => item.page_key === pageKey), [definitions, pageKey]
  )
  const selectUser = async (nextUserId: string) => {
    const version = ++loadVersion.current
    setUserId(nextUserId)
    setPageKey(undefined)
    setSensitiveAction(undefined)
    setResult(undefined)
    setLoadingPages(true)
    try {
      const response = await getUserPagePermissions(nextUserId)
      if (version !== loadVersion.current) return
      setDefinitions(response.definitions || [])
    } catch (error) {
      if (version !== loadVersion.current) return
      setDefinitions([])
      message.error(error instanceof Error ? error.message : "页面权限目录加载失败")
    } finally {
      if (version === loadVersion.current) setLoadingPages(false)
    }
  }
  const verify = async () => {
    if (!userId || !pageKey) return
    setChecking(true)
    setResult(undefined)
    try {
      setResult(await simulatePagePermission({
        user_id: userId, page_key: pageKey, permission,
        sensitive_action: sensitiveAction || null,
      }))
    } catch (error) {
      message.error(error instanceof Error ? error.message : "权限诊断失败")
    } finally {
      setChecking(false)
    }
  }

  const effective = result?.effective
  const source = effective?.source === "user" ? "用户覆盖"
    : effective?.source === "role" ? `角色：${effective.source_role_names?.join("、") || "未命名角色"}`
      : effective?.source === "super_admin" ? "系统管理员" : "未授权"

  return <Card title="单用户权限诊断" size="small">
    <Typography.Paragraph type="secondary">
      按用户、菜单页面和业务动作预判授权条件，并显示模块入口、授权来源与数据范围。实际接口还会核对页面绑定、数据范围及业务规则。
    </Typography.Paragraph>
    <Space wrap align="start">
      <Select showSearch optionFilterProp="label" className="min-w-56" placeholder="选择用户"
        value={userId} options={users.map((user) => ({ value: user.id, label: `${user.name}${user.department ? ` · ${user.department}` : ""}` }))}
        onChange={(value) => void selectUser(value)} />
      <Select showSearch optionFilterProp="label" className="min-w-72" placeholder="选择菜单页面"
        loading={loadingPages} disabled={!userId} value={pageKey}
        options={definitions.map((item) => ({ value: item.page_key,
          label: `${getPermissionModuleName(item.module_code)} · ${item.page_name}` }))}
        onChange={(value) => { setPageKey(value); setSensitiveAction(undefined); setResult(undefined) }} />
      <Select className="min-w-32" value={permission} options={[...permissionOptions]}
        onChange={(value) => { setPermission(value); setResult(undefined) }} />
      <Select allowClear className="min-w-48" placeholder="高风险动作（可选）"
        disabled={!definition?.sensitive_actions?.length} value={sensitiveAction}
        options={(definition?.sensitive_actions || []).map((action) => ({ value: action.key, label: action.name }))}
        onChange={(value) => { setSensitiveAction(value); setResult(undefined) }} />
      <Button type="primary" loading={checking} disabled={!userId || !pageKey} onClick={() => void verify()}>
        验证当前权限
      </Button>
    </Space>
    {result && <Alert className="mt-4" showIcon type={result.allowed ? "success" : "error"}
      title={result.allowed ? "授权条件满足" : "授权条件不满足"} description={<div className="space-y-2">
        <div>{result.reason}</div>
        <Space wrap>
          <Tag>来源：{source}</Tag>
          <Tag>最终档位：{pagePermissionTierLabel(effective?.permissions || [])}</Tag>
          <Tag>数据范围：{pageScopeSummary(effective?.data_scope.scope_type || "not_applicable", effective?.data_scope.department_ids || [])}</Tag>
        </Space>
        {!!effective?.resolution?.length && <div>
          <Typography.Text strong>判定过程</Typography.Text>
          <ul className="mb-0 mt-1 pl-5">
            {effective.resolution.map((item) => <li key={item}>{item}</li>)}
          </ul>
        </div>}
        {!!effective?.role_sources?.length && <div>
          <Typography.Text strong>角色贡献</Typography.Text>
          <div className="mt-1 space-y-1">{effective.role_sources.map((item) => <div key={item.role_id}>
            <Tag color="geekblue">{item.role_name}</Tag>
            <Typography.Text type="secondary">
              {pagePermissionTierLabel(item.permissions || [])} · {pageScopeSummary(
                item.data_scope.scope_type, item.data_scope.department_ids || [])}
              {!!item.sensitive_actions?.length && ` · 高风险动作 ${item.sensitive_actions.length} 项`}
            </Typography.Text>
          </div>)}</div>
        </div>}
      </div>} />}
  </Card>
}
