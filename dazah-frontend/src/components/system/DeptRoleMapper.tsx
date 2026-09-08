"use client"

import { useState } from "react"
import { Button, Form, Input, Select } from "antd"
import type { DeptRuleItem, RoleItem } from "@/lib/api/client/admin"
import { BatchApplyDeptRoles } from "./BatchApplyDeptRoles"

interface DeptRoleMapperProps {
  initialRules: DeptRuleItem[]
  initialRoles: RoleItem[]
  initialDepartments: unknown[]
}

type DepartmentSelection = { role_id: string; department_id?: string; department_name?: string }

export function DeptRoleMapper({ initialRoles }: DeptRoleMapperProps) {
  const [selection, setSelection] = useState<DepartmentSelection | null>(null)
  const [running, setRunning] = useState(false)
  const [form] = Form.useForm<DepartmentSelection>()
  const role = initialRoles.find((item) => item.id === selection?.role_id)

  return <div className="space-y-4">
    <Form form={form} layout="vertical" disabled={running}
      onValuesChange={() => setSelection(null)}
      onFinish={(values) => setSelection({
        role_id: values.role_id,
        department_id: values.department_id?.trim() || undefined,
        department_name: values.department_name?.trim() || undefined,
      })}>
      <div className="flex flex-wrap items-start gap-3">
        <Form.Item name="role_id" label="已有角色" rules={[{ required: true, message: "请选择角色" }]}>
          <Select placeholder="选择角色" showSearch optionFilterProp="label" style={{ width: 240 }}
            options={initialRoles.map((item) => ({ value: item.id, label: item.name }))} />
        </Form.Item>
        <Form.Item name="department_id" label="飞书部门 ID" dependencies={["department_name"]} rules={[
          { validator: (_, value: string | undefined) => value?.trim() || form.getFieldValue("department_name")?.trim()
            ? Promise.resolve() : Promise.reject(new Error("飞书部门 ID 或部门名称至少填写一个")) },
        ]}>
          <Input placeholder="输入飞书部门 ID" maxLength={255} style={{ width: 240 }} />
        </Form.Item>
        <Form.Item name="department_name" label="部门名称">
          <Input placeholder="输入部门名称" maxLength={255} style={{ width: 240 }} />
        </Form.Item>
        <Form.Item label={<span aria-hidden="true">&nbsp;</span>} colon={false}>
          <Button htmlType="submit" disabled={running}>查询部门用户</Button>
        </Form.Item>
      </div>
    </Form>
    {selection && role && <BatchApplyDeptRoles
      key={JSON.stringify(selection)} role={role}
      departmentId={selection.department_id} departmentName={selection.department_name}
      onRunningChange={setRunning} />}
  </div>
}
