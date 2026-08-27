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
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { DeleteOutlined, EditOutlined, EyeOutlined, PlusOutlined } from '@ant-design/icons'
import { useRouter } from 'next/navigation'

import {
  createDeclarationProgressEntry,
  createDeclarationProgressSubRecord,
  deleteDeclarationProgressEntry,
  updateDeclarationProgressEntry,
} from '@/actions/registration'
import { fetchDeclarationProgressRecordHistory } from '@/lib/api/client/registration'
import type {
  DeclarationProgressColumn,
  DeclarationProgressEntryInput,
  DeclarationProgressHistoryRecord,
  DeclarationProgressRecord,
  DeclarationProgressRecordHistory,
  DeclarationProgressSheetDetail,
} from '@/types/registration'

interface DeclarationProgressPageProps {
  detail: DeclarationProgressSheetDetail
}

interface DeclarationProgressHistoryDisplayRecord extends DeclarationProgressHistoryRecord {
  key: string
}

type DeclarationProgressFormValues = Record<string, string | undefined>
type DeclarationProgressFormMode = 'create-main' | 'edit-main' | 'create-sub-record'

function getCellColor(mark?: string | null): string | undefined {
  if (mark === 'updated') return '#FF0000'
  if (mark === 'new') return '#0000FE'
  return undefined
}

function renderCellValue(
  value?: string | null,
  mark?: string | null,
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
        color: getCellColor(mark),
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

function getColumnWidth(label: string): number {
  if (label === '序号') return 72
  if (label.includes('项目名称') || label.includes('产品名称')) return 160
  if (label === '产品' || label === '涉及产品') return 132
  if (label.includes('质量标准')) return 110
  if (label.includes('受理机构') || label.includes('国家')) return 132
  if (label.includes('内部编号') || label.includes('登记号') || label.includes('批准文号')) return 138
  if (label.includes('递交时间') || label.includes('签署日期') || label.includes('审计日期')) return 140
  if (label.includes('是否')) return 128
  if (label.includes('结果') || label.includes('问题') || label.includes('备注')) return 220
  if (label.includes('规格') || label.includes('资料')) return 180
  if (label.includes('药物类型')) return 180
  if (label.includes('类型')) return 200
  return 128
}

function getMainCellClampLines(label: string): number {
  if (
    label.includes('结果') ||
    label.includes('问题') ||
    label.includes('备注') ||
    label.includes('规格') ||
    label.includes('资料') ||
    label.includes('类型')
  ) {
    return 3
  }
  if (label.includes('项目名称') || label.includes('产品')) {
    return 2
  }
  return 1
}

function toEntryInput(
  sheetKey: string,
  columns: DeclarationProgressColumn[],
  values: DeclarationProgressFormValues
): DeclarationProgressEntryInput {
  return {
    sheet_key: sheetKey,
    values: Object.fromEntries(
      columns.map((column) => [column.key, values[column.key]?.trim() || null])
    ),
  }
}

function isLongTextField(label: string): boolean {
  return (
    label.includes('结果') ||
    label.includes('问题') ||
    label.includes('备注') ||
    label.includes('资料') ||
    label.includes('历史') ||
    label.includes('规格') ||
    label.includes('类型')
  )
}

const HIDDEN_COLUMNS_BY_SHEET: Record<string, string[]> = {
  'international-planned-in-progress': [
    'MF内部编号',
    'MF官方登记号',
    '与制剂关联审评历史',
    '交费/时间',
    '代理机构',
    '是否为第一供应商',
    '制剂文件计划递交时间',
  ],
  'domestic-planned-in-progress': [
    '官方登记号/批准文号',
    '与制剂关联审评历史',
    '交费/时间',
    '制剂剂型/规格/官方登记号',
    '是否为第一供应商',
    '制剂文件计划递交时间',
    '我司文件计划递交时间',
  ],
  'international-completed': [
    'MF官方登记号',
    '与制剂关联审评历史',
    '交费/时间',
    '代理机构',
    '制剂公司',
    '制剂剂型/规格/官方登记号',
    'LOA签署日期',
  ],
  'domestic-completed': [
    '官方登记号/批准文号',
    '与制剂关联审评历史',
    '交费/时间',
    '制剂剂型/规格/官方登记号',
    '是否为第一供应商',
    '制剂文件递交时间',
  ],
  'us-fda-progress': [
    '批量/包装规格',
    '制剂文件递交时间',
    '我司文件递交时间',
    '是否现场审计',
    '是否发货/时间',
  ],
}

function isColumnHidden(sheetKey: string, columnLabel: string): boolean {
  const hiddenLabels = HIDDEN_COLUMNS_BY_SHEET[sheetKey]
  if (!hiddenLabels) return false
  return hiddenLabels.some(
    (label) => columnLabel === label || columnLabel.includes(label) || label.includes(columnLabel)
  )
}

export default function DeclarationProgressPage({ detail }: DeclarationProgressPageProps) {
  const router = useRouter()
  const { message } = App.useApp()
  const [form] = Form.useForm<DeclarationProgressFormValues>()
  const [keyword, setKeyword] = useState('')
  const [projectFilter, setProjectFilter] = useState<string>()
  const [productFilter, setProductFilter] = useState<string>()
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null)
  const [editingRecord, setEditingRecord] = useState<DeclarationProgressRecord | null>(null)
  const [historyRecord, setHistoryRecord] = useState<DeclarationProgressRecord | null>(null)
  const [historyPayload, setHistoryPayload] = useState<DeclarationProgressRecordHistory | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [formModalOpen, setFormModalOpen] = useState(false)
  const [formMode, setFormMode] = useState<DeclarationProgressFormMode>('create-main')
  const [detailRecord, setDetailRecord] = useState<DeclarationProgressRecord | null>(null)
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [pending, startTransition] = useTransition()

  const projectColumnKey = useMemo(
    () =>
      detail.columns.find((column) => column.label.includes('项目名称'))?.key,
    [detail.columns]
  )
  const productColumnKey = useMemo(
    () =>
      detail.columns.find((column) =>
        ['产品', '产品名称', '涉及产品'].includes(column.label)
      )?.key,
    [detail.columns]
  )

  const projectOptions = useMemo(() => {
    if (!projectColumnKey) return []
    return Array.from(
      new Set(
        detail.records
          .map((record) => record.latest_values[projectColumnKey]?.trim())
          .filter((value): value is string => Boolean(value))
      )
    ).map((value) => ({ label: value, value }))
  }, [detail.records, projectColumnKey])

  const productOptions = useMemo(() => {
    if (!productColumnKey) return []
    return Array.from(
      new Set(
        detail.records
          .map((record) => record.latest_values[productColumnKey]?.trim())
          .filter((value): value is string => Boolean(value))
      )
    ).map((value) => ({ label: value, value }))
  }, [detail.records, productColumnKey])

  const filteredRecords = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase()
    return detail.records.filter((record) => {
      if (projectFilter && projectColumnKey) {
        if ((record.latest_values[projectColumnKey] || '').trim() !== projectFilter) {
          return false
        }
      }

      if (productFilter && productColumnKey) {
        if ((record.latest_values[productColumnKey] || '').trim() !== productFilter) {
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

  const tableColumns = useMemo<ColumnsType<DeclarationProgressRecord>>(
    () =>
      visibleColumns.map((column, index) => ({
        title: column.label,
        key: column.key,
        width: getColumnWidth(column.label),
        fixed: index === 0 ? ('left' as const) : undefined,
        align: 'center' as const,
        render: (_value: unknown, record: DeclarationProgressRecord) => {
          const content = renderCellValue(
            record.latest_values[column.key],
            record.latest_style_marks[column.key],
            {
              compact: true,
              clampLines: getMainCellClampLines(column.label),
            }
          )

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

  const historyColumns = useMemo<ColumnsType<DeclarationProgressHistoryDisplayRecord>>(
    () => [
      {
        title: '版本',
        key: 'version',
        width: 88,
        fixed: 'left',
        align: 'center',
        render: (_value, record) => (
          <Tag color={record.version === historyPayload?.history_count ? 'processing' : undefined}>
            {record.version === historyPayload?.history_count ? '最新' : `历史 ${record.version}`}
          </Tag>
        ),
      },
      ...detail.columns.map((column) => ({
        title: column.label,
        key: column.key,
        width: getColumnWidth(column.label),
        align: 'center' as const,
        render: (_value: unknown, record: DeclarationProgressHistoryDisplayRecord) =>
          renderCellValue(record.values[column.key], record.style_marks[column.key], {
            compact: true,
            emptyPlaceholder: '',
          }),
      })),
    ],
    [detail.columns, historyPayload?.history_count]
  )

  const historyData = useMemo<DeclarationProgressHistoryDisplayRecord[]>(
    () =>
      (historyPayload?.history_records || []).map((record) => ({
        ...record,
        key: record.entry_id,
      })),
    [historyPayload]
  )

  async function openHistoryModal(record: DeclarationProgressRecord | null) {
    if (!record) {
      message.warning('请先选择一条申报进度记录')
      return
    }
    setHistoryRecord(record)
    setHistoryPayload(null)
    setHistoryLoading(true)
    try {
      const payload = await fetchDeclarationProgressRecordHistory(record.record_id)
      setHistoryPayload(payload)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '获取历史失败')
    } finally {
      setHistoryLoading(false)
    }
  }

  function openCreateModal() {
    setFormMode('create-main')
    setEditingRecord(null)
    form.resetFields()
    const nextSequence =
      detail.records.reduce((maxValue, record) => Math.max(maxValue, record.sequence), 0) + 1
    form.setFieldsValue({
      [detail.columns[0].key]: String(nextSequence),
    })
    setFormModalOpen(true)
  }

  function openEditModal() {
    if (!selectedRecord) {
      message.warning('请先选择一条申报进度记录')
      return
    }
    setFormMode('edit-main')
    setEditingRecord(selectedRecord)
    form.setFieldsValue(
      Object.fromEntries(
        detail.columns.map((column) => [
          column.key,
          selectedRecord.latest_values[column.key] || undefined,
        ])
      )
    )
    setFormModalOpen(true)
  }

  function openCreateSubRecordModal() {
    if (!selectedRecord) {
      message.warning('请先选择一条申报进度主记录')
      return
    }
    if (!detail.supports_sub_records) {
      message.info('当前子表不支持新增子记录')
      return
    }
    setFormMode('create-sub-record')
    setEditingRecord(selectedRecord)
    form.setFieldsValue(
      Object.fromEntries(
        detail.columns.map((column) => [
          column.key,
          selectedRecord.latest_values[column.key] || undefined,
        ])
      )
    )
    setFormModalOpen(true)
  }

  function handleDelete() {
    if (!selectedRecord) {
      message.warning('请先选择一条申报进度记录')
      return
    }

    startTransition(async () => {
      try {
        await deleteDeclarationProgressEntry(selectedRecord.record_id, detail.sheet_key)
        message.success('申报进度记录已删除')
        setSelectedRecordId(null)
        router.refresh()
      } catch (error) {
        message.error(error instanceof Error ? error.message : '删除失败')
      }
    })
  }

  async function handleSubmit(values: DeclarationProgressFormValues) {
    const payload = toEntryInput(detail.sheet_key, detail.columns, values)

    startTransition(async () => {
      try {
        if (formMode === 'edit-main' && editingRecord) {
          await updateDeclarationProgressEntry(editingRecord.record_id, payload)
          message.success('申报进度记录已更新')
        } else if (formMode === 'create-sub-record' && editingRecord) {
          await createDeclarationProgressSubRecord(editingRecord.record_id, payload)
          message.success('申报进度子记录已新增')
        } else {
          await createDeclarationProgressEntry(payload)
          message.success('申报进度主记录已新增')
        }
        setFormModalOpen(false)
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
          {
            title: <Link href="/registration/project">申报项目</Link>,
          },
          {
            title: <Link href="/registration/declaration-progress">申报进度</Link>,
          },
          {
            title: detail.sheet_name,
          },
        ]}
      />

      <Space orientation="vertical" size={4}>
        <Typography.Title level={3} style={{ marginBottom: 0 }}>
          {detail.sheet_name}
        </Typography.Title>
      </Space>

      <Card
        size="small"
        extra={
          <Space>
            <Button icon={<PlusOutlined />} type="primary" onClick={openCreateModal}>
              新增主记录
            </Button>
            <Button icon={<EditOutlined />} disabled={!selectedRecord} onClick={openEditModal}>
              编辑选中
            </Button>
            {detail.supports_sub_records ? (
              <Button icon={<PlusOutlined />} disabled={!selectedRecord} onClick={openCreateSubRecordModal}>
                新增子记录
              </Button>
            ) : null}
            <Button
              icon={<EyeOutlined />}
              disabled={!selectedRecord}
              onClick={() => void openHistoryModal(selectedRecord)}
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
              title="确认删除选中的申报进度记录吗？"
              okText="删除"
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
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Space wrap size={12}>
            {projectColumnKey ? (
              <Select
                allowClear
                showSearch
                placeholder="按项目筛选"
                value={projectFilter}
                onChange={(value) => setProjectFilter(value)}
                options={projectOptions}
                style={{ width: 280 }}
                optionFilterProp="label"
              />
            ) : null}
            {productColumnKey ? (
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
            ) : null}
            <Input
              allowClear
              placeholder="按任意字段搜索"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              style={{ width: 280 }}
            />
          </Space>

          <Table<DeclarationProgressRecord>
            rowKey="record_id"
            columns={tableColumns}
            dataSource={filteredRecords}
            rowSelection={{
              type: 'radio',
              selectedRowKeys: selectedRecordId ? [selectedRecordId] : [],
              onChange: (selectedRowKeys) => {
                setSelectedRecordId((selectedRowKeys[0] as string) || null)
              },
            }}
            pagination={{ pageSize: 20, showSizeChanger: true }}
            scroll={{ x: 'max-content', y: 640 }}
          />
        </Space>
      </Card>

      <Modal
        destroyOnHidden
        confirmLoading={pending}
        open={formModalOpen}
        width={1000}
        title={
          formMode === 'create-main'
            ? '新增申报进度主记录'
            : formMode === 'create-sub-record'
              ? '新增申报进度子记录'
              : '编辑申报进度记录'
        }
        okText="保存"
        cancelText="取消"
        onCancel={() => setFormModalOpen(false)}
        onOk={() => form.submit()}
      >
        <Form<DeclarationProgressFormValues> form={form} layout="vertical" onFinish={handleSubmit}>
          <Table<DeclarationProgressColumn>
            rowKey="key"
            pagination={false}
            size="small"
            dataSource={detail.columns}
            columns={[
              {
                title: '字段',
                key: 'label',
                width: 260,
                render: (_value, record) => <Typography.Text strong>{record.label}</Typography.Text>,
              },
              {
                title: '内容',
                key: 'input',
                render: (_value, record) => (
                  <Form.Item
                    name={record.key}
                    style={{ marginBottom: 0 }}
                    tooltip={
                      formMode === 'create-sub-record' && record.is_main
                        ? '子记录场景下主字段将沿用当前主记录值'
                        : undefined
                    }
                  >
                    <Input.TextArea
                      autoSize={{ minRows: isLongTextField(record.label) ? 4 : 2, maxRows: 12 }}
                      placeholder={`请输入${record.label}`}
                      disabled={formMode === 'create-sub-record' && record.is_main}
                    />
                  </Form.Item>
                ),
              },
            ]}
          />
        </Form>
      </Modal>

      <Modal
        footer={null}
        open={Boolean(historyRecord)}
        width={1200}
        title={historyRecord ? `${historyRecord.sequence} 号记录历史` : '记录历史'}
        onCancel={() => {
          setHistoryRecord(null)
          setHistoryPayload(null)
        }}
      >
        <Table<DeclarationProgressHistoryDisplayRecord>
          rowKey="key"
          columns={historyColumns}
          dataSource={historyData}
          loading={historyLoading}
          pagination={false}
          scroll={{ x: 'max-content', y: 520 }}
        />
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
        className="declaration-progress-detail-modal"
        title={
          detailRecord
            ? `${detailRecord.latest_values[projectColumnKey || ''] || detail.sheet_name} - 详情`
            : '详情'
        }
      >
        {detailRecord ? (
          <Descriptions column={2} bordered size="small">
            {detail.columns.map((column) => (
              <Descriptions.Item
                key={column.key}
                label={column.label}
                span={isLongTextField(column.label) ? 2 : 1}
              >
                {renderCellValue(
                  detailRecord.latest_values[column.key],
                  detailRecord.latest_style_marks[column.key],
                  { emptyPlaceholder: '—' }
                )}
              </Descriptions.Item>
            ))}
          </Descriptions>
        ) : null}
      </Modal>

      <style jsx global>{`
        .declaration-progress-detail-modal .ant-descriptions-item-label {
          background: #faf8ff;
          font-weight: 600;
          font-size: 13px;
          width: 140px;
        }

        .declaration-progress-detail-modal .ant-descriptions-item-content {
          font-size: 13px;
        }
      `}</style>
    </Space>
  )
}
