'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import Link from 'next/link'
import dayjs, { type Dayjs } from 'dayjs'
import { App, Avatar, Button, DatePicker, Descriptions, Drawer, Form, Input, Modal, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteDeviationInvestigationPushRecord as deleteDeviationInvestigationPushRecordAction, updateDeviationInvestigationPushRecord as updateDeviationInvestigationPushRecordAction } from '@/actions/quality-deviation'
import { pullQualityRecordsFromFeishu } from '@/actions/quality'
import { fetchDeviationInvestigationPushRecords, fetchDeviationReportRecords, fetchQualityFeishuAppSettings } from '@/lib/api/client/quality'

import type {
  DepartmentContact,
  DeviationInvestigationPushRecordItem,
  DeviationReportRecordItem,
} from '@/types/quality'

function formatDateTime(value: string | null | undefined): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const yyyy = date.getFullYear()
  const mm = `${date.getMonth() + 1}`.padStart(2, '0')
  const dd = `${date.getDate()}`.padStart(2, '0')
  const hh = `${date.getHours()}`.padStart(2, '0')
  const mi = `${date.getMinutes()}`.padStart(2, '0')
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}`
}

function renderReviewResult(value: string | null | undefined): React.ReactNode {
  if (!value) return '-'
  if (value === 'approved') return <Tag color="green" style={{ borderRadius: 999 }}>通过</Tag>
  if (value === 'rejected') return <Tag color="red" style={{ borderRadius: 999 }}>不通过</Tag>
  return value
}

/** 人员列渲染：头像+姓名，无对象时回退字符串姓名 */
function renderPerson(
  persons: Array<{ name?: string; avatar_url?: string; id?: string }> | null | undefined,
  fallbackName?: string | null,
): React.ReactNode {
  const list = persons && persons.length > 0 ? persons : fallbackName ? [{ name: fallbackName }] : []
  if (list.length === 0) return <span>-</span>
  return (
    <Space size={4} wrap>
      {list.map((person, index) => (
        <span key={index} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
          <Avatar size={20} src={person.avatar_url || undefined}>
            {person.name?.slice(0, 1) || '?'}
          </Avatar>
          <span>{person.name || '-'}</span>
        </span>
      ))}
    </Space>
  )
}

const baseColumns: ColumnsType<DeviationInvestigationPushRecordItem> = [
  { title: '偏差编号', dataIndex: 'deviation_code', key: 'deviation_code', width: 160 },
  { title: '第N次推送', dataIndex: 'push_round', key: 'push_round', width: 110 },
  {
    title: '偏差调查报告',
    dataIndex: 'investigation_report_url',
    key: 'investigation_report_url',
    width: 220,
    render: (value: string | null | undefined) => {
      if (!value) return '-'
      if (/^https?:\/\//i.test(value)) {
        return (
          <a href={value} target="_blank" rel="noreferrer">
            偏差调查报告
          </a>
        )
      }
      return (
        <Tooltip title={value}>
          <span>{value}</span>
        </Tooltip>
      )
    },
  },
  {
    title: '提交日期',
    dataIndex: 'submitted_at',
    key: 'submitted_at',
    width: 150,
    render: (value: string | null | undefined) => formatDateTime(value),
  },
  {
    title: '提交人',
    key: 'submitters',
    width: 120,
    render: (_: unknown, record: DeviationInvestigationPushRecordItem) =>
      renderPerson(record.submitters, record.submitter),
  },
  {
    title: '部门负责人',
    key: 'department_heads',
    width: 140,
    render: (_: unknown, record: DeviationInvestigationPushRecordItem) =>
      renderPerson(record.department_heads, record.department_head),
  },
  {
    title: '部门负责人审核结果',
    dataIndex: 'department_head_result',
    key: 'department_head_result',
    width: 170,
    render: (value: string | null | undefined) => renderReviewResult(value),
  },
  {
    title: '部门负责人审核时间',
    dataIndex: 'department_head_reviewed_at',
    key: 'department_head_reviewed_at',
    width: 170,
    render: (value: string | null | undefined) => formatDateTime(value),
  },
]

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

interface InvestigationPushFormValues {
  deviation_code: string
  push_round: string
  investigation_report_url: string
  submitted_at: Dayjs
  submitter_open_id?: string
}

interface DeviationInvestigationPushPageProps {
  submitterContacts?: DepartmentContact[]
}

const pushRoundOptions = ['第1次', '第2次', '第3次'].map((value) => ({
  label: value,
  value,
}))

function buildReportRecordOptions(items: DeviationReportRecordItem[]): DeviationReportRecordItem[] {
  const deduplicated = new Map<string, DeviationReportRecordItem>()

  for (const item of items) {
    const deviationCode = item.deviation_code?.trim()
    const reportStatus = (item.report_status || '').trim()
    if (!deviationCode) continue
    if (reportStatus === 'draft' || reportStatus === '草稿') continue
    if (!deduplicated.has(deviationCode)) {
      deduplicated.set(deviationCode, item)
    }
  }

  return Array.from(deduplicated.values())
}

export function DeviationInvestigationPushPage({
  submitterContacts = [],
}: DeviationInvestigationPushPageProps) {
  const { message } = App.useApp()
  const [saving, setSaving] = useState(false)
  const [pulling, setPulling] = useState(false)
  const [deletingRecordId, setDeletingRecordId] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<DeviationInvestigationPushRecordItem | null>(null)
  const [detailRecord, setDetailRecord] = useState<DeviationInvestigationPushRecordItem | null>(null)
  const [form] = Form.useForm<InvestigationPushFormValues>()
  const selectedDeviationCode = Form.useWatch('deviation_code', form)

  const queryClient = useQueryClient()

  const { data: pushRecordsData, isLoading: loading, error } = useQuery({
    queryKey: ['quality-deviation', 'investigation-push'],
    queryFn: () => fetchDeviationInvestigationPushRecords({ page: 1, page_size: 50 }),
  })

  const { data: reportRecordsData } = useQuery({
    queryKey: ['quality-deviation', 'report-records-options'],
    queryFn: () => fetchDeviationReportRecords({ page: 1, page_size: 1000 }),
  })

  const { data: appSettings } = useQuery({
    queryKey: ['quality-feishu-settings', 'app'],
    queryFn: fetchQualityFeishuAppSettings,
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, '加载调查推送失败'))
    }
  }, [error, message])

  const items: DeviationInvestigationPushRecordItem[] = pushRecordsData?.items ?? []
  const reportRecordOptions = useMemo(
    () => buildReportRecordOptions(reportRecordsData?.items ?? []),
    [reportRecordsData?.items]
  )

  const selectedReportRecord = useMemo(
    () =>
      reportRecordOptions.find(
        (item) => (item.deviation_code || '').trim() === (selectedDeviationCode || '').trim()
      ),
    [reportRecordOptions, selectedDeviationCode]
  )

  const submitterOptions = useMemo(() => {
    const selectedDepartment = selectedReportRecord?.department?.trim()
    return submitterContacts
      .filter((item) => Boolean(item.open_id))
      .filter((item) =>
        selectedDepartment ? item.department?.trim() === selectedDepartment : true
      )
      .map((item) => ({
        label: `${item.name || '-'}${item.department ? ` / ${item.department}` : ''}`,
        value: item.open_id as string,
      }))
  }, [selectedReportRecord?.department, submitterContacts])

  const formDeviationOptions = useMemo(() => {
    const options = reportRecordOptions.map((item) => ({
      value: item.deviation_code || '',
      label: item.deviation_code || '-',
    }))
    if (
      editingRecord?.deviation_code &&
      !options.some((item) => item.value === editingRecord.deviation_code)
    ) {
      options.unshift({
        value: editingRecord.deviation_code,
        label: editingRecord.deviation_code,
      })
    }
    return options
  }, [editingRecord, reportRecordOptions])

  const closeModal = useCallback(() => {
    setOpen(false)
    setEditingRecord(null)
    form.resetFields()
  }, [form])

  const resolveSubmitterOpenId = useCallback(
    (
      record: Pick<DeviationInvestigationPushRecordItem, 'submitter'>,
      reportRecord?: DeviationReportRecordItem
    ) => {
      const submitterName = record.submitter?.trim()
      if (!submitterName) return undefined
      const selectedDepartment = reportRecord?.department?.trim()
      return (
        submitterContacts.find(
          (item) =>
            item.open_id &&
            (item.name || '').trim() === submitterName &&
            (!selectedDepartment || (item.department || '').trim() === selectedDepartment)
        )?.open_id ||
        submitterContacts.find(
          (item) => item.open_id && (item.name || '').trim() === submitterName
        )?.open_id ||
        undefined
      )
    },
    [submitterContacts]
  )

  const openEdit = useCallback(
    (record: DeviationInvestigationPushRecordItem) => {
      const matchedReportRecord = reportRecordOptions.find(
        (item) => (item.deviation_code || '').trim() === (record.deviation_code || '').trim()
      )
      setEditingRecord(record)
      form.resetFields()
      form.setFieldsValue({
        deviation_code: record.deviation_code,
        push_round: record.push_round,
        investigation_report_url: record.investigation_report_url || undefined,
        submitted_at: record.submitted_at ? dayjs(record.submitted_at) : dayjs(),
        submitter_open_id: resolveSubmitterOpenId(record, matchedReportRecord),
      })
      setOpen(true)
    },
    [form, reportRecordOptions, resolveSubmitterOpenId]
  )

  const handleCreateNew = useCallback(() => {
    const url = (appSettings?.deviation_investigation_push_form_url || '').trim()
    if (!url) {
      message.warning('请在飞书设置中配置新建表单链接')
      return
    }
    window.open(url, '_blank', 'noopener,noreferrer')
  }, [appSettings, message])

  const handleSubmit = useCallback(async () => {
    const values = await form.validateFields()
    try {
      setSaving(true)
      const payload = {
        deviation_code: values.deviation_code.trim(),
        push_round: values.push_round,
        investigation_report_url: values.investigation_report_url.trim(),
        submitted_at: values.submitted_at.format('YYYY-MM-DDTHH:mm:ssZ'),
        ...(values.submitter_open_id ? { submitter_open_id: values.submitter_open_id } : {}),
      }
      if (editingRecord) {
        await updateDeviationInvestigationPushRecordAction(editingRecord.record_id, payload)
        message.success('调查推送记录已更新')
      }
      closeModal()
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'investigation-push'] })
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'report-records-options'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存调查推送记录失败'))
    } finally {
      setSaving(false)
    }
  }, [closeModal, editingRecord, form, queryClient, message])

  const handleDelete = useCallback(async (recordId: string) => {
    try {
      setDeletingRecordId(recordId)
      await deleteDeviationInvestigationPushRecordAction(recordId)
      message.success('调查推送记录已删除')
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'investigation-push'] })
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'report-records-options'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '删除调查推送记录失败'))
    } finally {
      setDeletingRecordId(null)
    }
  }, [queryClient, message])

  const handlePullFromFeishu = useCallback(async () => {
    try {
      setPulling(true)
      const result = await pullQualityRecordsFromFeishu('deviation_investigation_push_record')
      message.success(`从飞书拉取完成：成功 ${result?.synced ?? 0} 条，失败 ${result?.failed ?? 0} 条`)
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'investigation-push'] })
      queryClient.invalidateQueries({ queryKey: ['quality-deviation', 'report-records-options'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '从飞书拉取调查推送失败'))
    } finally {
      setPulling(false)
    }
  }, [queryClient, message])

  const columns = useMemo<ColumnsType<DeviationInvestigationPushRecordItem>>(
    () => [
      ...baseColumns,
      {
        title: '操作',
        key: 'action',
        width: 200,
        fixed: 'right',
        render: (_, record) => (
          <Space size="small">
            <Button type="link" onClick={() => setDetailRecord(record)}>详情</Button>
            <Button type="link" onClick={() => openEdit(record)}>修改</Button>
            <Popconfirm
              title="确认删除这条调查推送记录？"
              okText="删除"
              cancelText="取消"
              onConfirm={() => void handleDelete(record.record_id)}
            >
              <Button
                type="link"
                danger
                loading={deletingRecordId === record.record_id}
              >
                删除
              </Button>
            </Popconfirm>
          </Space>
        ),
      },
    ],
    [deletingRecordId, handleDelete, openEdit]
  )

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 偏差管理 / 调查推送</p>
        <Typography.Title level={3} style={{ margin: 0 }}>偏差调查推送</Typography.Title>
      </div>
      <Space style={{ marginBottom: 16 }} wrap>
        <Button type="primary" onClick={handleCreateNew}>新增推送记录</Button>
        <Button loading={pulling} onClick={() => void handlePullFromFeishu()}>从飞书拉取</Button>
        <Link href="/quality/deviations/records"><Button>返回报告记录</Button></Link>
        <Link href="/quality/deviations/ledger"><Button>查看偏差台账</Button></Link>
      </Space>
      <Table<DeviationInvestigationPushRecordItem>
        rowKey="record_id"
        loading={loading}
        columns={columns}
        dataSource={items}
        pagination={false}
        scroll={{ x: 1440 }}
      />
      <Modal
        title="修改推送记录"
        open={open}
        onOk={() => void handleSubmit()}
        onCancel={closeModal}
        confirmLoading={saving}
        destroyOnHidden
      >
        <Form
          form={form}
          layout="vertical"
          onValuesChange={(changedValues) => {
            if ('deviation_code' in changedValues) {
              form.setFieldValue('submitter_open_id', undefined)
            }
          }}
        >
          <Form.Item name="deviation_code" label="偏差编号" rules={[{ required: true, message: '请选择偏差编号' }]}>
            <Select
              showSearch
              optionFilterProp="label"
              options={formDeviationOptions}
              placeholder="请选择偏差编号"
            />
          </Form.Item>
          <Form.Item name="push_round" label="第N次推送" rules={[{ required: true, message: '请选择第N次推送' }]}>
            <Select
              options={pushRoundOptions}
              placeholder="请选择选项"
            />
          </Form.Item>
          <Form.Item
            name="investigation_report_url"
            label="偏差调查报告"
            rules={[
              { required: true, message: '请输入偏差调查报告链接' },
              { type: 'url', message: '请输入有效链接' },
            ]}
          >
            <Input placeholder="请输入内容" />
          </Form.Item>
          <Form.Item
            name="submitted_at"
            label="提交日期"
            rules={[{ required: true, message: '请选择提交日期' }]}
          >
            <DatePicker
              showTime
              format="YYYY-MM-DD HH:mm"
              style={{ width: '100%' }}
              allowClear={false}
            />
          </Form.Item>
          <Form.Item
            name="submitter_open_id"
            label="提交人"
            rules={[]}
          >
            <Select
              showSearch
              optionFilterProp="label"
              options={submitterOptions}
              disabled={!selectedDeviationCode}
              placeholder={
                selectedReportRecord?.department
                  ? `请选择${selectedReportRecord.department}部门联系人中的提交人`
                  : '如需修改提交人，请重新选择'
              }
            />
          </Form.Item>
        </Form>
      </Modal>
      <Drawer
        title="调查推送详情"
        open={!!detailRecord}
        onClose={() => setDetailRecord(null)}
        size="large"
      >
        {detailRecord ? (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="偏差编号">{detailRecord.deviation_code || '-'}</Descriptions.Item>
            <Descriptions.Item label="第N次推送">{detailRecord.push_round || '-'}</Descriptions.Item>
            <Descriptions.Item label="偏差调查报告">
              {detailRecord.investigation_report_url ? (
                <a href={detailRecord.investigation_report_url} target="_blank" rel="noreferrer">
                  偏差调查报告
                </a>
              ) : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="提交日期">{formatDateTime(detailRecord.submitted_at)}</Descriptions.Item>
            <Descriptions.Item label="提交人">
              {renderPerson(detailRecord.submitters, detailRecord.submitter)}
            </Descriptions.Item>
            <Descriptions.Item label="部门负责人">
              {renderPerson(detailRecord.department_heads, detailRecord.department_head)}
            </Descriptions.Item>
            <Descriptions.Item label="部门负责人审核结果">
              {renderReviewResult(detailRecord.department_head_result)}
            </Descriptions.Item>
            <Descriptions.Item label="部门负责人审核时间">
              {formatDateTime(detailRecord.department_head_reviewed_at)}
            </Descriptions.Item>
            <Descriptions.Item label="QA">
              {renderPerson(detailRecord.qas, detailRecord.qa_name)}
            </Descriptions.Item>
            <Descriptions.Item label="QA审核结果">
              {renderReviewResult(detailRecord.qa_result)}
            </Descriptions.Item>
            <Descriptions.Item label="QA审核时间">
              {formatDateTime(detailRecord.qa_reviewed_at)}
            </Descriptions.Item>
            <Descriptions.Item label="QA负责人">
              {renderPerson(detailRecord.qa_heads, detailRecord.qa_head_name)}
            </Descriptions.Item>
            <Descriptions.Item label="QA负责人审核结果">
              {renderReviewResult(detailRecord.qa_head_result)}
            </Descriptions.Item>
            <Descriptions.Item label="QA负责人审核时间">
              {formatDateTime(detailRecord.qa_head_reviewed_at)}
            </Descriptions.Item>
          </Descriptions>
        ) : null}
      </Drawer>
    </div>
  )
}
