"use client"

import { useEffect, useRef, useState } from "react"
import { App, Button, Input, Progress, Radio, Space, Table, Tag } from "antd"
import { applyDeptRolesToUser } from "@/actions/admin"
import { fetchAdminUsers, type AdminUserItem, type AdminUserQuery, type RoleItem } from "@/lib/api/client/admin"

type ApplyResult = { id: string; name: string; success: boolean; message: string }

export function BatchApplyDeptRoles({ role, departmentId, departmentName, onRunningChange }: {
  role: RoleItem; departmentId?: string; departmentName?: string; onRunningChange: (running: boolean) => void
}) {
  const { modal } = App.useApp()
  const [users, setUsers] = useState<AdminUserItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [keyword, setKeyword] = useState("")
  const [selected, setSelected] = useState<AdminUserItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState("")
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<ApplyResult[]>([])
  const [reload, setReload] = useState(0)
  const [scope, setScope] = useState<AdminUserQuery["user_scope"]>("department")
  const busy = useRef(false)

  useEffect(() => {
    let cancelled = false
    fetchAdminUsers({ keyword, offset: (page - 1) * 20, limit: 20,
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

  const confirmApply = () => {
    if (busy.current || !selected.length) return
    const targets = [...selected]
    const roleIds = [role.id]
    onRunningChange(true)
    modal.confirm({
      title: `确认向 ${targets.length} 位用户应用“${role.name}”？`,
      content: <div>
        <p>用户：{targets.map((user) => user.name).join("、")}</p>
        <p>追加所选角色，保留已有角色。仅修改勾选用户的角色，不修改部门信息。</p>
      </div>,
      okText: "确认应用",
      cancelText: "取消",
      onCancel: () => onRunningChange(false),
      onOk: async () => {
        if (busy.current) return
        busy.current = true
        setRunning(true)
        setResults([])
        const completed: ApplyResult[] = []
        try {
          for (const user of targets) {
            try {
              const result = await applyDeptRolesToUser(user.id, roleIds)
              completed.push({ id: user.id, name: user.name, success: result.ok, message: result.ok ? "角色已应用" : result.message })
            } catch (cause) {
              completed.push({ id: user.id, name: user.name, success: false, message: cause instanceof Error ? cause.message : "请求失败，请核对用户权限后重试" })
            }
            setResults([...completed])
          }
          setSelected(targets.filter((user) => completed.some((item) => item.id === user.id && !item.success)))
          setLoading(true)
          setReload((value) => value + 1)
        } finally {
          busy.current = false
          setRunning(false)
          onRunningChange(false)
        }
      },
    })
  }

  return <section aria-label="部门用户角色分配">
    <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
      <Space wrap>
        <span>角色：{role.name}</span><span>部门：{departmentName || departmentId}</span>
        <Radio.Group value={scope} disabled={running} options={[
          { label: "相关部门", value: "department" }, { label: "无部门名称", value: "missing" }, { label: "全部用户", value: "all" },
        ]} onChange={(event) => {
          setScope(event.target.value); setPage(1); setLoading(true); setError("")
        }} />
      </Space>
      <Input.Search placeholder="按姓名搜索用户" allowClear disabled={running} onSearch={(value) => {
        setLoading(true); setError(""); setPage(1); setKeyword(value); setReload((current) => current + 1)
      }} />
      {error && <div role="alert">{error}<Button onClick={() => {
        setLoading(true); setReload((value) => value + 1)
      }}>重试</Button></div>}
      <Table<AdminUserItem> rowKey="id" size="small" loading={loading} dataSource={error ? [] : users}
        scroll={{ x: 560 }} columns={[
          { title: "姓名", dataIndex: "name" },
          { title: "部门", render: (_, user) => user.department?.trim() || "未显示部门" },
          { title: "已有手动角色", render: (_, user) => user.roles.map((role) => role.name).join("、") || "未分配" },
        ]}
        rowSelection={{ selectedRowKeys: selected.map((user) => user.id), preserveSelectedRowKeys: true,
          onChange: (_, rows) => setSelected(rows), getCheckboxProps: () => ({ disabled: running }) }}
        pagination={{ current: page, total, pageSize: 20, showSizeChanger: false, disabled: running,
          onChange: (value) => { setLoading(true); setError(""); setPage(value) } }} />
      <Space wrap>
        <span>已选 {selected.length} 位用户（支持跨页选择，每次最多 100 位）</span>
        <Button disabled={running || !selected.length} onClick={() => setSelected([])}>清空选择</Button>
        <Button type="primary" loading={running} disabled={running || loading || !!error || !selected.length || selected.length > 100} onClick={confirmApply}>
          {results.some((item) => !item.success) ? "重试所选用户" : "保存应用角色"}
        </Button>
      </Space>
      {running && <Progress percent={Math.round(results.length / selected.length * 100)} />}
      {results.length > 0 && <>
        <div role="status">{`${running ? "处理中" : "处理完成"}：成功 ${results.filter((item) => item.success).length} 位，失败 ${results.filter((item) => !item.success).length} 位`}</div>
        <Table<ApplyResult> rowKey="id" size="small" dataSource={results} pagination={{ pageSize: 10 }} columns={[
          { title: "用户", dataIndex: "name" },
          { title: "结果", render: (_, item) => <Tag color={item.success ? "success" : "error"}>{item.success ? "成功" : "失败"}</Tag> },
          { title: "说明", dataIndex: "message" },
        ]} />
      </>}
    </Space>
  </section>
}
