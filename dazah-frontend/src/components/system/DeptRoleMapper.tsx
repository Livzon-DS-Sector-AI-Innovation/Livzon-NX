"use client"

import { useEffect, useState } from "react"
import { Form, Input, Select, Tabs } from "antd"
import { SEARCH_DELAY_MS } from "@/hooks/useSearchFilter"
import type { DeptRuleItem, RoleItem } from "@/lib/api/client/admin"
import { BatchApplyRoles } from "./BatchApplyRoles"

interface DeptRoleMapperProps {
  initialRules: DeptRuleItem[]
  initialRoles: RoleItem[]
  initialDepartments: unknown[]
}

type DepartmentSelection = { role_id: string; department_id?: string; department_name?: string }

export function DeptRoleMapper({ initialRoles }: DeptRoleMapperProps) {
  const [mode, setMode] = useState("users")
  const [activeFilterKey, setActiveFilterKey] = useState<string | null>(null)
  const [composing, setComposing] = useState(false)
  const [running, setRunning] = useState(false)
  const [form] = Form.useForm<DepartmentSelection>()
  const roleId = Form.useWatch("role_id", form)
  const departmentId = Form.useWatch("department_id", form)?.trim() || undefined
  const departmentName = Form.useWatch("department_name", form)?.trim() || undefined
  const role = initialRoles.find((item) => item.id === roleId)
  const filterKey = role && (departmentId || departmentName) ? JSON.stringify([role.id, departmentId, departmentName]) : null

  useEffect(() => {
    if (!filterKey || composing || filterKey === activeFilterKey) return
    const timer = window.setTimeout(() => setActiveFilterKey(filterKey), SEARCH_DELAY_MS)
    return () => window.clearTimeout(timer)
  }, [activeFilterKey, composing, filterKey])

  const departmentInputProps = {
    allowClear: true,
    maxLength: 255,
    style: { width: 240, maxWidth: "100%" },
    onCompositionStart: () => setComposing(true),
    onCompositionEnd: () => setComposing(false),
  }

  return <Tabs activeKey={mode} onChange={setMode} items={[
    {
      key: "users",
      label: "搜索用户",
      disabled: running && mode !== "users",
      children: <BatchApplyRoles roles={initialRoles} onRunningChange={setRunning} />,
    },
    {
      key: "department",
      label: "按部门查询",
      disabled: running && mode !== "department",
      children: <div className="space-y-4">
        <Form form={form} layout="vertical" disabled={running} component="div">
          <div className="flex flex-wrap items-start gap-3">
            <Form.Item name="role_id" label="已有角色" required>
              <Select placeholder="选择角色" showSearch={{ optionFilterProp: "label" }} style={{ width: 240 }}
                options={initialRoles.map((item) => ({ value: item.id, label: item.name }))} />
            </Form.Item>
            <Form.Item name="department_id" label="飞书部门 ID" extra="飞书部门 ID 和部门名称至少填写一项">
              <Input {...departmentInputProps} placeholder="输入飞书部门 ID" />
            </Form.Item>
            <Form.Item name="department_name" label="部门名称">
              <Input {...departmentInputProps} placeholder="输入部门名称" />
            </Form.Item>
          </div>
        </Form>
        {filterKey && filterKey === activeFilterKey && role && <BatchApplyRoles
          key={filterKey} role={role}
          departmentId={departmentId} departmentName={departmentName}
          onRunningChange={setRunning} />}
      </div>,
    },
  ]} />
}
