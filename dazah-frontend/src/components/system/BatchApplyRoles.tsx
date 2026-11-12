"use client"

import { useEffect, useId, useRef, useState } from "react"
import { App, Button, Input, Progress, Radio, Select, Space, Table, Tag } from "antd"
import PlatformNotice from "@/components/shared/PlatformNotice"
import { applyDeptRolesToUser } from "@/actions/admin"
import { fetchAdminUsers, type AdminUserItem, type AdminUserQuery, type RoleItem } from "@/lib/api/client/admin"

type Assignment = { user: AdminUserItem; roleIds: string[] }
type ApplyResult = { id: string; name: string; success: boolean; message: string }

type BatchApplyRolesProps = { onRunningChange: (running: boolean) => void } & (
  | { role: RoleItem; departmentId?: string; departmentName?: string; roles?: never }
  | { roles: RoleItem[]; role?: never; departmentId?: never; departmentName?: never }
)

const PAGE_SIZE = 20
const MAX_USERS = 100
const MAX_ROLES = 200

function userLabel(user: AdminUserItem) {
  const detail = [user.department, user.email].filter(Boolean).join(" · ")
  return detail ? `${user.name}（${detail}）` : user.name
}

export function BatchApplyRoles({ role, roles, departmentId, departmentName, onRunningChange }: BatchApplyRolesProps) {
  const { modal } = App.useApp()
  const selectId = useId()
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState("")
  const [selected, setSelected] = useState<Assignment[]>([])
  const [commonRoleIds, setCommonRoleIds] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [running, setRunning] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [results, setResults] = useState<ApplyResult[]>([])
  const [reload, setReload] = useState(0)
  const [scope, setScope] = useState<AdminUserQuery["user_scope"]>(role ? "department" : undefined)
  const busy = useRef(false)
  const locked = confirming || running
  const roleOptions = (roles ?? (role ? [role] : [])).map(({ id, name }) => ({ value: id, label: name }))
  const roleNames = new Map(roleOptions.map(({ value, label }) => [value, label]))
  const canSubmit = !locked && !loading && !error && selected.length > 0 && selected.length <= MAX_USERS
    && selected.every(({ roleIds }) => roleIds.length > 0 && roleIds.every((id) => roleNames.has(id)))

  useEffect(() => {
    let cancelled = false
    fetchAdminUsers({ keyword, offset: (page - 1) * PAGE_SIZE, limit: PAGE_SIZE,
      department_id: departmentId, department_name: departmentName, user_scope: scope,
    }).then((data) => {
      if (cancelled) return
      setUsers(data.items)
      setTotal(data.total)
      setError("")
    }).catch((cause: unknown) => {
      if (!cancelled) setError(cause instanceof Error ? cause.message : "用户加载失败，请重试")
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [keyword, page, reload, departmentId, departmentName, scope])

  const refresh = () => {
    setLoading(true)
    setError("")
    setReload((value) => value + 1)
  }

  const confirmApply = () => {
    if (busy.current || !canSubmit) return
    const targets = selected
    setConfirming(true)
    onRunningChange(true)
    modal.confirm({
      title: role ? `确认向 ${targets.length} 位用户应用“${role.name}”？` : `确认向 ${targets.length} 位用户分配角色？`,
      content: <div>
        <p>将为以下用户追加所列角色，保留已有角色。</p>
        <ul className="max-h-60 list-disc space-y-1 overflow-auto break-words pl-5">
          {targets.map(({ user, roleIds }) => <li key={user.id}>
            {userLabel(user)}：{roleIds.map((id) => roleNames.get(id)).join("、")}
          </li>)}
        </ul>
      </div>,
      okText: role ? "确认应用" : "确认分配",
      cancelText: "取消",
      onCancel: () => {
        setConfirming(false)
        onRunningChange(false)
      },
      onOk: async () => {
        if (busy.current) return
        busy.current = true
        setRunning(true)
        setResults([])
        const completed: ApplyResult[] = []
        const failed: Assignment[] = []
        try {
          for (const target of targets) {
            const { user, roleIds } = target
            const name = userLabel(user)
            try {
              const result = await applyDeptRolesToUser(user.id, roleIds)
              if (!result.ok) failed.push(target)
              completed.push({ id: user.id, name, success: result.ok, message: result.ok ? "角色已应用" : result.message })
            } catch (cause) {
              failed.push(target)
              completed.push({ id: user.id, name, success: false, message: cause instanceof Error ? cause.message : "请求失败，请核对用户权限后重试" })
            }
            setResults([...completed])
          }
          setSelected(failed)
          setCommonRoleIds([])
          refresh()
        } finally {
          busy.current = false
          setRunning(false)
          setConfirming(false)
          onRunningChange(false)
        }
      },
    })
  }

  return <section aria-label={role ? "部门用户角色分配" : "搜索用户批量分配角色"}>
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      {role && <Space wrap>
        <span>角色：{role.name}</span><span>部门：{departmentName || departmentId}</span>
        <Radio.Group value={scope} disabled={locked || loading} options={[
          { label: "相关部门", value: "department" }, { label: "无部门名称", value: "missing" }, { label: "全部用户", value: "all" },
        ]} onChange={(event) => {
          setScope(event.target.value); setPage(1); setLoading(true); setError("")
        }} />
      </Space>}
      <Input.Search
        aria-label={role ? "搜索部门用户" : "搜索用户"}
        placeholder={role ? "按姓名搜索用户" : "按姓名、部门、账号、邮箱、手机号或工号搜索"}
        enterButton="搜索"
        allowClear
        disabled={locked}
        onSearch={(value) => {
          setPage(1)
          setKeyword(value.trim())
          refresh()
      }} />
      {error && <PlatformNotice type="error" title={error} showRulesLink={!!role}
        action={<Button onClick={refresh}>{role ? "重试" : "重试搜索"}</Button>} />}
      {!error && <Table<AdminUserItem> rowKey="id" size="small" loading={loading} dataSource={users}
        locale={{ emptyText: loading ? "正在查询用户" : "未找到符合条件的用户" }}
        scroll={{ x: 560 }} columns={[
          { title: "姓名", dataIndex: "name", render: (_, user) => role ? user.name : <div className="break-words">
            {user.name}
            {user.email && <div className="text-xs text-[var(--color-slate)]">{user.email}</div>}
          </div> },
          { title: "部门", render: (_, user) => user.department?.trim() || "未显示部门" },
          { title: "已有手动角色", render: (_, user) => user.roles.map((role) => role.name).join("、") || "未分配" },
        ]}
        rowSelection={{
          selectedRowKeys: selected.map(({ user }) => user.id),
          preserveSelectedRowKeys: true,
          onChange: (keys) => setSelected((previous) => {
            const assignments = new Map(previous.map((item) => [item.user.id, item]))
            const visibleUsers = new Map(users.map((user) => [user.id, user]))
            return keys.flatMap((key) => {
              const id = String(key)
              const existing = assignments.get(id)
              const user = visibleUsers.get(id)
              if (existing) return [existing]
              return user ? [{ user, roleIds: role ? [role.id] : [] }] : []
            })
          }),
          getCheckboxProps: () => ({ disabled: locked || loading }),
        }}
        pagination={{ current: page, total, pageSize: PAGE_SIZE, showSizeChanger: false, disabled: locked || loading,
          onChange: (value) => { setLoading(true); setPage(value) } }} />}
      {roles && (
        <Space wrap>
          <Select<string[]> id={`${selectId}-common`} mode="multiple" aria-label="共同角色" placeholder="选择共同角色"
            options={roleOptions} value={commonRoleIds} onChange={setCommonRoleIds}
            showSearch={{ optionFilterProp: "label" }} allowClear maxCount={MAX_ROLES} maxTagCount={2}
            disabled={locked || !selected.length} style={{ width: 240 }} />
          <Button disabled={locked || !selected.length || !commonRoleIds.length} onClick={() => {
            setSelected((current) => current.map((item) => ({ ...item, roleIds: commonRoleIds })))
          }}>统一设置待分配角色</Button>
        </Space>
      )}
      {roles && selected.length > 0 && (
        <Table<Assignment> rowKey={({ user }) => user.id} size="small" dataSource={selected}
          scroll={{ x: 320 }} pagination={{ pageSize: 10, showSizeChanger: false }} columns={[
            { title: "已选用户", render: (_, { user }) => <span className="break-words">{userLabel(user)}</span>, width: "40%" },
            { title: "待分配角色", render: (_, { user, roleIds }) => (
              <Select<string[]> id={`${selectId}-user-${user.id}`} mode="multiple"
                aria-label={`${userLabel(user)}的待分配角色`} placeholder="选择角色"
                value={roleIds} options={roleOptions} showSearch={{ optionFilterProp: "label" }}
                maxCount={MAX_ROLES} maxTagCount={3} allowClear disabled={locked} style={{ width: "100%" }}
                onChange={(nextRoles) => setSelected((current) => current.map((item) =>
                  item.user.id === user.id ? { ...item, roleIds: nextRoles } : item
                ))} />
            ) },
            { title: "操作", width: 72, render: (_, { user }) => <Button type="link" disabled={locked}
              aria-label={`移除${userLabel(user)}`}
              onClick={() => setSelected((current) => current.filter((item) => item.user.id !== user.id))}>移除</Button> },
          ]} />
      )}
      <Space wrap>
        <span>已选 {selected.length} 位用户（支持跨页选择，每次最多 {MAX_USERS} 位）</span>
        <Button disabled={locked || !selected.length} onClick={() => {
          setSelected([])
          setCommonRoleIds([])
        }}>清空选择</Button>
        <Button type="primary" loading={running} disabled={!canSubmit} onClick={confirmApply}>
          {role ? (results.some((item) => !item.success) ? "重试所选用户" : "保存应用角色") : "批量分配角色"}
        </Button>
      </Space>
      {running && <Progress percent={Math.round(results.length / selected.length * 100)} />}
      {results.length > 0 && <>
        <div role="status">{`${running ? "处理中" : "处理完成"}：成功 ${results.filter((item) => item.success).length} 位，失败 ${results.filter((item) => !item.success).length} 位`}</div>
        <Table<ApplyResult> rowKey="id" size="small" dataSource={results} pagination={{ pageSize: 10, showSizeChanger: false }} columns={[
          { title: "用户", dataIndex: "name" },
          { title: "结果", render: (_, item) => <Tag color={item.success ? "success" : "error"}>{item.success ? "成功" : "失败"}</Tag> },
          { title: "说明", dataIndex: "message" },
        ]} />
      </>}
    </Space>
  </section>
}
