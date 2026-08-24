"use client"

import { useMemo } from "react"
import { Radio, Tree } from "antd"
import type { TreeDataNode } from "antd"
import type { DepartmentItem } from "@/lib/api/server/admin"

export type DataScopeSelection = {
  scopeType: "all" | "departments" | null // null = 默认（本部门+子部门）
  departmentNames: string[]
}

interface DataScopeConfigProps {
  departments: DepartmentItem[]
  value: DataScopeSelection
  onChange: (selection: DataScopeSelection) => void
}

/**
 * 可见部门配置（后台可配置，不写死）：
 * - 默认：本部门 + 子部门（未配置时的兜底规则）
 * - 全部部门：可看全厂数据（如高管）
 * - 指定部门：勾选可见部门集合
 */
export function DataScopeConfig({ departments, value, onChange }: DataScopeConfigProps) {
  const deptTreeData = useMemo(() => {
    const byParent = new Map<string, DepartmentItem[]>()
    for (const dept of departments) {
      const parentKey = dept.parent_feishu_department_id ?? ""
      const list = byParent.get(parentKey) ?? []
      list.push(dept)
      byParent.set(parentKey, list)
    }
    const build = (parentKey: string): TreeDataNode[] =>
      (byParent.get(parentKey) ?? [])
        .sort((a, b) => a.name.localeCompare(b.name, "zh"))
        .map((dept) => ({
          key: dept.name,
          title: dept.name,
          children: build(dept.feishu_department_id),
        }))
    return build("")
  }, [departments])

  return (
    <div>
      <Radio.Group
        value={value.scopeType ?? "default"}
        onChange={(e) => {
          const scopeType = e.target.value as "default" | "all" | "departments"
          onChange({
            scopeType: scopeType === "default" ? null : scopeType,
            departmentNames: scopeType === "departments" ? value.departmentNames : [],
          })
        }}
      >
        <Radio value="default">默认（本部门 + 子部门）</Radio>
        <Radio value="all">全部部门</Radio>
        <Radio value="departments">指定部门</Radio>
      </Radio.Group>
      {value.scopeType === "departments" && (
        <div className="mt-2 max-h-64 overflow-y-auto border rounded-md p-3">
          <Tree
            key="data-scope-dept-tree"
            checkable
            checkedKeys={value.departmentNames}
            onCheck={(keys) =>
              onChange({ scopeType: "departments", departmentNames: keys as string[] })
            }
            treeData={deptTreeData}
            defaultExpandAll
            selectable={false}
            showLine={{ showLeafIcon: false }}
          />
        </div>
      )}
    </div>
  )
}