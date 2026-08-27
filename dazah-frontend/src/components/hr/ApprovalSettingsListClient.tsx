'use client'

import { useEffect, useState, useCallback } from 'react'
import { App, Card, Button, Space, Table, Tag, Typography, AutoComplete, Popconfirm } from 'antd'
import { DeleteOutlined } from '@ant-design/icons'
import { fetchDeptApprovalConfigs, searchFeishuMembers, type DeptApprovalConfigVM, type FeishuContactVM } from '@/lib/api/client/hr'
import { updateDeptApprovalConfigAction, createDeptApprovalConfigAction, deleteDeptApprovalConfigAction } from '@/actions/hr'

type ApproverField = 'direct_leader' | 'manager' | 'director' | 'vp'

const fieldLabels: Record<ApproverField, string> = {
  direct_leader: '直属领导',
  manager: '部门经理',
  director: '部门总监',
  vp: '主管领导',
}

export default function ApprovalSettingsListClient() {
  const { message } = App.useApp()
  const [configs, setConfigs] = useState<DeptApprovalConfigVM[]>([])
  const [loading, setLoading] = useState(false)
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set())
  const [searchResults, setSearchResults] = useState<Record<string, FeishuContactVM[]>>({})

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const data = await fetchDeptApprovalConfigs()
      setConfigs(data || [])
    } catch {
      message.error('加载审批配置失败')
    } finally {
      setLoading(false)
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(loadData)
  }, [loadData])

  const handleContactSearch = useCallback(async (keyword: string, key: string) => {
    if (!keyword || keyword.length < 1) return
    try {
      const members = await searchFeishuMembers(keyword)
      setSearchResults(prev => ({ ...prev, [key]: members }))
    } catch {
      // 静默失败
    }
  }, [])

  const handleContactSelect = (deptId: string, field: ApproverField, member: FeishuContactVM) => {
    setConfigs(prev => prev.map(c => {
      if (c.department_id !== deptId) return c
      return {
        ...c,
        [`${field}_name`]: member.name,
        [`${field}_open_id`]: member.open_id,
      }
    }))
  }

  const handleClearApprover = (deptId: string, field: ApproverField) => {
    setConfigs(prev => prev.map(c => {
      if (c.department_id !== deptId) return c
      return {
        ...c,
        [`${field}_name`]: null,
        [`${field}_open_id`]: null,
      }
    }))
  }

  const handleSave = async (config: DeptApprovalConfigVM) => {
    const key = config.id || config.department_id
    setSavingIds(prev => new Set(prev).add(key))
    try {
      const payload = {
        direct_leader_name: config.direct_leader_name || undefined,
        direct_leader_open_id: config.direct_leader_open_id || undefined,
        manager_name: config.manager_name || undefined,
        manager_open_id: config.manager_open_id || undefined,
        director_name: config.director_name || undefined,
        director_open_id: config.director_open_id || undefined,
        vp_name: config.vp_name || undefined,
        vp_open_id: config.vp_open_id || undefined,
      }
      if (config.id) {
        await updateDeptApprovalConfigAction(config.id, payload)
      } else {
        await createDeptApprovalConfigAction({
          department_id: config.department_id,
          department_name: config.department_name,
          ...payload,
        })
      }
      message.success(`${config.department_name} 配置已保存`)
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '保存失败')
    } finally {
      setSavingIds(prev => { const n = new Set(prev); n.delete(key); return n })
    }
  }

  const handleDelete = async (config: DeptApprovalConfigVM) => {
    if (!config.id) return
    try {
      await deleteDeptApprovalConfigAction(config.id)
      message.success('删除成功')
      loadData()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '删除失败')
    }
  }

  const renderApproverCell = (config: DeptApprovalConfigVM, field: ApproverField) => {
    const name = config[`${field}_name` as keyof DeptApprovalConfigVM] as string | null
    const searchKey = `${config.id}_${field}`
    return (
      <div className="flex items-center gap-1">
        <AutoComplete
          style={{ width: 140 }}
          placeholder={name || `选择${fieldLabels[field]}`}
          filterOption={false}
          onSearch={(value) => handleContactSearch(value, searchKey)}
          onSelect={(value) => {
            const members = searchResults[searchKey] || []
            const member = members.find(m => m.name === value)
            if (member) handleContactSelect(config.department_id, field, member)
          }}
          options={(searchResults[searchKey] || []).map(m => ({
            label: `${m.name} - ${m.department || ''}${m.job_title ? ` - ${m.job_title}` : ''}`,
            value: m.name,
          }))}
          allowClear
          onClear={() => handleClearApprover(config.department_id, field)}
        />
        {name && (
          <Tag color="blue" closable onClose={() => handleClearApprover(config.department_id, field)}>
            {name}
          </Tag>
        )}
      </div>
    )
  }

  const columns = [
    {
      title: '部门名称',
      dataIndex: 'department_name',
      key: 'department_name',
      width: 140,
      fixed: 'left' as const,
      render: (text: string) => <Typography.Text strong>{text}</Typography.Text>,
    },
    {
      title: '直属领导',
      key: 'direct_leader',
      width: 200,
      render: (_: unknown, r: DeptApprovalConfigVM) => renderApproverCell(r, 'direct_leader'),
    },
    {
      title: '部门经理',
      key: 'manager',
      width: 200,
      render: (_: unknown, r: DeptApprovalConfigVM) => renderApproverCell(r, 'manager'),
    },
    {
      title: '部门总监',
      key: 'director',
      width: 200,
      render: (_: unknown, r: DeptApprovalConfigVM) => renderApproverCell(r, 'director'),
    },
    {
      title: '主管领导',
      key: 'vp',
      width: 200,
      render: (_: unknown, r: DeptApprovalConfigVM) => renderApproverCell(r, 'vp'),
    },
    {
      title: '操作',
      key: 'action',
      width: 140,
      fixed: 'right' as const,
      render: (_: unknown, r: DeptApprovalConfigVM) => (
        <Space size="small">
          <Button
            type="primary"
            size="small"
            loading={savingIds.has(r.id || r.department_id)}
            onClick={() => handleSave(r)}
          >
            保存
          </Button>
          {r.id && (
            <Popconfirm
              title="确认删除"
              onConfirm={() => handleDelete(r)}
              okText="确定"
              cancelText="取消"
            >
              <Button type="text" size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold">审批流程设置 - 岗位调动与合同审批</h1>
      </div>

      <Card>
        <div className="mb-4 p-3 bg-blue-50 rounded">
          <Typography.Text strong>岗位调动审批流程说明：</Typography.Text>
          <ul className="mt-2 ml-4 text-sm text-gray-600">
            <li><b>主管以下人员</b>：直属领导 → 部门经理/总监（经理签了总监就不用，同一人自动跳过）</li>
            <li><b>主管以上人员</b>：部门经理 → 部门总监 → 主管领导</li>
            <li>原部门和接收部门各走一遍，最后 HR → 常务副总 → 总经理</li>
            <li>审批人从下表按部门配置，未配置的从部门负责人自动解析</li>
          </ul>
          <div className="mt-3 pt-3 border-t border-blue-200">
            <Typography.Text strong>员工合同到期审批流程说明：</Typography.Text>
            <ul className="mt-2 ml-4 text-sm text-gray-600">
              <li><b>部门经理 = 部门负责人（第一级）</b>：收到合同到期审批卡片并审批（无经理回退直属领导）</li>
              <li><b>部门总监 = 分管领导（第二级）</b>：部门经理同意后收到审批卡片复核（未配置总监则自动跳过第二级）</li>
              <li>直属领导/主管领导仅用于岗位调动审批，不用于合同审批</li>
              <li>审批卡片在飞书内直接点击处理，不跳转浏览器</li>
            </ul>
          </div>
        </div>
        <Table
          rowKey="department_id"
          columns={columns}
          dataSource={configs}
          loading={loading}
          pagination={false}
          scroll={{ x: 1100 }}
          size="small"
        />
      </Card>
    </div>
  )
}
