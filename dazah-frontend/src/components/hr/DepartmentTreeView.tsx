'use client'

import { useState, useMemo, useCallback } from 'react'
import {
  Tree,
  Input,
  Button,
  Space,
  Tag,
  Badge,
  Dropdown,
} from 'antd'
import type { MenuProps } from 'antd'
import type { DataNode } from 'antd/es/tree'
import {
  SearchOutlined,
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  ExpandOutlined,
  CompressOutlined,
  ApartmentOutlined,
} from '@ant-design/icons'
import { Department } from '@/types/hr'

interface DepartmentTreeViewProps {
  departments: Department[]
  selectedDepartmentId: string | null
  canEdit: boolean
  onSelect: (id: string | null) => void
  onAdd: (parentId?: string) => void
  onEdit: (dept: Department) => void
  onDelete: (id: string) => void
  onRefresh: () => void
  onNodeClick: (id: string) => void
}

/**
 * 将后端返回的部门数据（支持嵌套和扁平两种格式）转换为 antd Tree 节点。
 *
 * 后端 get_department_tree 返回的是已嵌套的 Department[]（含 children 字段），
 * 扁平列表（如 list_departments）需要按 parent_id 自行构建树。
 */
function buildTreeData(departments: Department[]): DataNode[] {
  // 检测是否为已嵌套格式：首层元素是否有 children
  const isNested = departments.length > 0 && departments[0].children !== undefined

  if (isNested) {
    // 已嵌套：直接递归转换
    const convert = (list: Department[]): DataNode[] =>
      list.map((dept) => ({
        key: dept.id,
        title: dept.name,
        isLeaf: !dept.children || dept.children.length === 0,
        children: dept.children && dept.children.length > 0 ? convert(dept.children) : undefined,
        _dept: dept,
      }))
    return convert(departments)
  }

  // 扁平列表：按 parent_id 构建树
  const deptMap = new Map<string, Department>()
  departments.forEach((dept) => deptMap.set(dept.id, dept))

  const roots: Department[] = []
  departments.forEach((dept) => {
    if (!dept.parent_id || !deptMap.has(dept.parent_id)) {
      roots.push(dept)
    }
  })

  const buildChildren = (parentId: string): DataNode[] | undefined => {
    const children = departments
      .filter((d) => d.parent_id === parentId)
      .map((dept) => ({
        key: dept.id,
        title: dept.name,
        isLeaf: !departments.some((d) => d.parent_id === dept.id),
        children: buildChildren(dept.id),
        _dept: dept,
      }))
    return children.length > 0 ? children : undefined
  }

  return roots.map((dept) => ({
    key: dept.id,
    title: dept.name,
    isLeaf: !departments.some((d) => d.parent_id === dept.id),
    children: buildChildren(dept.id),
    _dept: dept,
  }))
}

function filterTree(nodes: DataNode[], keyword: string): DataNode[] {
  const lowerKeyword = keyword.toLowerCase()

  return nodes
    .map((node) => {
      const matchSelf =
        typeof node.title === 'string' &&
        (node.title as string).toLowerCase().includes(lowerKeyword)
      const filteredChildren = node.children
        ? filterTree(node.children, keyword)
        : undefined

      if (matchSelf || (filteredChildren && filteredChildren.length > 0)) {
        return {
          ...node,
          children: filterTree(
            node.children || [],
            keyword,
          ),
        }
      }

      return null
    })
    .filter(Boolean) as DataNode[]
}

function collectAllKeys(nodes: DataNode[]): React.Key[] {
  const keys: React.Key[] = []
  const walk = (list: DataNode[]) => {
    list.forEach((node) => {
      keys.push(node.key)
      if (node.children) {
        walk(node.children)
      }
    })
  }
  walk(nodes)
  return keys
}

export default function DepartmentTreeView({
  departments,
  selectedDepartmentId,
  canEdit,
  onSelect,
  onAdd,
  onEdit,
  onDelete,
  onRefresh,
  onNodeClick,
}: DepartmentTreeViewProps) {
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([])
  const [searchKeyword, setSearchKeyword] = useState('')
  const [searchExpanded, setSearchExpanded] = useState(false)

  const rawTreeData = useMemo(
    () => buildTreeData(departments),
    [departments],
  )

  const allKeys = useMemo(() => collectAllKeys(rawTreeData), [rawTreeData])

  const filteredTreeData = useMemo(() => {
    if (!searchKeyword.trim()) return rawTreeData
    return filterTree(rawTreeData, searchKeyword.trim())
  }, [rawTreeData, searchKeyword])

  // 搜索时自动展开所有匹配的节点
  const filteredKeys = useMemo(
    () => collectAllKeys(filteredTreeData),
    [filteredTreeData],
  )

  const handleSearch = useCallback(
    (value: string) => {
      setSearchKeyword(value)
      if (value.trim()) {
        setExpandedKeys(filteredKeys)
        setSearchExpanded(true)
      } else {
        setSearchExpanded(false)
      }
    },
    [filteredKeys],
  )

  const handleExpandAll = () => {
    setExpandedKeys(allKeys)
  }

  const handleCollapseAll = () => {
    setExpandedKeys([])
  }

  const handleSelect = (selectedKeys: React.Key[]) => {
    if (selectedKeys.length > 0) {
      onSelect(selectedKeys[0] as string)
    } else {
      onSelect(null)
    }
  }

  const handleExpand = (keys: React.Key[]) => {
    setExpandedKeys(keys)
  }

  // 递归渲染树节点，用 Dropdown 包裹实现右键菜单
  const getContextMenuItems = (dept: Department): MenuProps['items'] =>
    canEdit
      ? [
          {
            key: 'add-child',
            label: '新增子部门',
            icon: <PlusOutlined />,
            onClick: () => onAdd(dept.id),
          },
          {
            key: 'edit',
            label: '编辑',
            icon: <EditOutlined />,
            onClick: () => onEdit(dept),
          },
          {
            key: 'delete',
            label: '删除',
            icon: <DeleteOutlined />,
            danger: true,
            onClick: () => onDelete(dept.id),
          },
        ]
      : []

  const renderTreeTitle = (nodes: DataNode[]): DataNode[] => {
    return nodes.map((node) => {
      const dept = (node as any)._dept as Department | undefined
      return {
        ...node,
        title: dept ? (
          <Dropdown
            menu={{ items: getContextMenuItems(dept) }}
            trigger={['contextMenu']}
          >
            <span
              className="inline-flex items-center gap-2"
              onClick={() => onNodeClick(dept.id)}
            >
              <ApartmentOutlined className="text-[var(--color-primary)]" />
              <span className="font-medium">{dept.name}</span>
              {dept.leader_name && (
                <Tag color="blue" className="text-xs leading-none">
                  {dept.leader_name}
                </Tag>
              )}
              {(dept.current_count !== undefined || dept.headcount !== undefined) && (
                <Badge
                  count={dept.current_count ?? dept.headcount}
                  overflowCount={99999}
                  style={{ backgroundColor: dept.current_count !== undefined ? '#52c41a' : '#d9d9d9' }}
                  title={dept.current_count !== undefined ? `在岗人数: ${dept.current_count}` : `编制人数: ${dept.headcount}`}
                  className="ml-1"
                />
              )}
            </span>
          </Dropdown>
        ) : (
          node.title
        ),
        children: node.children ? renderTreeTitle(node.children) : undefined,
      }
    })
  }

  const treeData = useMemo(
    () => renderTreeTitle(filteredTreeData),
    [filteredTreeData, departments],
  )

  return (
    <div className="h-full flex flex-col">
      {/* 搜索与操作栏 */}
      <div className="flex items-center gap-2 mb-3">
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索部门名称..."
          allowClear
          value={searchKeyword}
          onChange={(e) => handleSearch(e.target.value)}
          className="flex-1"
        />
        <Space.Compact>
          <Button
            icon={<ExpandOutlined />}
            size="small"
            title="展开全部"
            onClick={handleExpandAll}
          />
          <Button
            icon={<CompressOutlined />}
            size="small"
            title="收起全部"
            onClick={handleCollapseAll}
          />
        </Space.Compact>
      </div>

      {/* 虚拟滚动树 */}
      <div className="flex-1 overflow-auto">
        {treeData.length > 0 ? (
          <Tree
            treeData={treeData}
            selectedKeys={selectedDepartmentId ? [selectedDepartmentId] : []}
            expandedKeys={
              searchExpanded
                ? expandedKeys
                : expandedKeys.length > 0
                  ? expandedKeys
                  : allKeys.slice(0, 50)
            }
            onSelect={handleSelect}
            onExpand={handleExpand}
            blockNode
            virtual
            height={600}
            showIcon={false}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400">
            <div className="text-center">
              <ApartmentOutlined className="text-4xl mb-2" />
              <p>{searchKeyword ? '无匹配部门' : '暂无部门数据'}</p>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
