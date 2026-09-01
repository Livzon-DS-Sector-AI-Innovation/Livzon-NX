'use client'

import Link from 'next/link'
import { useMemo, useState, useTransition } from 'react'
import {
  App,
  Breadcrumb,
  Button,
  Card,
  Descriptions,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Drawer,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'

import {
  createProjectLedgerEntry,
  createProjectLedgerSubRecord,
  deleteProjectLedgerEntry,
  updateProjectLedgerEntry,
} from '@/actions/registration'
import { fetchProjectLedgerRecordHistory } from '@/lib/api/client/registration'
import type {
  ProjectLedgerColumn,
  ProjectLedgerEntryInput,
  ProjectLedgerHistoryRecord,
  ProjectLedgerRecord,
  ProjectLedgerRecordHistory,
  ProjectLedgerSheetDetail,
} from '@/types/registration'

interface ProjectLedgerSheetPageProps {
  detail: ProjectLedgerSheetDetail
}

interface ProjectLedgerHistoryDisplayRecord extends ProjectLedgerHistoryRecord {
  displayValues: Record<string, string | null>
}

type ProjectLedgerFormValues = Record<string, string | undefined>
type ProjectLedgerFormMode = 'create-main' | 'edit-main' | 'create-sub-record'

export function renderCellValue(
  value?: string | null,
  options?: {
    compact?: boolean
    emptyPlaceholder?: string
    clampLines?: number
  }
) {
  if (!value) {
    return options?.emptyPlaceholder ?? '—'
  }

  return (
    <div
      style={{
        whiteSpace: 'pre-line',
        wordBreak: 'break-word',
        lineHeight: options?.compact ? 1.45 : 1.55,
        display: options?.clampLines ? '-webkit-box' : undefined,
        WebkitBoxOrient: options?.clampLines ? 'vertical' : undefined,
        WebkitLineClamp: options?.clampLines,
        overflow: options?.clampLines ? 'hidden' : undefined,
      }}
      title={value}
    >
      {value}
    </div>
  )
}

export function getColumnWidth(label: string): number {
  if (label === '序号') return 64
  if (label === '产品') return 108
  if (label === '项目名称') return 132
  if (label === '质量标准') return 88
  if (label === '批量/包装规格') return 104
  if (label === '程序类型1') return 84
  if (label.includes('RMS/CMS')) return 76
  if (label.includes('是否获得证书') || label.includes('是否为第一供应商')) return 96
  if (label.includes('药政活动类型')) return 112
  if (label.includes('交费/时间')) return 96
  if (label.includes('文件递交日期')) return 102
  if (label.includes('递交时间')) return 102
  if (label.includes('签署日期')) return 120
  if (label.includes('官方登记号/受理号')) return 132
  if (label.includes('登记号') || label.includes('证书编号') || label.includes('批准文号')) return 122
  if (label.includes('证书效期')) return 112
  if (label.includes('证书名称')) return 118
  if (label.includes('内部编号')) return 106
  if (label.includes('国家/受理机构') || label.includes('受理机构')) return 112
  if (label.includes('代理机构') || label.includes('制剂公司')) return 116
  if (label.includes('药物类型')) return 126
  if (label.includes('制剂剂型/规格/官方登记号')) return 148
  if (label.includes('MF官方登记号')) return 136
  if (label.includes('与制剂关联审评历史') || label.includes('审评结果') || label.includes('批准情况'))
    return 154
  if (label.includes('备注')) return 124
  return 108
}

export function getMainCellClampLines(label: string): number {
  if (label === '项目名称' || label === '产品') return 2
  if (
    label.includes('审评结果') ||
    label.includes('批准情况') ||
    label.includes('与制剂关联审评历史') ||
    label.includes('药政活动说明') ||
    label.includes('备注')
  ) {
    return 2
  }
  if (label.includes('批量/包装规格') || label.includes('药物类型')) {
    return 2
  }
  return 1
}

export function buildHistoryColumns(
  columns: ProjectLedgerColumn[],
  historyCount: number
): ColumnsType<ProjectLedgerHistoryDisplayRecord> {
  return [
    {
      title: '版本',
      key: 'version',
      width: 78,
      align: 'center',
      fixed: 'left',
      render: (_value, record) =>
        record.version === historyCount ? (
          <Tag color="processing" style={{ marginInlineEnd: 0 }}>
            最新
          </Tag>
        ) : (
          <Tag style={{ marginInlineEnd: 0 }}>历史 {record.version}</Tag>
        ),
    },
    ...columns.map((column) => ({
      title: column.label,
      key: column.key,
      width: getColumnWidth(column.label),
      align: 'center' as const,
      render: (_value: unknown, record: ProjectLedgerHistoryDisplayRecord) =>
        renderCellValue(record.displayValues[column.key], {
          compact: true,
          emptyPlaceholder: '',
        }),
    })),
  ]
}

export function buildHistoryDisplayRecords(
  historyRecords: ProjectLedgerHistoryRecord[],
  columns: ProjectLedgerColumn[]
): ProjectLedgerHistoryDisplayRecord[] {
  return historyRecords.map((record) => {
    const displayValues = Object.fromEntries(
      columns.map((column) => [column.key, record.values[column.key] ?? null])
    )

    return {
      ...record,
      displayValues,
    }
  })
}

export function isMultilineField(label: string): boolean {
  return (
    label.includes('类型') ||
    label.includes('说明') ||
    label.includes('历史') ||
    label.includes('结果') ||
    label.includes('情况') ||
    label.includes('规格') ||
    label.includes('备注')
  )
}

const HIDDEN_COLUMNS_BY_SHEET: Record<string, string[]> = {
  'international-associated-review': [
    '药物类型（无菌/非无菌，原料药/中间体，人用药/兽用药）',
    '质量标准',
    '批量/包装规格',
    '国家/受理机构',
    '程序类型1',
    'RMS/CMS个数2',
    '交费/时间',
    'MF内部编号',
    '制剂剂型/规格/官方登记号',
    '是否为第一供应商，是否涉及省份',
    '制剂文件递交时间',
    '（该项目）审评结果/API和制剂分别被批准的时间/正式批准信函或证书情况',
  ],
  'international-standalone-review': [
    'MF内部编号',
    'MF官方登记号',
    '证书名称',
    '证书编号',
    '证书效期',
  ],
  'domestic-associated-review': [
    '批量/包装规格',
    '官方登记号/批准文号',
    '药政活动类型（首次递交/缺陷信回复/变更/年度报告/再注册/委托生产/撤销）',
    '我司文件递交时间',
    '制剂公司',
    '制剂剂型/规格/官方登记号',
    '制剂递交时间',
  ],
  'domestic-standalone-review': [
    '批量/包装规格',
    '证书效期',
  ],
}

export function isColumnHidden(sheetKey: string, columnLabel: string): boolean {
  const hiddenLabels = HIDDEN_COLUMNS_BY_SHEET[sheetKey]
  if (!hiddenLabels) return false
  return hiddenLabels.some((label) => columnLabel === label || columnLabel.includes(label) || label.includes(columnLabel))
}

export function toEntryInput(
  sheetKey: string,
  columns: ProjectLedgerColumn[],
  values: ProjectLedgerFormValues
): ProjectLedgerEntryInput {
  return {
    sheet_key: sheetKey,
    values: Object.fromEntries(
      columns.map((column) => [column.key, values[column.key]?.trim() || null])
    ),
  }
}

export default function ProjectLedgerSheetPage({ detail }: ProjectLedgerSheetPageProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const [form] = Form.useForm<ProjectLedgerFormValues>()
  const [keyword, setKeyword] = useState('')
  const [projectFilter, setProjectFilter] = useState<string>()
  const [productFilter, setProductFilter] = useState<string>()
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null)
  const [editingRecord, setEditingRecord] = useState<ProjectLedgerRecord | null>(null)
  const [historyRecord, setHistoryRecord] = useState<ProjectLedgerRecord | null>(null)
  const [historyPayload, setHistoryPayload] = useState<ProjectLedgerRecordHistory | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [formModalOpen, setFormModalOpen] = useState(false)
  const [formMode, setFormMode] = useState<ProjectLedgerFormMode>('create-main')
  const [detailRecord, setDetailRecord] = useState<ProjectLedgerRecord | null>(null)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [pending, startTransition] = useTransition()

  const projectColumnKey = useMemo(
    () => detail.columns.find((column) => column.label.includes('项目'))?.key,
    [detail.columns]
  )
  const productColumnKey = useMemo(
    () => detail.columns.find((column) => column.label === '产品')?.key,
    [detail.columns]
  )

  const projectOptions = useMemo(() => {
    if (!projectColumnKey) {
      return []
    }

    return Array.from(
      new Set(
        detail.records
          .map((record) => record.latest_values[projectColumnKey]?.trim())
          .filter((value): value is string => Boolean(value))
      )
    ).map((value) => ({
      label: value,
      value,
    }))
  }, [detail.records, projectColumnKey])

  const productOptions = useMemo(() => {
    if (!productColumnKey) {
      return []
    }

    return Array.from(
      new Set(
        detail.records
          .map((record) => record.latest_values[productColumnKey]?.trim())
          .filter((value): value is string => Boolean(value))
      )
    ).map((value) => ({
      label: value,
      value,
    }))
  }, [detail.records, productColumnKey])

  const filteredRecords = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()

    return detail.records.filter((record) => {
      if (projectFilter && projectColumnKey) {
        const projectValue = record.latest_values[projectColumnKey]?.trim()
        if (projectValue !== projectFilter) {
          return false
        }
      }

      if (productFilter && productColumnKey) {
        const productValue = record.latest_values[productColumnKey]?.trim()
        if (productValue !== productFilter) {
          return false
        }
      }

      if (!normalizedKeyword) {
        return true
      }

      return Object.values(record.latest_values).some((value) =>
        value?.toLowerCase().includes(normalizedKeyword)
      )
    })
  }, [detail.records, keyword, productFilter, projectFilter, productColumnKey, projectColumnKey])

  const selectedRecord = useMemo(
    () => filteredRecords.find((record) => record.record_id === selectedRecordId) || null,
    [filteredRecords, selectedRecordId]
  )

  const visibleColumns = useMemo(
    () => detail.columns.filter((column) => !isColumnHidden(detail.sheet_key, column.label)),
    [detail.columns, detail.sheet_key]
  )

  const tableColumns = useMemo<ColumnsType<ProjectLedgerRecord>>(
    () =>
      visibleColumns.map((column, index) => ({
        title: column.label,
        key: column.key,
        width: getColumnWidth(column.label),
        fixed: index === 0 ? ('left' as const) : undefined,
        align: 'center' as const,
        render: (_value: unknown, record: ProjectLedgerRecord) => {
          const content = renderCellValue(record.latest_values[column.key], {
            compact: true,
            clampLines: getMainCellClampLines(column.label),
          })
          if (index !== 0) {
            return content
          }

          return (
            <Space orientation="vertical" size={2} style={{ width: '100%' }}>
              <div>{content}</div>
              {record.history_count > 1 ? (
                <Tag
                  color="purple"
                  style={{ marginInlineEnd: 0, cursor: 'pointer' }}
                  onClick={(event) => {
                    event.preventDefault()
                    event.stopPropagation()
                    void openHistoryModal(record)
                  }}
                >
                  历史 {record.history_count - 1} 条
                </Tag>
              ) : null}
            </Space>
          )
        },
      })),
    [visibleColumns]
  )

  function openCreateModal() {
    setFormMode('create-main')
    setEditingRecord(null)
    form.resetFields()
    const sequenceColumn = detail.columns[0]
    const nextSequence =
      detail.records.reduce((maxValue, record) => Math.max(maxValue, record.sequence), 0) + 1
    form.setFieldsValue({
      [sequenceColumn.key]: String(nextSequence),
    })
    setFormModalOpen(true)
  }

  function openEditModal() {
    if (!selectedRecord) {
      message.warning('请先选择一条申报台账记录')
      return
    }

    setFormMode('edit-main')
    setEditingRecord(selectedRecord)
    form.setFieldsValue(
      Object.fromEntries(
        detail.columns.map((column) => [column.key, selectedRecord.latest_values[column.key] || undefined])
      )
    )
    setFormModalOpen(true)
  }

  function openCreateSubRecordModal() {
    if (!selectedRecord) {
      message.warning('请先选择一条申报台账主记录')
      return
    }

    setFormMode('create-sub-record')
    setEditingRecord(selectedRecord)
    form.setFieldsValue(
      Object.fromEntries(
        detail.columns.map((column) => [column.key, selectedRecord.latest_values[column.key] || undefined])
      )
    )
    setFormModalOpen(true)
  }

  async function openHistoryModal(targetRecord: ProjectLedgerRecord | null = selectedRecord) {
    if (!targetRecord) {
      message.warning('请先选择一条申报台账记录')
      return
    }
    if (targetRecord.history_count <= 1) {
      message.info('当前记录暂无历史版本')
      return
    }
    setHistoryRecord(targetRecord)
    setHistoryPayload(null)
    setHistoryLoading(true)
    try {
      const payload = await fetchProjectLedgerRecordHistory(targetRecord.record_id)
      setHistoryPayload(payload)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取历史失败')
    } finally {
      setHistoryLoading(false)
    }
  }

  function handleDelete() {
    if (!selectedRecord) {
      message.warning('请先选择一条申报台账记录')
      return
    }

    startTransition(async () => {
      try {
        await deleteProjectLedgerEntry(selectedRecord.record_id, detail.sheet_key)
        message.success('申报台账记录已删除')
        setSelectedRecordId(null)
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除失败')
      }
    })
  }

  async function handleSubmit(values: ProjectLedgerFormValues) {
    const payload = toEntryInput(detail.sheet_key, detail.columns, values)

    startTransition(async () => {
      try {
        if (formMode === 'edit-main' && editingRecord) {
          await updateProjectLedgerEntry(editingRecord.record_id, payload)
          message.success('主记录已更新')
        } else if (formMode === 'create-sub-record' && editingRecord) {
          await createProjectLedgerSubRecord(editingRecord.record_id, payload)
          message.success('子记录已新增')
        } else {
          await createProjectLedgerEntry(payload)
          message.success('主记录已新增')
        }
        setFormModalOpen(false)
        setEditingRecord(null)
        form.resetFields()
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '保存失败')
      }
    })
  }

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <Breadcrumb
        items={[
          { title: <Link href="/registration">注册管理</Link> },
          { title: <Link href="/registration/project-ledger">申报台账</Link> },
          { title: detail.sheet_name },
        ]}
      />

      <Typography.Title level={3} style={{ marginBottom: 0 }}>
        {detail.sheet_name}
      </Typography.Title>

      <Card
        size="small"
        extra={
          <Space>
            <Button icon={<PlusOutlined />} type="primary" onClick={openCreateModal}>
              新增主记录
            </Button>
            <Button icon={<PlusOutlined />} disabled={!selectedRecord} onClick={openCreateSubRecordModal}>
              新增子记录
            </Button>
            <Button icon={<EditOutlined />} disabled={!selectedRecord} onClick={openEditModal}>
              编辑主记录
            </Button>
            <Button
              icon={<EyeOutlined />}
              disabled={!selectedRecord}
              onClick={() => {
                void openHistoryModal()
              }}
            >
              查看历史
            </Button>
            <Button
              icon={<EyeOutlined />}
              disabled={!selectedRecord}
              onClick={() => {
                setDetailRecord(selectedRecord)
                setDetailModalOpen(true)
              }}
            >
              详情
            </Button>
            <Popconfirm
              title="确认删除选中的申报台账记录吗？"
              description="该记录的子记录与历史版本将一并软删除，可在历史版本中找回。"
              okText="删除"
              okButtonProps={{ danger: true }}
              cancelText="取消"
              onConfirm={handleDelete}
              disabled={!selectedRecord}
            >
              <Button danger icon={<DeleteOutlined />} disabled={!selectedRecord}>
                删除选中
              </Button>
            </Popconfirm>
          </Space>
        }
      >
        <Space wrap size={12} style={{ width: '100%', marginBottom: 16 }}>
          <Select
            allowClear
            showSearch
            placeholder="按项目筛选"
            value={projectFilter}
            onChange={(value) => setProjectFilter(value)}
            options={projectOptions}
            style={{ width: 260 }}
            optionFilterProp="label"
          />
          <Select
            allowClear
            showSearch
            placeholder="按产品筛选"
            value={productFilter}
            onChange={(value) => setProductFilter(value)}
            options={productOptions}
            style={{ width: 240 }}
            optionFilterProp="label"
          />
          <Input
            allowClear
            placeholder="按项目名称、产品、受理号、证书号等搜索"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
            style={{ width: 320 }}
          />
        </Space>

        <Table<ProjectLedgerRecord>
          className="project-ledger-table"
          rowKey="record_id"
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          dataSource={filteredRecords}
          locale={{
            emptyText:
              keyword || productFilter || projectFilter
                ? '当前筛选条件下暂无记录'
                : '暂无台账记录',
          }}
          columns={tableColumns}
          scroll={{ x: 'max-content' }}
          rowClassName={(record) =>
            record.record_id === selectedRecordId
              ? 'project-ledger-row-selected'
              : 'project-ledger-row'
          }
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedRecordId ? [selectedRecordId] : [],
            onChange: (selectedKeys) => setSelectedRecordId((selectedKeys[0] as string) || null),
          }}
          onRow={(record) => ({
            onClick: () => setSelectedRecordId(record.record_id),
          })}
        />
      </Card>

      <Drawer
        destroyOnHidden
        open={formModalOpen}
        title={
          formMode === 'edit-main'
            ? '编辑申报台账主记录'
            : formMode === 'create-sub-record'
              ? '新增申报台账子记录'
              : '新增申报台账主记录'
        }
        width={560}
        footer={
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
            <Button
              onClick={() => {
                setFormModalOpen(false)
                setEditingRecord(null)
                form.resetFields()
              }}
            >
              取消
            </Button>
            <Button type="primary" loading={pending} onClick={() => form.submit()}>
              {formMode === 'edit-main' ? '保存' : '新增'}
            </Button>
          </div>
        }
        onClose={() => {
          setFormModalOpen(false)
          setEditingRecord(null)
          form.resetFields()
        }}
      >
        <Form<ProjectLedgerFormValues> form={form} layout="vertical" onFinish={handleSubmit}>
          {detail.columns.map((column) => (
            <Form.Item
              key={column.key}
              name={column.key}
              label={column.label}
              rules={column.label === '序号' ? [{ required: true, message: `请填写${column.label}` }] : undefined}
            >
              {isMultilineField(column.label) ? (
                <Input.TextArea
                  rows={3}
                  disabled={column.label === '序号' && formMode !== 'create-main'}
                />
              ) : (
                <Input disabled={column.label === '序号' && formMode !== 'create-main'} />
              )}
            </Form.Item>
          ))}
        </Form>
      </Drawer>

      <Modal
        open={Boolean(historyRecord)}
        onCancel={() => {
          setHistoryRecord(null)
          setHistoryPayload(null)
        }}
        footer={null}
        width="92vw"
        title={
          historyRecord
            ? `${historyRecord.latest_values[projectColumnKey || ''] || detail.sheet_name} 历史记录`
            : '历史记录'
        }
        styles={{ body: { paddingTop: 12 } }}
      >
        {historyRecord ? (
          <Table<ProjectLedgerHistoryDisplayRecord>
            rowKey={(item) => `${historyRecord.record_id}-${item.entry_id}`}
            size="small"
            pagination={false}
            loading={historyLoading}
            className="project-ledger-history-table"
            columns={buildHistoryColumns(detail.columns, historyPayload?.history_count || historyRecord.history_count)}
            dataSource={buildHistoryDisplayRecords(historyPayload?.history_records || [], detail.columns)}
            scroll={{ x: 'max-content', y: '60vh' }}
          />
        ) : null}
      </Modal>

      <Modal
        destroyOnHidden
        open={detailModalOpen}
        onCancel={() => {
          setDetailModalOpen(false)
          setDetailRecord(null)
        }}
        footer={null}
        width="92vw"
        className="project-ledger-detail-modal"
        title={
          detailRecord
            ? `${detailRecord.latest_values[projectColumnKey || ''] || detail.sheet_name} - 详情`
            : '详情'
        }
      >
        {detailRecord ? (
          <Descriptions column={3} bordered size="small">
            {detail.columns.map((column) => (
              <Descriptions.Item key={column.key} label={column.label} span={column.label.includes('审评结果') || column.label.includes('批准情况') || column.label.includes('备注') ? 2 : 1}>
                {renderCellValue(detailRecord.latest_values[column.key], {
                  emptyPlaceholder: '—',
                })}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : null}
      </Modal>

      <style jsx global>{`
        .project-ledger-table .ant-table-thead > tr > th,
        .project-ledger-history-table .ant-table-thead > tr > th {
          background: #faf8ff;
          border-bottom: 1px solid #e7dcff;
          text-align: center;
          font-size: 13px;
          line-height: 1.45;
          font-weight: 600;
          padding: 8px 4px;
        }

        .project-ledger-table .ant-table-tbody > tr > td,
        .project-ledger-history-table .ant-table-tbody > tr > td {
          text-align: center;
          vertical-align: middle;
          font-size: 13px;
          line-height: 1.6;
          padding: 10px 14px;
          border-bottom: 1px solid #f0f0f0;
        }

        .project-ledger-history-table .ant-table-thead > tr > th {
          font-size: 13px;
          line-height: 1.35;
          padding: 7px 4px;
        }

        .project-ledger-history-table .ant-table-tbody > tr > td {
          line-height: 1.6;
          padding: 12px;
        }

        .project-ledger-table .ant-table-tbody > tr.project-ledger-row:nth-child(even) > td,
        .project-ledger-history-table .ant-table-tbody > tr:nth-child(even) > td {
          background: #fcfcff;
        }

        .project-ledger-table .ant-table-tbody > tr.project-ledger-row:hover > td,
        .project-ledger-history-table .ant-table-tbody > tr:hover > td {
          background: #f6f2ff;
        }

        .project-ledger-table .ant-table-tbody > tr.project-ledger-row-selected > td {
          background: #f1ebff !important;
        }

        .project-ledger-detail-modal .ant-descriptions-item-label {
          background: #faf8ff;
          font-weight: 600;
          font-size: 13px;
          width: 140px;
        }

        .project-ledger-detail-modal .ant-descriptions-item-content {
          font-size: 13px;
        }
      `}</style>
    </Space>
  )
}
