'use client'

import { useEffect, useState } from 'react'
import { App, Button, Card, Modal, Space, Tag, Row, Col, Table, Upload } from 'antd'
import { ExclamationCircleOutlined, SendOutlined, CheckCircleOutlined, CloseCircleOutlined, DownloadOutlined, UploadOutlined } from '@ant-design/icons'
import * as XLSX from 'xlsx'
import {
  pushContractExpiringAction,
  getContractPushStatusAction,
  saveContractTemplateAction,
} from '@/actions/hr'
import { useSyncPolling } from './useSyncPolling'

interface ContractExpiringItem {
  employee_id: string
  name: string
  department: string
  sub_department: string
  contract_end_date: string
  employee_number?: string
  position?: string
  contract_sequence?: number
}

interface Props {
  onViewExpiring?: (startDate: string, endDate: string) => void
}

interface ContractPushResult {
  state?: string
  status?: string
  progress?: string
  message?: string
  result?: unknown
  pushed?: number
  failed?: number
  skipped_pushed?: number
  skipped_approved?: number
}

function asContractPushResult(value: unknown): ContractPushResult | null {
  return typeof value === 'object' && value !== null ? value as ContractPushResult : null
}

function getNextQuarter() {
  const now = new Date()
  const quarterStart = Math.floor(now.getMonth() / 3) * 3 + 1
  const startDate = new Date(now.getFullYear(), quarterStart - 1, 1)
  const endDate = new Date(now.getFullYear(), quarterStart + 2, 0)
  const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
  return { start: fmt(startDate), end: fmt(endDate), label: `${startDate.getFullYear()}年Q${Math.ceil(quarterStart / 3)}` }
}

export default function ContractAlertBanner({ onViewExpiring }: Props) {
  const [items, setItems] = useState<ContractExpiringItem[]>([])
  const [notifyMsg, setNotifyMsg] = useState<string | null>(null)
  const [pushed, setPushed] = useState(false)
  const [pushSummary, setPushSummary] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [exportOpen, setExportOpen] = useState(false)
  const [quarter] = useState(getNextQuarter)
  const { message } = App.useApp()

  useEffect(() => {
    (async () => {
      try {
        const res = await fetch(`/api/v1/hr/employees/contract-expiring?start_date=${quarter.start}&end_date=${quarter.end}&page_size=100`, { cache: 'no-store' })
        if (!res.ok) return
        const json = await res.json() as { data?: unknown }
        const rows = Array.isArray(json.data) ? json.data : []
        setItems(rows.map((raw): ContractExpiringItem => {
          const e = asContractPushResult(raw) as ContractPushResult & Partial<ContractExpiringItem>
          return {
            employee_id: e.employee_id || '',
            name: e.name || '',
            department: e.department || '',
            sub_department: e.sub_department || '',
            contract_end_date: e.contract_end_date || '',
            employee_number: e.employee_number,
            position: e.position,
            contract_sequence: e.contract_sequence,
          }
        }))
      } catch { /* ignore */ }
    })()
  }, [quarter.start, quarter.end])

  // 初始化检查推送状态
  useEffect(() => {
    (async () => {
      try {
        const statusRes = await getContractPushStatusAction()
        if (asContractPushResult(statusRes.data)?.state === 'completed') {
          setPushed(true)
        }
      } catch { /* ignore */ }
    })()
  }, [])

  const { isSyncing, startSync } = useSyncPolling({
    syncAction: async () => {
      const json = await pushContractExpiringAction(quarter.start, quarter.end)
      setNotifyMsg(json.message || '发起审批任务已启动')
      message.info('发起审批任务已启动，正在发送审批卡片...')
      return json
    },
    pollAction: getContractPushStatusAction,
    maxPolls: 90,
    interval: 2000,
    onSuccess: (_msg, result) => {
      setPushed(true)
      const pushResult = asContractPushResult(result)
      if (pushResult) {
        const pushed = pushResult.pushed || 0
        const failed = pushResult.failed || 0
        const skippedPushed = pushResult.skipped_pushed || 0
        const skippedApproved = pushResult.skipped_approved || 0
        const parts: string[] = [`发送审批卡片 ${pushed} 个部门`]
        if (failed > 0) parts.push(`失败 ${failed} 个部门`)
        if (skippedPushed > 0) parts.push(`已发送跳过 ${skippedPushed} 人`)
        if (skippedApproved > 0) parts.push(`已审批跳过 ${skippedApproved} 人`)
        const summary = parts.join('，')
        setPushSummary(summary)
        setNotifyMsg(`发起审批完成：${summary}`)
        if (pushed > 0) {
          message.success(`审批卡片已发送：${summary}`)
        } else {
          message.info(`无新增到期人员需要发起审批（${summary}）`)
        }
      } else {
        setNotifyMsg('发起审批完成')
        message.success('审批卡片已发送')
      }
    },
    onError: (msg) => {
      setNotifyMsg(msg)
      message.error(msg)
    },
  })

  const handlePush = async () => {
    setNotifyMsg(null)
    setPushSummary(null)
    startSync()
  }

  // 按部门排序
  const sortedItems = [...items].sort((a, b) => a.department.localeCompare(b.department, 'zh-CN'))

  // 导出预览表格列（部门拆分为一级/二级）
  const exportColumns = [
    { title: '序号', dataIndex: 'seq', key: 'seq', width: 60, align: 'center' as const },
    { title: '姓名', dataIndex: 'name', key: 'name', width: 100 },
    { title: '一级部门', dataIndex: 'department', key: 'department', width: 120 },
    { title: '二级部门', dataIndex: 'sub_department', key: 'sub_department', width: 120 },
    { title: '合同到期日期', dataIndex: 'contract_end_date', key: 'contract_end_date', width: 130 },
    { title: '车间领导审批', dataIndex: 'leader_approval', key: 'leader_approval', width: 130, align: 'center' as const },
  ]

  const exportData = sortedItems.map((item, idx) => ({
    key: item.employee_id,
    seq: idx + 1,
    name: item.name,
    department: item.department,
    sub_department: item.sub_department,
    contract_end_date: item.contract_end_date,
    leader_approval: '',
  }))

  // 计算合并单元格：按部门合并"车间领导审批"列
  const getRowSpan = (index: number) => {
    if (index === 0) {
      const dept = sortedItems[0]?.department
      let count = 0
      for (let i = 0; i < sortedItems.length; i++) {
        if (sortedItems[i].department === dept) count++
        else break
      }
      return count
    }
    const currentDept = sortedItems[index]?.department
    const prevDept = sortedItems[index - 1]?.department
    if (currentDept === prevDept) return 0
    let count = 0
    for (let i = index; i < sortedItems.length; i++) {
      if (sortedItems[i].department === currentDept) count++
      else break
    }
    return count
  }

  const mergedColumns = exportColumns.map((col) => ({
    ...col,
    onCell: (_record: unknown, rowIndex?: number) => {
      if (col.key === 'leader_approval' && rowIndex !== undefined) {
        const span = getRowSpan(rowIndex)
        if (span > 1) return { rowSpan: span }
        if (span === 0) return { rowSpan: 0 }
      }
      return {}
    },
  }))

  // 导出为 Excel 文件（调用后端 API）
  const handleExport = async () => {
    try {
      const res = await fetch(`/api/v1/hr/employees/contract-expiring/export?start_date=${quarter.start}&end_date=${quarter.end}`, { cache: 'no-store' })
      if (!res.ok) throw new Error('导出失败')
      const blob = await res.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${quarter.label}合同到期提醒.xlsx`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
      message.success('导出成功')
      setExportOpen(false)
    } catch {
      message.error('导出失败')
    }
  }

  // 导入模板文件：解析模板格式配置保存到后端
  const handleImportFile = (file: File) => {
    const reader = new FileReader()
    reader.onload = async () => {
      try {
        const data = reader.result
        const wb = XLSX.read(data, { type: 'binary' })
        const ws = wb.Sheets[wb.SheetNames[0]]
        const jsonData = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1, defval: '' })

        let headerRowIdx = -1
        for (let i = 0; i < jsonData.length; i++) {
          const row = jsonData[i] || []
          if (row.some((c) => String(c || '').includes('姓名')) && row.some((c) => String(c || '').includes('部门'))) {
            headerRowIdx = i; break
          }
        }
        if (headerRowIdx === -1) { message.error('模板格式不正确'); return }

        const headers = (jsonData[headerRowIdx] || []).map((h) => String(h || '').trim())
        const templateConfig = {
          sheet_name: wb.SheetNames[0],
          header_row: headerRowIdx + 1,
          title_text: String(jsonData[0]?.[0] || ''),
          headers: headers,
          total_rows: jsonData.length,
        }

        await saveContractTemplateAction(templateConfig)
        message.success('模板导入成功')
      } catch {
        message.error('模板导入失败')
      }
    }
    reader.readAsBinaryString(file)
    return false
  }

  if (items.length === 0) {
    return (
      <Card size="small" style={{ marginBottom: 16, background: '#f6ffed', border: '1px solid #b7eb8f' }}>
        <Space><CheckCircleOutlined style={{ color: '#52c41a' }} /><span style={{ fontWeight: 600 }}>{quarter.label} 暂无合同到期人员</span><Tag color="green">已检查6个字段</Tag></Space>
      </Card>
    )
  }

  return (
    <>
      <Card
        style={{ marginBottom: 16, background: '#fff7e6', border: '1px solid #ffa940' }}
        styles={{ body: { padding: '14px 20px' } }}
        title={<span style={{ fontWeight: 700, fontSize: 15 }}><ExclamationCircleOutlined style={{ color: '#fa8c16', marginRight: 6 }} />合同到期提醒 — {quarter.label}<Tag color="warning" style={{ marginLeft: 8 }}>{items.length}人</Tag></span>}
        extra={
          <Space>
            {items.length > 20 && <Button size="small" onClick={() => setDetailOpen(true)}>查看全部</Button>}
            <Upload accept=".xlsx,.xls" showUploadList={false} beforeUpload={handleImportFile}>
              <Button size="small" icon={<UploadOutlined />}>导入</Button>
            </Upload>
            <Button size="small" icon={<DownloadOutlined />} onClick={() => setExportOpen(true)}>导出</Button>
            <Button size="small" icon={<SendOutlined />} loading={isSyncing} onClick={handlePush} danger
              title={pushed ? '已发起过审批，可继续为新增的到期人员发起审批' : undefined}
            >
              {pushed ? '继续发起审批' : '发起审批'}
            </Button>
          </Space>
        }
      >
        <Row gutter={[12, 6]}>
          {items.slice(0, 20).map((item) => (
            <Col key={item.employee_id} xs={24} sm={12}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 10px', background: 'rgba(255,255,255,0.5)', borderRadius: 4, border: '1px solid #ffe7ba' }}>
                <span>
                  <strong>{item.name}</strong>
                  <span style={{ color: '#8c8c8c', marginLeft: 8, fontSize: 12 }}>{item.department}</span>
                </span>
                <Tag color="volcano" style={{ margin: 0 }}>{item.contract_end_date}</Tag>
              </div>
            </Col>
          ))}
        </Row>
        {notifyMsg && (
          <div style={{ marginTop: 10, padding: '6px 12px', background: '#fffbe6', borderRadius: 4, border: '1px solid #ffe58f', fontSize: 13 }}>
            {notifyMsg.includes('失败') ? <CloseCircleOutlined style={{ color: '#ff4d4f', marginRight: 4 }} /> : <CheckCircleOutlined style={{ color: '#52c41a', marginRight: 4 }} />}
            {notifyMsg}
          </div>
        )}
      </Card>

      {/* 全部到期人员 Modal */}
      <Modal title="全部到期人员" open={detailOpen} onCancel={() => setDetailOpen(false)} footer={null} width={700}>
        <Row gutter={[12, 6]}>
          {items.map((item) => (
            <Col key={item.employee_id} span={12}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '5px 10px', background: '#fffbe6', borderRadius: 4, border: '1px solid #ffe7ba' }}>
                <span><strong>{item.name}</strong><span style={{ color: '#8c8c8c', marginLeft: 8, fontSize: 12 }}>{item.department}</span></span>
                <Tag color="volcano" style={{ margin: 0 }}>{item.contract_end_date}</Tag>
              </div>
            </Col>
          ))}
        </Row>
      </Modal>

      {/* 导出预览 Modal */}
      <Modal
        title="导出预览"
        open={exportOpen}
        onCancel={() => setExportOpen(false)}
        width={900}
        footer={[
          <Button key="cancel" onClick={() => setExportOpen(false)}>取消</Button>,
          <Button key="export" type="primary" icon={<DownloadOutlined />} onClick={handleExport}>确认导出</Button>,
        ]}
      >
        <div style={{ marginBottom: 12, color: '#666', fontSize: 13 }}>
          共 {sortedItems.length} 人，按部门排序。“车间领导审批”列已按部门合并。请确认内容无误后点击“确认导出”。
        </div>
        <Table
          columns={mergedColumns}
          dataSource={exportData}
          pagination={false}
          size="small"
          bordered
          scroll={{ y: 400 }}
          style={{ fontSize: 13 }}
        />
      </Modal>
    </>
  )
}
