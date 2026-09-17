"use client"

import { useEffect, useMemo, useState } from "react"
import { Alert, App, Button, Card, Empty, Select, Space, Statistic, Table, Tag, Typography } from "antd"
import { EditOutlined, ReloadOutlined, ToolOutlined } from "@ant-design/icons"
import { getPagePermissionHealth, remediatePagePermissionHealth, type PagePermissionHealthOut } from "@/actions/admin"
import { getPermissionDepartments, getUsers, type UserManagementItem } from "@/actions/users"
import { fetchRoles, type RoleItem } from "@/lib/api/client/admin"
import type { DepartmentItem } from "@/lib/api/server/admin"
import { RolePagePermissionsDrawer } from "./RolePagePermissionsDrawer"
import ModulePermissionsDrawer from "@/components/settings/ModulePermissionsDrawer"
import { getPermissionModuleName } from "@/lib/menu-config"

type HealthIssue = NonNullable<PagePermissionHealthOut["issues"]>[number]

const issueLabels: Record<string, string> = {
  retired_page: "页面已停用", invalid_department: "部门已失效",
  missing_module_access: "缺少模块入口", redundant_user_override: "冗余用户覆盖",
  sensitive_without_expiry: "高风险权限无期限", sensitive_expired: "高风险权限已到期",
  sensitive_expiring: "高风险权限即将到期",
}

export function PagePermissionHealthPanel() {
  const { message, modal } = App.useApp()
  const [result, setResult] = useState<PagePermissionHealthOut>()
  const [loading, setLoading] = useState(false)
  const [fixing, setFixing] = useState<string>()
  const [severity, setSeverity] = useState("all")
  const [issueCode, setIssueCode] = useState("all")
  const [targetType, setTargetType] = useState("all")
  const [moduleCode, setModuleCode] = useState("all")
  const [roleTarget, setRoleTarget] = useState<RoleItem | null>(null)
  const [userTarget, setUserTarget] = useState<UserManagementItem | null>(null)
  const [departments, setDepartments] = useState<DepartmentItem[]>([])
  const load = async () => {
    setLoading(true)
    try { setResult(await getPagePermissionHealth()) }
    catch (error) { message.error(error instanceof Error ? error.message : "权限健康检查失败") }
    finally { setLoading(false) }
  }
  useEffect(() => {
    const task = window.setTimeout(() => void load(), 0)
    return () => window.clearTimeout(task)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const issues = useMemo(() => (result?.issues || []).filter((item) =>
    (severity === "all" || item.severity === severity)
    && (issueCode === "all" || item.code === issueCode)
    && (targetType === "all" || item.target_type === targetType)
    && (moduleCode === "all" || item.module_code === moduleCode)),
  [issueCode, moduleCode, result, severity, targetType])
  const modules = useMemo(() => Array.from(new Set(
    (result?.issues || []).map((item) => item.module_code).filter(Boolean) as string[],
  )).sort(), [result])

  const openEditor = async (item: HealthIssue) => {
    try {
      if (item.target_type === "role") {
        const [roles, nextDepartments] = await Promise.all([fetchRoles(), getPermissionDepartments()])
        const role = roles.find((entry) => entry.id === item.target_id)
        if (!role) throw new Error("角色已不存在，请重新检查")
        setDepartments(nextDepartments)
        setRoleTarget(role)
      } else {
        const response = await getUsers({ status: "active" })
        const user = response.items.find((entry) => entry.id === item.target_id)
        if (!user) throw new Error("用户已不存在，请重新检查")
        setUserTarget(user)
      }
    } catch (error) {
      message.error(error instanceof Error ? error.message : "授权编辑器加载失败")
    }
  }

  const fixIssue = (item: HealthIssue) => {
    const key = `${item.code}:${item.target_type}:${item.target_id}:${item.page_key}`
    modal.confirm({
      title: item.remediation === "prune_departments" ? "清除失效部门引用？" : "自动修复此权限问题？",
      content: item.remediation === "prune_departments"
        ? "仅清除已失效的部门；如果全部指定部门均已失效，将转到授权编辑器重新选择。"
        : item.code === "redundant_user_override"
          ? "将删除冗余用户覆盖并恢复角色基线。" : "将移除已停用页面的无效授权。",
      okText: "确认修复", cancelText: "取消",
      onOk: async () => {
        setFixing(key)
        const response = await remediatePagePermissionHealth({
          code: item.code as "retired_page" | "invalid_department" | "redundant_user_override",
          target_type: item.target_type, target_id: item.target_id, page_key: item.page_key,
          expected_grant_version: item.grant_version,
          reason: `权限健康检查自动修复：${issueLabels[item.code] || item.code}`,
        })
        setFixing(undefined)
        if (!response.ok) {
          message.warning(response.message)
          if (item.remediation === "prune_departments") await openEditor(item)
          return
        }
        message.success(response.data.message)
        await load()
      },
    })
  }

  return <Card title="权限健康检查" size="small" extra={<Button size="small"
    icon={<ReloadOutlined />} loading={loading} onClick={() => void load()}>重新检查</Button>}>
    <Typography.Paragraph type="secondary">
      检查失效页面和部门、无模块入口授权、冗余用户覆盖，以及高风险权限的到期状态，并可直接定位或修复。
    </Typography.Paragraph>
    {result && <><Space size="large" wrap className="mb-4">
      <Statistic title="问题总数" value={result.issue_count} />
      <Statistic title="错误" value={result.error_count} valueStyle={{ color: "#cf1322" }} />
      <Statistic title="提醒" value={result.warning_count} valueStyle={{ color: "#d48806" }} />
    </Space>{!result.issue_count && <Alert className="mb-4" type="success" showIcon title="未发现页面权限健康问题" />}</>}
    <Space wrap className="mb-4">
      <Select value={severity} onChange={setSeverity} className="w-32" options={[
        { value: "all", label: "全部级别" }, { value: "error", label: "错误" }, { value: "warning", label: "提醒" },
      ]} />
      <Select value={targetType} onChange={setTargetType} className="w-32" options={[
        { value: "all", label: "全部对象" }, { value: "role", label: "角色" }, { value: "user", label: "用户" },
      ]} />
      <Select value={issueCode} onChange={setIssueCode} className="w-52" options={[
        { value: "all", label: "全部问题" },
        ...Object.entries(issueLabels).map(([value, label]) => ({ value, label })),
      ]} />
      <Select value={moduleCode} onChange={setModuleCode} className="w-40" options={[
        { value: "all", label: "全部模块" },
        ...modules.map((value) => ({ value, label: getPermissionModuleName(value) })),
      ]} />
      <Typography.Text type="secondary">当前显示 {issues.length} 条</Typography.Text>
    </Space>
    <Table rowKey={(item) => `${item.code}:${item.target_type}:${item.target_id}:${item.page_key}`}
      loading={loading} dataSource={issues} pagination={{ pageSize: 10 }} scroll={{ x: 1100 }}
      locale={{ emptyText: <Empty description="暂无健康问题" /> }} columns={[
        { title: "级别", dataIndex: "severity", width: 80,
          render: (value: string) => <Tag color={value === "error" ? "error" : "warning"}>{value === "error" ? "错误" : "提醒"}</Tag> },
        { title: "问题", dataIndex: "code", width: 170, render: (value: string) => issueLabels[value] || value },
        { title: "对象", key: "target", width: 180, render: (_: unknown, item: HealthIssue) => <div>{item.target_name}
          <Typography.Text type="secondary" className="block text-xs">{item.target_type === "role" ? "角色" : "用户"}</Typography.Text></div> },
        { title: "页面", key: "page", width: 240, render: (_: unknown, item: HealthIssue) => <div>{item.page_name}
          <Typography.Text type="secondary" className="block text-xs">{item.page_key}</Typography.Text></div> },
        { title: "说明", dataIndex: "detail" },
        { title: "操作", key: "actions", width: 190, fixed: "right", render: (_: unknown, item: HealthIssue) => {
          const key = `${item.code}:${item.target_type}:${item.target_id}:${item.page_key}`
          return <Space><Button size="small" icon={<EditOutlined />} onClick={() => void openEditor(item)}>编辑</Button>
            {item.remediation !== "edit" && <Button size="small" type="primary" icon={<ToolOutlined />}
              loading={fixing === key} onClick={() => fixIssue(item)}>修复</Button>}</Space>
        } },
      ]} />
    <RolePagePermissionsDrawer role={roleTarget} departments={departments} open={Boolean(roleTarget)}
      onClose={() => { setRoleTarget(null); void load() }} />
    <ModulePermissionsDrawer user={userTarget} open={Boolean(userTarget)}
      onClose={() => { setUserTarget(null); void load() }} />
  </Card>
}
