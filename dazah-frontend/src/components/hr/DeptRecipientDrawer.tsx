'use client'

import { useEffect, useState } from 'react'
import { App, Drawer, Table, Switch, Select, Button, Space, Typography } from 'antd'
import { SaveOutlined, CheckOutlined } from '@ant-design/icons'
import { fetchDeptRecipients, type DeptRecipientVM as DeptRecipient } from '@/lib/api/client/hr'
import { saveDeptRecipients } from '@/actions/hr'

interface DeptNode {
  name?: string
  children?: DeptNode[]
}

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

// 从部门树为每个部门（含子孙节点）建立「叶子部门名 -> 该部门名」归属映射，
// 用于把细粒度成员（车队/绿化/磅房等）归到其所属的配置部门下筛选
function collectMembership(nodes: DeptNode[], rootName: string, map: Record<string, string>): Record<string, string> {
  for (const n of nodes) {
    if (!n.name) continue
    map[n.name] = rootName
    if (n.children?.length) {
      collectMembership(n.children, rootName, map)
    }
  }
  return map
}

function findDeptNode(nodes: DeptNode[], name: string): DeptNode | undefined {
  for (const n of nodes) {
    if (n.name === name) return n
    if (n.children?.length) {
      const found = findDeptNode(n.children, name)
      if (found) return found
    }
  }
  return undefined
}

// 部门列表以「部门审批人配置」同款粒度为准（排除总经办、汇总车间展开为子车间等），
// 与合同审批解析的部门粒度保持一致；树仅用于成员归属映射
function buildMembership(treeData: DeptNode[], deptNames: string[]): Record<string, string> {
  const membership: Record<string, string> = {}
  for (const name of deptNames) {
    const node = findDeptNode(treeData, name)
    if (node) {
      collectMembership([node], name, membership)
    } else {
      membership[name] = name
    }
  }
  return membership
}

// ─── 配置部门名单的业务调整（以「部门审批人配置」名单为基础）───

/** 部门合并：多个子部门合并为一个配置条目（人员按部门树归属自动归并） */
const DEPT_MERGE: Record<string, string> = {
  '103一车间': '103车间',
  '103二车间': '103车间',
  '103车间公用部门': '103车间',
}

/** 部门改名：对齐人员实际所在部门名（否则该条目匹配不到人） */
const DEPT_RENAME: Record<string, string> = {
  '生产部': '生产管理',
}

/** 从名单中移除的部门（保留其子部门条目） */
const DEPT_REMOVE = new Set(['研发部'])

/** 人员互选的部门组：组内任一条目配置时，可选组内全部部门成员（配置条目仍各自保存） */
const DEPT_MEMBER_POOLS: Record<string, string[]> = {
  '201二车间': ['201二车间', '201二车间（多拉）', '201三车间'],
  '201二车间（多拉）': ['201二车间', '201二车间（多拉）', '201三车间'],
  '201三车间': ['201二车间', '201二车间（多拉）', '201三车间'],
}

function transformDeptNames(raw: string[]): string[] {
  const result: string[] = []
  for (const n of raw) {
    if (DEPT_REMOVE.has(n)) continue
    const target = DEPT_MERGE[n] || DEPT_RENAME[n] || n
    if (!result.includes(target)) result.push(target)
  }
  return result
}

export default function DeptRecipientDrawer({ open, onClose, reminderConfigId, hrMembers = [], mode = 'recipient' }: Props) {
  const { message } = App.useApp()
  const [rows, setRows] = useState<DeptRow[]>([])
  const [membership, setMembership] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open || !reminderConfigId) return
    ;(async () => {
      setLoading(true)
      try {
        const [recipients, deptCfgRes, treeRes] = await Promise.all([
          fetchDeptRecipients(reminderConfigId),
          fetch('/api/v1/hr/dept-approval-configs/names', { cache: 'no-store' }).then(r => r.json()),
          fetch('/api/v1/hr/departments/tree', { cache: 'no-store' }).then(r => r.json()),
        ])
        // 部门粒度与「部门审批人配置」一致（201一车间/201二车间/行政部 等，不含车队/绿化等细级），
        // 再叠加业务调整：103 合并、生产部改名、剔除研发部
        const deptNames = transformDeptNames((deptCfgRes.data ?? []).filter(Boolean))
        const treeData = treeRes.data || []
        const membership = buildMembership(treeData, deptNames)
        setMembership(membership)
        // 历史已保存的细粒度（叶子部门）配置，按归属归并到对应部门行
        const recipientMap: Record<string, DeptRecipient> = {}
        for (const r of recipients) {
          const rootName = membership[r.department] || DEPT_RENAME[r.department] || r.department
          const existing = recipientMap[rootName]
          if (!existing) {
            recipientMap[rootName] = r
          } else if (!existing.recipient_open_ids?.length && r.recipient_open_ids?.length) {
            recipientMap[rootName] = r
          }
        }
        setRows(deptNames.map((name: string) => {
          const existing = recipientMap[name]
          return {
            key: name,
            department: name,
            parent_department: '',
            leader_name: undefined,
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
    // 函数式更新：onChange 中连续两次 updateRow 时基于最新 rows 依次生效，
    // 避免后者覆盖前者（旧实现导致 recipient_open_ids 永远为空、点击无法选中）
    setRows(prev => prev.map(r => (r.key === key ? { ...r, [field]: value } : r)))
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
        // 筛选该部门下的人员（含细粒度子级成员，按归属映射归到部门）；
        // 互选组（如 201二车间/多拉/三车间）内任一条目可选组内全部人员
        const pool = DEPT_MEMBER_POOLS[r.department]
        const deptMembers = hrMembers.filter(m =>
          pool
            ? pool.includes(m.department)
            : m.department === r.department || membership[m.department] === r.department
        )
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
        <Table
          rowKey="key"
          columns={columns}
          dataSource={rows}
          pagination={false}
          size="small"
        />
      )}
    </Drawer>
  )
}
