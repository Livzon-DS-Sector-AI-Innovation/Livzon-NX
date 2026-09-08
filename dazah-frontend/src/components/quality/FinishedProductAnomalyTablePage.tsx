'use client'

import { useEffect, useMemo, useState } from 'react'
import { App, Alert, Button, Input, Select, Space, Table, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { useSearchParams } from 'next/navigation'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  EyeOutlined,
  LinkOutlined,
  FileSyncOutlined,
} from '@ant-design/icons'
import {
  fetchAnomalyReportFields,
  fetchAnomalyReportRecords,
  fetchAnomalyReportShareLinks,
  fetchAnomalyReportYears,
} from '@/lib/api/client/quality'
import type {
  AnomalyReportFieldMeta,
  AnomalyReportRecord,
  AnomalyReportYearStatus,
} from '@/types/quality'
import {
  createAnomalyReportRecord,
  deleteAnomalyReportRecord,
  updateAnomalyReportRecord,
} from '@/actions/finished-product-anomaly'
import { FinishedProductAnomalyDetailDrawer } from './FinishedProductAnomalyDetailDrawer'
import { FinishedProductAnomalyFormModal } from './FinishedProductAnomalyFormModal'
import { FeishuAttachmentPreviewModal } from './FeishuAttachmentPreviewModal'
import {
  renderFeishuValue,
  type FeishuAttachmentUrlBuilder,
  type FeishuAttachmentPreviewContext,
  type RenderFeishuValueOptions,
} from './inspection/renderFeishuValue'
import { TableEmptyState } from './TableEmptyState'

interface AttachmentPreviewState {
  recordId: string
  fileName: string
  fileToken: string
}

/** 按钮类字段是飞书自动化动作，不作为数据展示 */
const HIDDEN_UI_TYPES = new Set(['Button'])

/**
 * 年度列定制（与飞书子表字段一一对应）：
 * exclude = 不进列表、只在详情抽屉中查看；
 * narrow = 90px；medium = 108px（约 1.2 倍窄列）；wide = 加宽列（百分比）。
 * 显式档位优先于内容类型自动窄列。
 */
const ANOMALY_YEAR_COLUMN_OVERRIDES: Record<
  number,
  {
    exclude: string[]
    narrow: string[]
    medium?: string[]
    wide?: string[]
  }
> = {
  2025: {
    exclude: ['调查结果说明', '是否结案'],
    narrow: ['发现时间', '数据来源'],
  },
  2026: {
    exclude: ['自动编号', '是否结案', '跟踪情况'],
    narrow: ['数据来源', '提交人'],
    medium: ['涉及产品', '提交时间'],
    wide: ['不合格项目描述'],
  },
}

/** 内容天然很短的展示类型，统一压缩列宽 */
const NARROW_UI_TYPES = new Set([
  'DateTime',
  'CreatedTime',
  'ModifiedTime',
  'CreatedUser',
])

const NARROW_FIELD_WIDTH = 90
const MEDIUM_FIELD_WIDTH = 108
const WIDE_FIELD_WIDTH = '26%'

function anomalyAttachmentUrlBuilder(year: number): FeishuAttachmentUrlBuilder {
  return (_entityCode, recordId, fileToken) =>
    `/api/v1/quality/finished-product-anomaly/records/${encodeURIComponent(recordId)}/attachments/${encodeURIComponent(fileToken)}/content?year=${year}`
}

/**
 * 台账列 = 全部展示字段（排除飞书自动化按钮与年度排除项），
 * 其余字段仍可在详情抽屉中查看。
 */
function buildListFields(
  fieldMetas: AnomalyReportFieldMeta[],
  exclude: string[],
): string[] {
  const excluded = new Set(exclude)
  return fieldMetas
    .filter((meta) => !HIDDEN_UI_TYPES.has(meta.ui_type))
    .filter((meta) => !excluded.has(meta.field_name))
    .map((meta) => meta.field_name)
}

/** 显式档位（宽/中/窄）优先，其次按内容类型自动压缩 */
function resolveFieldWidth(
  fieldName: string,
  meta: AnomalyReportFieldMeta | undefined,
  overrides: { narrow: string[]; medium?: string[]; wide?: string[] },
): number | string | undefined {
  if (overrides.wide?.includes(fieldName)) return WIDE_FIELD_WIDTH
  if (overrides.medium?.includes(fieldName)) return MEDIUM_FIELD_WIDTH
  if (overrides.narrow.includes(fieldName) || NARROW_UI_TYPES.has(meta?.ui_type ?? '')) {
    return NARROW_FIELD_WIDTH
  }
  return undefined
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

function resolveDefaultYear(years: AnomalyReportYearStatus[] | undefined): number | null {
  if (!years || years.length === 0) return null
  const configured = years.filter((item) => item.table_configured)
  if (configured.length === 0) return null
  const currentYear = new Date().getFullYear()
  const current = configured.find((item) => item.year === currentYear)
  return (current ?? configured[configured.length - 1]).year
}

/** 成品异常报告台账：单页年份筛选直读对应飞书子表，新增/编辑/删除实时写回。 */
export function FinishedProductAnomalyTablePage() {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const searchParams = useSearchParams()
  const requestedYear = Number(searchParams.get('year')) || 0
  const [year, setYear] = useState<number | null>(requestedYear || null)
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [detailRecord, setDetailRecord] = useState<AnomalyReportRecord | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<AnomalyReportRecord | null>(null)
  const [saving, setSaving] = useState(false)
  const [previewFile, setPreviewFile] = useState<AttachmentPreviewState | null>(null)

  const { data: years } = useQuery({
    queryKey: ['anomaly-report', 'years'],
    queryFn: fetchAnomalyReportYears,
  })
  const configuredYears = useMemo(
    () => (years ?? []).filter((item) => item.table_configured),
    [years],
  )

  const activeYear =
    year ?? resolveDefaultYear(years) ?? 0
  const { data: fieldsResult } = useQuery({
    queryKey: ['anomaly-report', 'fields', activeYear],
    queryFn: () => fetchAnomalyReportFields(activeYear),
    enabled: activeYear > 0,
  })
  const listQuery = useQuery({
    queryKey: ['anomaly-report', 'list', activeYear, keyword, page, pageSize],
    queryFn: () =>
      fetchAnomalyReportRecords(activeYear, {
        keyword: keyword || undefined,
        page,
        page_size: pageSize,
      }),
    enabled: activeYear > 0,
  })

  const records = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0
  const fieldMetas = useMemo(
    () => fieldsResult?.fields ?? ([] as AnomalyReportFieldMeta[]),
    [fieldsResult],
  )
  const yearStatus = years?.find((item) => item.year === activeYear)
  const columnOverrides =
    ANOMALY_YEAR_COLUMN_OVERRIDES[activeYear] ?? { exclude: [], narrow: [] }
  const listFields = useMemo(
    () => buildListFields(fieldMetas, columnOverrides.exclude),
    [fieldMetas, columnOverrides.exclude],
  )

  useEffect(() => {
    if (listQuery.error) {
      message.error(
        getErrorMessage(listQuery.error, `加载${activeYear}年成品异常报告失败`),
      )
    }
  }, [listQuery.error, message, activeYear])

  const openDetail = (record: AnomalyReportRecord) => {
    setDetailRecord(record)
    setDetailOpen(true)
  }

  /** 附件点击进入弹窗预览（图片/PDF 原样，doc/wps/表格由后端转 PDF） */
  const handleAttachmentPreview: RenderFeishuValueOptions['onAttachmentPreview'] = ({
    record,
    attachment,
  }: FeishuAttachmentPreviewContext) => {
    const recordId = String(record.record_id ?? '')
    const fileToken = attachment.file_token || ''
    if (!recordId || !fileToken) {
      message.warning('该附件缺少文件标识，无法预览')
      return
    }
    setPreviewFile({
      recordId,
      fileName: attachment.name || '附件',
      fileToken,
    })
  }

  const attachmentCellOptions = (
    meta: AnomalyReportFieldMeta | undefined,
  ): RenderFeishuValueOptions => ({
    uiType: meta?.ui_type,
    attachmentUrlBuilder: anomalyAttachmentUrlBuilder(activeYear),
    onAttachmentPreview: handleAttachmentPreview,
  })

  /** 生成并打开该记录在飞书中的行级链接（share link 形式） */
  const openRowInFeishu = async (record: AnomalyReportRecord) => {
    try {
      const links = await fetchAnomalyReportShareLinks(activeYear, [record.record_id])
      const url = links[record.record_id]
      if (!url) {
        message.warning('该记录未生成飞书链接（可能无权限或记录不存在）')
        return
      }
      window.open(url, '_blank', 'noopener,noreferrer')
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '生成飞书记录链接失败'))
    }
  }

  const handleDelete = (record: AnomalyReportRecord) => {
    const titleField = listFields[0]
    const name = String(record[titleField] ?? record.record_id)
    modal.confirm({
      title: '确认删除',
      content: `确定要删除记录 "${name}" 吗？删除会同步到飞书多维表格。`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteAnomalyReportRecord(activeYear, record.record_id)
          message.success('删除成功')
          queryClient.invalidateQueries({
            queryKey: ['anomaly-report', 'list', activeYear],
          })
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  const handleSubmit = async (fields: Record<string, unknown>) => {
    try {
      setSaving(true)
      if (editingRecord) {
        await updateAnomalyReportRecord(activeYear, editingRecord.record_id, fields)
        message.success('成品异常报告记录已更新')
      } else {
        await createAnomalyReportRecord(activeYear, fields)
        message.success('成品异常报告记录已创建')
      }
      setEditorOpen(false)
      setEditingRecord(null)
      queryClient.invalidateQueries({
        queryKey: ['anomaly-report', 'list', activeYear],
      })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '保存成品异常报告记录失败'))
    } finally {
      setSaving(false)
    }
  }

  const columns: ColumnsType<AnomalyReportRecord> = listFields.map(
    (fieldName, index) => {
      const meta = fieldMetas.find((item) => item.field_name === fieldName)
      return {
        title: fieldName,
        key: fieldName,
        width: resolveFieldWidth(fieldName, meta, columnOverrides),
        ellipsis: true,
        render: (_: unknown, record: AnomalyReportRecord) => {
          const text =
            typeof record[fieldName] === 'string'
              ? (record[fieldName] as string).trim()
              : ''
          const cell =
            index === 0 ? (
              <a
                onClick={() => openDetail(record)}
                style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}
              >
                {renderFeishuValue(
                  record[fieldName],
                  record,
                  undefined,
                  message,
                  attachmentCellOptions(meta),
                )}
              </a>
            ) : (
              <div style={{ whiteSpace: 'normal', wordBreak: 'break-all' }}>
                {renderFeishuValue(
                  record[fieldName],
                  record,
                  undefined,
                  message,
                  attachmentCellOptions(meta),
                )}
              </div>
            )
          return text && index !== 0 ? (
            <Tooltip title={text} placement="topLeft">
              {cell}
            </Tooltip>
          ) : (
            cell
          )
        },
      }
    },
  )

  columns.push({
    title: '操作',
    key: 'action',
    width: 150,
    render: (_: unknown, record: AnomalyReportRecord) => (
      <Space size={0} wrap>
        <Button
          size="small"
          type="text"
          icon={<FileSyncOutlined />}
          title="打开飞书对应行"
          onClick={() => void openRowInFeishu(record)}
        />
        <Button size="small" type="text" icon={<EyeOutlined />} onClick={() => openDetail(record)} />
        <Button
          size="small"
          type="text"
          icon={<EditOutlined />}
          onClick={() => {
            setEditingRecord(record)
            setEditorOpen(true)
          }}
        />
        <Button size="small" type="text" danger icon={<DeleteOutlined />} onClick={() => handleDelete(record)} />
      </Space>
    ),
  })

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 成品异常报告 / 异常台账</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>
          成品异常报告台账{activeYear > 0 ? `（${activeYear}年）` : ''}
        </h1>
        <p style={{ marginTop: 8, color: 'var(--color-steel)' }}>
          按年份筛选飞书成品异常报告子表；支持新增、编辑、删除（实时同步飞书），点击行查看全部内容与附件。
        </p>
      </div>

      {years && configuredYears.length === 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="成品异常报告飞书表未配置"
          description="请到 质量管理 → 质量设置 → 飞书设置 中为「成品异常报告」各年度绑定 App Token 与表 ID 后刷新本页。"
        />
      )}

      <Space wrap style={{ marginBottom: 12 }}>
        <Select
          style={{ width: 130 }}
          placeholder="选择年份"
          loading={!years}
          value={activeYear > 0 ? activeYear : undefined}
          onChange={(value) => {
            setYear(value)
            setPage(1)
          }}
          options={configuredYears.map((item) => ({
            label: `${item.year}年`,
            value: item.year,
          }))}
        />
        <Input
          placeholder="关键词搜索"
          style={{ width: 240 }}
          value={keyword}
          allowClear
          onChange={(event) => {
            setKeyword(event.target.value)
            setPage(1)
          }}
        />
        <Button
          icon={<LinkOutlined />}
          onClick={() => {
            const url = yearStatus?.feishu_url
            if (url) {
              window.open(url, '_blank', 'noopener,noreferrer')
            } else {
              message.warning('当前年度飞书表未配置，无法打开')
            }
          }}
        >
          打开飞书表格
        </Button>
        <Button
          icon={<PlusOutlined />}
          type="primary"
          disabled={activeYear <= 0}
          onClick={() => {
            setEditingRecord(null)
            setEditorOpen(true)
          }}
        >
          新增
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => queryClient.invalidateQueries({ queryKey: ['anomaly-report'] })}
        >
          刷新
        </Button>
      </Space>

      <Table<AnomalyReportRecord>
        rowKey="record_id"
        loading={listQuery.isLoading}
        dataSource={records}
        columns={columns}
        tableLayout="fixed"
        locale={{
          emptyText: (
            <TableEmptyState hasFilters={Boolean(keyword) || page > 1} />
          ),
        }}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          showQuickJumper: true,
          showTotal: (count) => `共 ${count} 条`,
          onChange: (nextPage, nextPageSize) => {
            setPage(nextPage)
            setPageSize(nextPageSize)
          },
        }}
      />

      <FinishedProductAnomalyDetailDrawer
        open={detailOpen}
        record={detailRecord}
        fieldMetas={fieldMetas}
        attachmentUrlBuilder={anomalyAttachmentUrlBuilder(activeYear)}
        onAttachmentPreview={handleAttachmentPreview}
        onClose={() => {
          setDetailOpen(false)
          setDetailRecord(null)
        }}
      />

      <FeishuAttachmentPreviewModal
        open={previewFile !== null}
        fileName={previewFile?.fileName ?? ''}
        previewSrc={
          previewFile
            ? `/api/v1/quality/finished-product-anomaly/records/${encodeURIComponent(previewFile.recordId)}/attachments/${encodeURIComponent(previewFile.fileToken)}/preview?year=${activeYear}`
            : ''
        }
        downloadSrc={
          previewFile
            ? anomalyAttachmentUrlBuilder(activeYear)(
                '',
                previewFile.recordId,
                previewFile.fileToken,
              )
            : ''
        }
        onClose={() => setPreviewFile(null)}
      />

      <FinishedProductAnomalyFormModal
        open={editorOpen}
        saving={saving}
        year={activeYear}
        fieldMetas={fieldMetas}
        initialRecord={editingRecord}
        onCancel={() => {
          setEditorOpen(false)
          setEditingRecord(null)
        }}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
