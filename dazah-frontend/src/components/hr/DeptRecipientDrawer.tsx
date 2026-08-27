'use client'

import { useEffect, useState, useMemo } from 'react'
import { App, Drawer, Table, Switch, Select, Button, Space, Typography, Collapse, Tag } from 'antd'
import { SaveOutlined, CheckOutlined } from '@ant-design/icons'
import { fetchDeptRecipients, type DeptRecipientVM as DeptRecipient } from '@/lib/api/client/hr'
import { saveDeptRecipients } from '@/actions/hr'

interface DeptRow {
  key: string
  department: string
  parent_department: string
  leader_name?: string
  use_dept_leader: boolean
  recipient_open_ids: string[]
  recipient_names: string[]
  existing_id?: string
}

interface Props {
  open: boolean
  onClose: () => void
  reminderConfigId: string
  hrMembers?: { open_id: string; name: string; department: string }[]
  /** recipient=按部门配置接收人（通用）；clerk=按部门配置签署办事员（合同签署用） */
  mode?: 'recipient' | 'clerk'
}

// 递归展平部门树，返回所有节点（一级+二级+子级）
function flattenTree(nodes: { id?: string; name?: string; leader_name?: string; children?: any[]; parent_id?: string }[], parentName: string): { id?: string; name: string; leader_name?: string; parent: string }[] {
  const result: { id?: string; name: string; leader_name?: string; parent: string }[] = []
  for (const n of nodes) {
    if (!n.name) continue
    result.push({ id: n.id, name: n.name, leader_name: n.leader_name, parent: parentName })
    if (n.children?.length) {
      result.push(...flattenTree(n.children, n.name))
    }
  }
  return result
}

export default function DeptRecipientDrawer({ open, onClose, reminderConfigId, hrMembers = [], mode = 'recipient' }: Props) {
  const { message } = App.useApp()
  const [rows, setRows] = useState<DeptRow[]>([])
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !reminderConfigId) return
    ;(async () => {
      setLoading(true)
      try {
        const [recipients, treeRes] = await Promise.all([
          fetchDeptRecipients(reminderConfigId),
          fetch('/api/v1/hr/departments/tree', { cache: 'no-store' }).then(r => r.json()),
        ])
        const treeData = treeRes.data || []
        // 展平全部部门（一级+二级+子级）
        const flat = flattenTree(treeData, '')
        const recipientMap: Record<string, DeptRecipient> = {}
        for (const r of recipients) {
          recipientMap[r.department] = r
        }
        setRows(flat.map((dept, idx) => {
          const existing = recipientMap[dept.name]
          return {
            key: dept.id || `${dept.name}_${idx}`,
            department: dept.name,
            parent_department: dept.parent,
            leader_name: dept.leader_name,
            use_dept_leader: existing?.use_dept_leader ?? true,
            recipient_open_ids: existing?.recipient_open_ids || [],
            recipient_names: existing?.recipient_names || [],
            existing_id: existing?.id,
          }
        }))
      } catch {
        message.error('加载失败')
      } finally {
        setLoading(false)
      }
    })()
  }, [open, reminderConfigId, message])

  // 按一级部门分组
  const grouped = useMemo(() => {
    const groups: Record<string, DeptRow[]> = {}
    for (const r of rows) {
      const key = r.parent_department || r.department
      if (!groups[key]) groups[key] = []
      groups[key].push(r)
    }
    return Object.entries(groups)
  }, [rows])

  const handleSave = async () => {
    setSaving(true)
    try {
      const isClerk = mode === 'clerk'
      const data = rows
        .filter(r => isClerk || !r.use_dept_leader || r.recipient_names.length > 0)
        .map(r => ({
          reminder_config_id: reminderConfigId,
          department: r.department,
          recipient_open_ids: r.recipient_open_ids,
          recipient_names: r.recipient_names,
          // clerk 模式不使用「部门负责人」语义
          use_dept_leader: isClerk ? false : r.use_dept_leader,
        }))
      await saveDeptRecipients(reminderConfigId, data)
      message.success('保存成功')
    } catch {
      message.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 全选：全部使用部门负责人
  const handleSelectAll = () => {
    setRows(rows.map(r => ({
      ...r,
      use_dept_leader: true,
      recipient_open_ids: [],
      recipient_names: [],
    })))
    message.info('已全部设为使用部门负责人')
  }

  const updateRow = (key: string, field: keyof DeptRow, value: unknown) => {
    setRows(rows.map(r => (r.key === key ? { ...r, [field]: value } : r)))
  }

  const columns = [
    {
      title: '部门',
      dataIndex: 'department',
      width: 150,
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    ...(mode === 'clerk'
      ? []
      : [{
          title: '使用部门负责人',
          dataIndex: 'use_dept_leader',
          width: 200,
          render: (val: boolean, r: DeptRow) => (
            <Space>
              <Switch checked={val} onChange={(v) => updateRow(r.key, 'use_dept_leader', v)} />
              <Typography.Text type="secondary">{r.leader_name || '未设置'}</Typography.Text>
            </Space>
          ),
        }]),
    {
      title: mode === 'clerk' ? '指定办事员' : '指定接收人',
      key: 'recipients',
      width: 300,
      render: (_: unknown, r: DeptRow) => {
        // 筛选该部门下的人员
        const deptMembers = hrMembers.filter(m => m.department === r.department)
        const deptOptions = deptMembers.map(m => ({
          value: m.open_id,
          label: m.name,
        }))

        return (
          <Select
            mode="multiple"
            style={{ width: '100%' }}
            placeholder={mode === 'clerk' ? '选择该部门办事员' : r.use_dept_leader ? '由部门负责人接收' : '选择接收人'}
            value={r.recipient_open_ids}
            onChange={(vals: string[]) => {
              const names = vals.map(id => {
                const member = hrMembers.find(m => m.open_id === id)
                return member?.name || id
              })
              updateRow(r.key, 'recipient_open_ids', vals)
              updateRow(r.key, 'recipient_names', names)
            }}
            options={deptOptions}
            disabled={mode !== 'clerk' && r.use_dept_leader}
            showSearch
            optionFilterProp="label"
            filterOption={(input, option) =>
              (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        )
      },
    },
  ]

  return (
    <Drawer
      title={mode === 'clerk' ? '按部门配置签署办事员' : '按部门配置接收人'}
      open={open}
      onClose={onClose}
      size={750}
      extra={
        <Space>
          {mode !== 'clerk' && (
            <Button icon={<CheckOutlined />} onClick={handleSelectAll}>
              全部使用部门负责人
            </Button>
          )}
          <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
            保存
          </Button>
        </Space>
      }
    >
      <Typography.Paragraph type="secondary" style={{ marginBottom: 16 }}>
        {mode === 'clerk'
          ? '为每个部门指定签署办事员：审批通过后由其通知员工到人事签署合同。未配置的部门使用上方「合同签署设置」中的全局办事员。'
          : '默认自动通知该部门的负责人。如需指定其他人，请关闭开关后输入姓名。'}
      </Typography.Paragraph>
      {loading ? (
        <Typography.Text type="secondary">加载中...</Typography.Text>
      ) : (
        <Collapse
          defaultActiveKey={grouped.map(([g]) => g)}
          items={grouped.map(([group, items]) => ({
            key: group,
            label: (
              <Space>
                <Typography.Text strong>{group}</Typography.Text>
                <Tag color="blue">{items.length}个部门</Tag>
              </Space>
            ),
            children: (
              <Table
                rowKey="key"
                columns={columns}
                dataSource={items}
                pagination={false}
                size="small"
              />
            ),
          }))}
        />
      )}
    </Drawer>
  )
}
