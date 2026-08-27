'use client'

import { useCallback, useEffect, useState } from 'react'
import { App, Button, Card, DatePicker, Select, Space, Table, Tag } from 'antd'
import { DownloadOutlined, PrinterOutlined } from '@ant-design/icons'
import dayjs, { type Dayjs } from 'dayjs'
import { fetchContractApprovalResults, exportContractApprovalResults, fetchDepartments } from '@/lib/api/client/hr'
import type { ContractApprovalResultVM } from '@/types/hr'

const { RangePicker } = DatePicker

interface Props {
  initialData: ContractApprovalResultVM[]
  initialTotal: number
  initialStartDate: string
  initialEndDate: string
}

export default function ContractApprovalResultsClient({
  initialData,
  initialTotal,
  initialStartDate,
  initialEndDate,
}: Props) {
  const { message } = App.useApp()
  const [data, setData] = useState<ContractApprovalResultVM[]>(initialData)
  const [total, setTotal] = useState(initialTotal)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [dateRange, setDateRange] = useState<[Dayjs, Dayjs]>([dayjs(initialStartDate), dayjs(initialEndDate)])
  const [department, setDepartment] = useState<string | undefined>()
  const [result, setResult] = useState<'approved' | 'rejected' | undefined>()
  const [deptOptions, setDeptOptions] = useState<{ value: string; label: string }[]>([])

  useEffect(() => {
    fetchDepartments({ page_size: 200 })
      .then((json) => {
        const names = (json.data || [])
          .map((d: any) => d.name)
          .filter((n: unknown): n is string => typeof n === 'string' && n.length > 0)
        setDeptOptions([...new Set(names)].map((n) => ({ value: n, label: n })))
      })
      .catch(() => {})
  }, [])

  const loadData = useCallback(async () => {
    setLoading(true)
    try {
      const json = await fetchContractApprovalResults({
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
        department,
        result,
        page,
        page_size: pageSize,
      })
      setData(json.data || [])
      setTotal(json.meta?.total || 0)
    } catch {
      message.error('加载合同审批结果失败')
    } finally {
      setLoading(false)
    }
  }, [dateRange, department, result, page, pageSize, message])

  useEffect(() => {
    queueMicrotask(loadData)
  }, [loadData])

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await exportContractApprovalResults({
        start_date: dateRange[0].format('YYYY-MM-DD'),
        end_date: dateRange[1].format('YYYY-MM-DD'),
        department,
        result,
      })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `合同审批结果_${dateRange[0].format('YYYY-MM-DD')}_${dateRange[1].format('YYYY-MM-DD')}.xlsx`
      a.click()
      window.URL.revokeObjectURL(url)
    } catch {
      message.error('导出失败')
    } finally {
      setExporting(false)
    }
  }

  const handlePrint = () => {
    window.print()
  }

  // 部门经理审批结果：dept_approved_at 非空 → 同意；空且整体拒绝 → 不同意
  const renderDeptResult = (r: ContractApprovalResultVM) => {
    if (r.dept_approved_at) {
      return <Tag color="green">{r.dept_leader_name || '部门经理'} 同意 {dayjs(r.dept_approved_at).format('MM-DD')}</Tag>
    }
    if (r.approval_status === 'rejected') {
      return <Tag color="red">{r.dept_leader_name || '部门经理'} 不同意</Tag>
    }
    return '-'
  }

  // 分管领导审批结果：supervisor_approved_at 非空 → 同意；整体拒绝且部门经理已同意 → 不同意；待审批 → 待审批
  const renderSupervisorResult = (r: ContractApprovalResultVM) => {
    if (r.supervisor_approved_at) {
      return <Tag color="green">{r.supervisor_name || '分管领导'} 同意 {dayjs(r.supervisor_approved_at).format('MM-DD')}</Tag>
    }
    if (r.approval_status === 'rejected' && r.dept_approved_at) {
      return <Tag color="red">{r.supervisor_name || '分管领导'} 不同意</Tag>
    }
    if (r.approval_status === 'supervisor_pending') {
      return <Tag color="orange">待审批</Tag>
    }
    return '-'
  }

  const columns = [
    { title: '工号', dataIndex: 'employee_number', width: 90 },
    { title: '姓名', dataIndex: 'name', width: 90 },
    { title: '一级部门', dataIndex: 'dept_level1', width: 130, ellipsis: true },
    { title: '二级部门', dataIndex: 'dept_level2', width: 130, ellipsis: true },
    { title: '合同到期日期', dataIndex: 'contract_end_date', width: 110 },
    {
      title: '部门经理审批',
      key: 'dept_result',
      width: 170,
      render: (_: unknown, r: ContractApprovalResultVM) => renderDeptResult(r),
    },
    {
      title: '分管领导审批',
      key: 'supervisor_result',
      width: 170,
      render: (_: unknown, r: ContractApprovalResultVM) => renderSupervisorResult(r),
    },
    {
      title: '审批结果',
      dataIndex: 'approval_status',
      width: 100,
      render: (v: string) =>
        v === 'approved' ? <Tag color="green">同意续签</Tag> : <Tag color="red">不同意续签</Tag>,
    },
  ]

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-1">合同到期审批结果</h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          查看合同到期两级审批的通过/不通过清单（部门经理、分管领导分别记录），支持导出打印留存归档
        </p>
      </div>

      <Card>
        <Space wrap className="w-full justify-between">
          <Space wrap>
            <RangePicker
              value={dateRange}
              onChange={(v) => {
                if (v && v[0] && v[1]) {
                  setDateRange([v[0], v[1]])
                  setPage(1)
                }
              }}
              allowClear={false}
            />
            <Select
              placeholder="一级部门"
              allowClear
              style={{ width: 160 }}
              value={department}
              onChange={(v) => {
                setDepartment(v)
                setPage(1)
              }}
              options={deptOptions}
            />
            <Select
              placeholder="审批结果"
              allowClear
              style={{ width: 140 }}
              value={result}
              onChange={(v) => {
                setResult(v)
                setPage(1)
              }}
              options={[
                { value: 'approved', label: '同意续签' },
                { value: 'rejected', label: '不同意续签' },
              ]}
            />
          </Space>
          <Button type="primary" icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
            导出打印
          </Button>
          <Button icon={<PrinterOutlined />} onClick={handlePrint} className="no-print">
            打印
          </Button>
        </Space>
      </Card>

      <Card>
        <Table<ContractApprovalResultVM>
          rowKey="id"
          columns={columns}
          dataSource={data}
          loading={loading}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showTotal: (t) => `共 ${t} 条`,
            onChange: (p, ps) => {
              setPage(p)
              setPageSize(ps)
            },
          }}
        />
      </Card>
    </div>
  )
}
