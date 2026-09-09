'use client'

import { useEffect, useState } from 'react'
import { App, Button, Modal, Radio, Space } from 'antd'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { batchDeleteFeishuValidationsAction, createFeishuValidationAction, deleteFeishuValidationAction, updateFeishuValidationAction } from '@/actions/quality'
import { fetchValidationFormLinks, fetchValidations, fetchValidationExecutions } from '@/lib/api/client/quality'
import type { ValidationListItem, ValidationExecutionItem } from '@/types/quality'
import { ValidationEditModal } from './ValidationEditModal'
import { ValidationDetailDrawer } from './ValidationDetailDrawer'
import { ValidationTable } from './ValidationTable'

/** 台账行：主列表为本地验证记录（无 record_id），子表为飞书执行记录（含 record_id） */
type ValidationRow = (ValidationListItem | ValidationExecutionItem) & { record_id?: string | null; id?: string }

/** 飞书操作优先用 record_id；本地记录回退主键 id */
function getRowRecordId(row: ValidationRow): string {
  return row.record_id || row.id || ''
}

interface ValidationLedgerPageProps {
  mode: 'master' | 'child'
  title: string
  description: string
  validationType?: string
}

interface ValidationTableFilters {
  record_code: string
  keyword: string
  status: string
  department: string
  validation_type: string
  planned_end_date_from: string
  planned_end_date_to: string
  drafted_at_from: string
  drafted_at_to: string
  /** 年度表；空 = 验证总表 */
  year: string
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

export function ValidationLedgerPage({
  mode,
  validationType,
  title,
  description,
}: ValidationLedgerPageProps) {
  const { message, modal } = App.useApp()
  const queryClient = useQueryClient()
  const [saving, setSaving] = useState(false)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filters, setFilters] = useState<ValidationTableFilters>({
    record_code: '',
    keyword: '',
    status: '',
    department: '',
    validation_type: '',
    planned_end_date_from: '',
    planned_end_date_to: '',
    drafted_at_from: '',
    drafted_at_to: '',
    // 子台账默认筛选当年年度表；主计划默认总表（全部年份）
    year: mode === 'child' ? String(new Date().getFullYear()) : '',
  })
  const [editorOpen, setEditorOpen] = useState(false)
  const [editingRecord, setEditingRecord] = useState<ValidationRow | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)
  const [detailRecord, setDetailRecord] = useState<ValidationRow | null>(null)
  // 主计划新增改为打开对应年度的飞书多维表单（表单可写群组等开放接口不支持的字段）
  const [formLinkOpen, setFormLinkOpen] = useState(false)
  const [formLinkYear, setFormLinkYear] = useState<number>(new Date().getFullYear())
  const formLinksQuery = useQuery({
    queryKey: ['validation-form-links'],
    queryFn: fetchValidationFormLinks,
    enabled: mode === 'master',
  })
  const formLinks = formLinksQuery.data ?? []
  const selectedFormLink = formLinks.find((item) => item.year === formLinkYear)

  /** 主计划模式：写入/删除统一走验证主计划实体（年度表含全部验证类别） */
  const mutationValidationType =
    mode === 'child' ? validationType : undefined
  /** 选择年度后读写对应年度表（主计划与子台账一致） */
  const mutationYear =
    filters.year ? Number(filters.year) : undefined

  const { data, isLoading: loading, error } = useQuery<{ items: ValidationRow[]; total: number }>({
    queryKey: ['quality-validation', 'list', {
      mode,
      validationType: validationType ?? '',
      record_code: filters.record_code,
      keyword: filters.keyword,
      status: filters.status,
      department: filters.department,
      validation_type: filters.validation_type,
      planned_end_date_from: filters.planned_end_date_from,
      planned_end_date_to: filters.planned_end_date_to,
      drafted_at_from: filters.drafted_at_from,
      drafted_at_to: filters.drafted_at_to,
      year: filters.year,
      page,
      pageSize,
    }],
    queryFn: () =>
      mode === 'master'
        ? fetchValidations({
            validation_type: filters.validation_type || undefined,
            record_code: filters.record_code || undefined,
            keyword: filters.keyword || undefined,
            status: filters.status || undefined,
            department: filters.department || undefined,
            planned_end_date_from: filters.planned_end_date_from || undefined,
            planned_end_date_to: filters.planned_end_date_to || undefined,
            year: filters.year ? Number(filters.year) : undefined,
            page,
            page_size: pageSize,
          })
        : fetchValidationExecutions(validationType ?? '', {
            keyword: filters.keyword || undefined,
            status: filters.status || undefined,
            department: filters.department || undefined,
            drafted_at_from: filters.drafted_at_from || undefined,
            drafted_at_to: filters.drafted_at_to || undefined,
            year: filters.year ? Number(filters.year) : undefined,
            page,
            page_size: pageSize,
          }),
  })

  useEffect(() => {
    if (error) {
      message.error(getErrorMessage(error, `加载${title}失败`))
    }
  }, [error, message, title])

  const items = data?.items ?? []
  const total = data?.total ?? 0

  const handleCreate = () => {
    if (mode === 'master') {
      setFormLinkYear(filters.year ? Number(filters.year) : new Date().getFullYear())
      setFormLinkOpen(true)
      return
    }
    setEditingRecord(null)
    setEditorOpen(true)
  }

  const handleOpenFeishuForm = () => {
    const url = (selectedFormLink?.form_url || '').trim()
    if (!url) {
      message.warning(`${formLinkYear} 年表单链接未配置，请到 质量管理-设置-飞书设置 中粘贴表单链接`)
      return
    }
    window.open(url, '_blank', 'noopener,noreferrer')
    setFormLinkOpen(false)
    message.info(`已打开 ${formLinkYear} 年飞书表单；提交后回到本页点击「刷新」即可看到新记录`)
  }

  const handleDetail = (record: ValidationRow) => {
    setDetailRecord(record)
    setDetailOpen(true)
  }

  const handleEdit = (record: ValidationListItem) => {
    setEditingRecord(record)
    setEditorOpen(true)
  }

  const handleDelete = (record: ValidationListItem) => {
    modal.confirm({
      title: '确认删除',
      content: `确定要删除记录 "${record.title}" 吗？`,
      okText: '确认',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteFeishuValidationAction(
            getRowRecordId(record),
            mutationValidationType ?? record.validation_type,
            mutationYear
          )
          message.success('删除成功')
          queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })
        } catch (error: unknown) {
          message.error(getErrorMessage(error, '删除失败'))
        }
      },
    })
  }

  const handleSubmit = async (
    values: Record<string, unknown>,
    targetYear?: number
  ) => {
    try {
      setSaving(true)
      if (editingRecord) {
        await updateFeishuValidationAction(
          getRowRecordId(editingRecord),
          values,
          mutationValidationType ?? editingRecord.validation_type ?? undefined,
          mutationYear
        )
        message.success(`${title}已更新`)
      } else {
        // 新增以弹窗内选择的年度表为准（未选择时回退页面年份筛选）
        await createFeishuValidationAction(
          values,
          targetYear ?? mutationYear
        )
        message.success(`${title}已创建`)
      }
      setEditorOpen(false)
      queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, `保存${title}失败`))
    } finally {
      setSaving(false)
    }
  }

  const handleBatchDelete = async (recordIds: string[]) => {
    try {
      await batchDeleteFeishuValidationsAction(recordIds, mutationValidationType, mutationYear)
      message.success(`成功删除 ${recordIds.length} 条记录`)
      queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })
    } catch (error: unknown) {
      message.error(getErrorMessage(error, '批量删除失败'))
    }
  }

  return (
    <div>
      <div style={{ marginBottom: 16 }}>
        <p className="mb-2 text-[13px] text-[var(--color-stone)]">质量管理 / 验证与确认 / {title}</p>
        <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0 }}>
          {mode === 'master' ? title : `${title}执行台账`}
        </h1>
        <p style={{ marginTop: 8, color: 'var(--color-steel)' }}>{description}</p>
      </div>

      <ValidationTable
        mode={mode}
        validationType={validationType}
        items={items as ValidationListItem[]}
        total={total}
        loading={loading}
        page={page}
        pageSize={pageSize}
        filters={filters}
        onFilterChange={(patch) => {
          setPage(1)
          setFilters((prev) => ({ ...prev, ...patch }))
        }}
        onPageChange={(nextPage, nextPageSize) => {
          setPage(nextPage)
          setPageSize(nextPageSize)
        }}
        onRefresh={() => queryClient.invalidateQueries({ queryKey: ['quality-validation', 'list'] })}
        onCreate={handleCreate}
        onDetail={handleDetail}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onBatchDelete={handleBatchDelete}
      />

      <ValidationDetailDrawer
        open={detailOpen}
        record={detailRecord as Record<string, unknown> | null}
        onClose={() => {
          setDetailOpen(false)
          setDetailRecord(null)
        }}
      />

      <ValidationEditModal
        open={editorOpen}
        saving={saving}
        validationType={validationType}
        validationTypeLabel={title}
        hideCategory={mode === 'master' && Boolean(filters.year)}
        year={mutationYear}
        initialValue={editingRecord as ValidationListItem | null}
        onCancel={() => setEditorOpen(false)}
        onSubmit={handleSubmit}
      />

      <Modal
        title="新增验证记录（飞书表单）"
        open={formLinkOpen}
        onCancel={() => setFormLinkOpen(false)}
        footer={[
          <Button key="cancel" onClick={() => setFormLinkOpen(false)}>
            取消
          </Button>,
          <Button
            key="open"
            type="primary"
            disabled={!selectedFormLink?.form_url}
            onClick={handleOpenFeishuForm}
          >
            打开 {formLinkYear} 年表单
          </Button>,
        ]}
        width={460}
      >
        <p style={{ marginTop: 0, color: 'var(--color-steel)' }}>
          请选择要录入的验证年度台账，将打开对应的飞书多维表单；群组等字段可在表单中直接填写。
        </p>
        <Radio.Group
          value={formLinkYear}
          onChange={(event) => setFormLinkYear(event.target.value)}
          style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
        >
          <Space direction="vertical" size={8}>
            {formLinks.map((item) => (
              <Radio key={item.year} value={item.year}>
                {item.year}年验证台账
                {!item.table_configured && (
                  <span style={{ color: 'var(--color-stone)' }}>（年度表未配置）</span>
                )}
                {!item.form_url && item.table_configured && (
                  <span style={{ color: 'var(--color-stone)' }}>（表单链接未配置）</span>
                )}
              </Radio>
            ))}
            {formLinks.length === 0 && (
              <span style={{ color: 'var(--color-stone)' }}>表单链接加载中…</span>
            )}
          </Space>
        </Radio.Group>
      </Modal>
    </div>
  )
}
