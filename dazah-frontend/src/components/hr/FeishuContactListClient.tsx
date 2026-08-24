'use client'

import { useEffect, useState, useCallback } from 'react'
import { App, Card, Table, Input, Avatar, Tag, Space, Typography, Select, Button, Tooltip } from 'antd'
import { SearchOutlined, UserOutlined, SyncOutlined } from '@ant-design/icons'
import { fetchFeishuMembers, fetchFeishuMemberDepartments, type FeishuContactVM } from '@/lib/api/client/hr'
import { syncFeishuMembersAction, getFeishuMembersSyncStatus } from '@/actions/hr'
import { useSyncPolling } from './useSyncPolling'

const statusMap: Record<string, { label: string; color: string }> = {
  '1': { label: '在职', color: 'green' },
  '2': { label: '离职', color: 'red' },
  '3': { label: '未激活', color: 'default' },
  '4': { label: '暂停使用', color: 'orange' },
}

const statusOptions = [
  { value: '1', label: '在职' },
  { value: '2', label: '离职' },
  { value: '3', label: '未激活' },
  { value: '4', label: '暂停使用' },
]

const genderMap: Record<string, string> = {
  '1': '男',
  '2': '女',
}

export default function FeishuContactListClient() {
  const { message } = App.useApp()
  const [data, setData] = useState<FeishuContactVM[]>([])
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [keyword, setKeyword] = useState('')
  const [department, setDepartment] = useState<string | undefined>(undefined)
  const [status, setStatus] = useState<string | undefined>(undefined)
  const [deptOptions, setDeptOptions] = useState<{ value: string; label: string }[]>([])

  // 飞书同步（使用共享轮询 hook）
  const { isSyncing, startSync: handleSync } = useSyncPolling({
    syncAction: syncFeishuMembersAction,
    pollAction: getFeishuMembersSyncStatus,
    maxPolls: 90,
    interval: 2000,
    onSuccess: () => {
      message.success('同步完成')
      loadData(page, pageSize, keyword, department, status)
      loadDeptOptions()
    },
    onError: (msg) => {
      message.error(msg)
    },
  })

  // 加载部门筛选选项：取联系人表中实际存在的部门，保证筛选值与数据一致
  const loadDeptOptions = useCallback(async () => {
    try {
      const res = await fetchFeishuMemberDepartments()
      setDeptOptions((res.data || []).map((name) => ({ value: name, label: name })))
    } catch {
      message.error('获取部门筛选选项失败')
    }
  }, [message])

  useEffect(() => {
    queueMicrotask(loadDeptOptions)
  }, [loadDeptOptions])

  const loadData = useCallback(
    async (p: number, ps: number, kw: string, dept: string | undefined, st: string | undefined) => {
      setLoading(true)
      try {
        const res = await fetchFeishuMembers({ page: p, page_size: ps, keyword: kw || undefined, department: dept, status: st })
        setData(res.data || [])
        setTotal(res.meta?.total || 0)
      } catch {
        message.error('加载失败')
      } finally {
        setLoading(false)
      }
    },
    [message],
  )

  useEffect(() => {
    loadData(page, pageSize, keyword, department, status)
  }, [page, pageSize, keyword, department, status, loadData])

  const handleSearch = (value: string) => {
    setKeyword(value)
    setPage(1)
    loadData(1, pageSize, value, department, status)
  }

  const handleDeptChange = (value: string | undefined) => {
    setDepartment(value)
    setPage(1)
    loadData(1, pageSize, keyword, value, status)
  }

  const handleStatusChange = (value: string | undefined) => {
    setStatus(value)
    setPage(1)
    loadData(1, pageSize, keyword, department, value)
  }

  const columns = [
    {
      title: '头像',
      dataIndex: 'avatar_url',
      width: 60,
      render: (url: string | null, record: FeishuContactVM) => (
        <Avatar size={32} src={url || undefined} icon={!url ? <UserOutlined /> : undefined}>
          {record.name?.charAt(0)}
        </Avatar>
      ),
    },
    {
      title: '姓名',
      dataIndex: 'name',
      width: 100,
      render: (name: string) => <Typography.Text strong>{name}</Typography.Text>,
    },
    {
      title: '部门',
      dataIndex: 'department',
      width: 120,
      render: (dept: string | null) => dept || '-',
    },
    {
      title: '职位',
      dataIndex: 'job_title',
      width: 100,
      render: (title: string | null) => title || '-',
    },
    {
      title: '工号',
      dataIndex: 'employee_no',
      width: 80,
      render: (no: string | null) => no || '-',
    },
    {
      title: '手机',
      dataIndex: 'mobile',
      width: 130,
      render: (mobile: string | null) => mobile || '-',
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      width: 200,
      render: (email: string | null) => <Typography.Text style={{ fontSize: 12 }}>{email || '-'}</Typography.Text>,
    },
    {
      title: '性别',
      dataIndex: 'gender',
      width: 60,
      render: (gender: string | null) => (gender ? genderMap[gender] || '-' : '-'),
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 80,
      render: (st: string | null) => {
        const s = st ? statusMap[st] : null
        return s ? <Tag color={s.color}>{s.label}</Tag> : '-'
      },
    },
    {
      title: '冻结/离职日期',
      dataIndex: 'status_changed_at',
      width: 110,
      render: (v: string | null, record: FeishuContactVM) => {
        if ((record.status === '4' || record.status === '2') && v) {
          return v.slice(0, 10)
        }
        return '-'
      },
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center flex-wrap gap-4">
        <h1 className="text-[22px] font-semibold">飞书联系人</h1>
        <Space wrap>
          <Tooltip title="从飞书重新拉取联系人数据">
            <Button
              icon={<SyncOutlined spin={isSyncing} />}
              loading={isSyncing}
              onClick={handleSync}
            >
              从飞书同步
            </Button>
          </Tooltip>
          <Select
            placeholder="筛选部门"
            allowClear
            showSearch
            style={{ width: 180 }}
            options={deptOptions}
            value={department}
            onChange={handleDeptChange}
          />
          <Select
            placeholder="筛选状态"
            allowClear
            style={{ width: 120 }}
            options={statusOptions}
            value={status}
            onChange={handleStatusChange}
          />
          <Input.Search
            placeholder="搜索姓名/部门/工号"
            allowClear
            style={{ width: 250 }}
            onSearch={handleSearch}
            prefix={<SearchOutlined />}
          />
        </Space>
      </div>
      <Card>
        <Table
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          locale={{
            emptyText: (
              <div className="py-8">
                <Typography.Text type="secondary" className="text-base">
                  暂无飞书联系人数据，请点击右上角【从飞书同步】按钮拉取数据
                </Typography.Text>
              </div>
            ),
          }}
          pagination={{
            current: page,
            pageSize: pageSize,
            total: total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 人`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
          scroll={{ x: 1000 }}
          size="middle"
        />
      </Card>
    </div>
  )
}
