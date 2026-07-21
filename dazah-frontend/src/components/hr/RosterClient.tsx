'use client'

import { useState, useCallback, useEffect } from 'react'
import { Table, Input, Select, Tag, Tooltip, App } from 'antd'
import { SearchOutlined, CheckCircleFilled } from '@ant-design/icons'
import { Employee } from '@/types/hr'
import { fetchEmployeesAction } from '@/actions/hr'
import FeishuSyncPanel from './FeishuSyncPanel'

interface RosterClientProps {
  initialEmployees: Employee[]
  initialTotal: number
}

const statusColorMap: Record<string, string> = {
  在职: 'success',
  试用期: 'warning',
  离职: 'default',
  待审批: 'processing',
}

export default function RosterClient({
 initialEmployees, initialTotal }: RosterClientProps) {
  const { message } = App.useApp()

  const [employees, setEmployees] = useState<Employee[]>(initialEmployees)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [loading, setLoading] = useState(false)
  const [keyword, setKeyword] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [filterDepartment, setFilterDepartment] = useState('')

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetchEmployeesAction({
        keyword: keyword || undefined,
        status: filterStatus || undefined,
        department: filterDepartment || undefined,
        page,
        page_size: pageSize,
      })
      setEmployees(res.data)
      setTotal(res.meta?.total || 0)
    } catch (err: any) {
      message.error(err.message || '加载数据失败')
    } finally {
      setLoading(false)
    }
  }, [keyword, filterStatus, filterDepartment, page, pageSize])

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      try {
        const res = await fetchEmployeesAction({
          keyword: keyword || undefined,
          status: filterStatus || undefined,
          department: filterDepartment || undefined,
          page,
          page_size: pageSize,
        })
        if (!cancelled) {
          setEmployees(res.data)
          setTotal(res.meta?.total || 0)
        }
      } catch (err: any) {
        if (!cancelled) message.error(err.message || '加载数据失败')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [keyword, filterStatus, filterDepartment, page, pageSize])

  const handlePageChange = (newPage: number, newPageSize: number) => {
    setPage(newPage)
    setPageSize(newPageSize)
  }

  const departments = Array.from(new Set(employees.map((e) => e.department).filter(Boolean)))

  const columns = [
    {
      title: '工号',
      dataIndex: 'employee_number',
      key: 'employee_number',
      width: 110,
      fixed: 'left' as const,
    },
    {
      title: '姓名',
      dataIndex: 'name',
      key: 'name',
      width: 90,
      fixed: 'left' as const,
    },
    {
      title: '部门',
      dataIndex: 'department',
      key: 'department',
      width: 120,
      filters: departments.map((d) => ({ text: d, value: d })),
      onFilter: (value: any, record: Employee) => record.department === value,
    },
    {
      title: '班组',
      dataIndex: 'team',
      key: 'team',
      width: 100,
    },
    {
      title: '职位',
      dataIndex: 'position',
      key: 'position',
      width: 120,
    },
    {
      title: '职类',
      dataIndex: 'job_category',
      key: 'job_category',
      width: 80,
    },
    {
      title: '级别',
      dataIndex: 'level',
      key: 'level',
      width: 80,
    },
    {
      title: '性别',
      dataIndex: 'gender',
      key: 'gender',
      width: 70,
    },
    {
      title: '年龄',
      dataIndex: 'age',
      key: 'age',
      width: 70,
    },
    {
      title: '籍贯',
      dataIndex: 'native_place',
      key: 'native_place',
      width: 100,
    },
    {
      title: '政治面貌',
      dataIndex: 'political_status',
      key: 'political_status',
      width: 100,
    },
    {
      title: '婚姻状况',
      dataIndex: 'marital_status',
      key: 'marital_status',
      width: 100,
    },
    {
      title: '户籍类型',
      dataIndex: 'household_type',
      key: 'household_type',
      width: 100,
    },
    {
      title: '学历',
      dataIndex: 'education',
      key: 'education',
      width: 80,
    },
    {
      title: '专业',
      dataIndex: 'major',
      key: 'major',
      width: 120,
    },
    {
      title: '毕业学校',
      dataIndex: 'school',
      key: 'school',
      width: 150,
    },
    {
      title: '职称类型',
      dataIndex: 'qualification_type',
      key: 'qualification_type',
      width: 100,
    },
    {
      title: '手机',
      dataIndex: 'phone',
      key: 'phone',
      width: 130,
    },
    {
      title: '邮箱',
      dataIndex: 'email',
      key: 'email',
      width: 180,
    },
    {
      title: '身份证号',
      dataIndex: 'id_card',
      key: 'id_card',
      width: 170,
    },
    {
      title: '入职日期',
      dataIndex: 'hire_date',
      key: 'hire_date',
      width: 110,
    },
    {
      title: '进厂时间',
      dataIndex: 'factory_entry_date',
      key: 'factory_entry_date',
      width: 110,
    },
    {
      title: '入丽珠时间',
      dataIndex: 'livo_entry_date',
      key: 'livo_entry_date',
      width: 110,
    },
    {
      title: '参加工作时间',
      dataIndex: 'work_start_date',
      key: 'work_start_date',
      width: 110,
    },
    {
      title: '厂龄',
      dataIndex: 'factory_tenure',
      key: 'factory_tenure',
      width: 90,
    },
    {
      title: '司龄',
      dataIndex: 'company_tenure',
      key: 'company_tenure',
      width: 90,
    },
    {
      title: '合同期限',
      dataIndex: 'contract_type',
      key: 'contract_type',
      width: 110,
    },
    {
      title: '银行卡号',
      dataIndex: 'bank_account',
      key: 'bank_account',
      width: 170,
    },
    {
      title: '培训档案编号',
      dataIndex: 'training_id',
      key: 'training_id',
      width: 120,
    },
    {
      title: '域账号',
      dataIndex: 'domain_account',
      key: 'domain_account',
      width: 120,
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 90,
      fixed: 'right' as const,
      render: (status: string) => (
        <Tag color={statusColorMap[status] || 'default'}>{status}</Tag>
      ),
    },
    {
      title: '飞书同步',
      key: 'feishu_sync',
      width: 100,
      fixed: 'right' as const,
      render: (_: any, record: Employee) =>
        record.feishu_record_id ? (
          <Tooltip title={`record_id: ${record.feishu_record_id}`}>
            <Tag color="success" icon={<CheckCircleFilled />}>已同步</Tag>
          </Tooltip>
        ) : (
          <Tag color="warning">未同步</Tag>
        ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)]">
          员工花名册
        </h1>
      </div>

      <FeishuSyncPanel onSynced={loadData} />

      <div className="flex flex-wrap gap-3 items-center">
        <Input
          placeholder="搜索姓名或工号"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          prefix={<SearchOutlined />}
          className="w-64"
          allowClear
        />
        <Select
          placeholder="部门筛选"
          value={filterDepartment || undefined}
          onChange={(value) => setFilterDepartment(value || '')}
          allowClear
          className="w-32"
          options={departments.map((d) => ({ value: d, label: d }))}
        />
        <Select
          placeholder="状态筛选"
          value={filterStatus || undefined}
          onChange={(value) => setFilterStatus(value || '')}
          allowClear
          className="w-32"
          options={[
            { value: '在职', label: '在职' },
            { value: '试用期', label: '试用期' },
            { value: '离职', label: '离职' },
            { value: '待审批', label: '待审批' },
          ]}
        />
      </div>

      <Table
        columns={columns}
        dataSource={employees}
        rowKey="id"
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showTotal: (t) => `共 ${t} 条`,
          onChange: handlePageChange,
        }}
        scroll={{ x: 2800 }}
        size="small"
        bordered
      />
    </div>
  )
}
