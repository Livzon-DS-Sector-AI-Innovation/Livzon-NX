'use client'

import { useEffect, useMemo, useState } from 'react'
import type { Key } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  App,
  Button,
  Input,
  Popconfirm,
  Switch,
  Table,
  Tag,
  Upload,
} from 'antd'
import type { UploadProps } from 'antd'
import {
  DeleteOutlined,
  FilePdfOutlined,
  InboxOutlined,
  ReloadOutlined,
} from '@ant-design/icons'
import {
  deleteInvoiceRecognitionRecord,
  deleteInvoiceRecognitionRecords,
  recognizeInvoicePdf,
} from '@/actions/purchasing'
import { fetchInvoiceRecognitionRecords } from '@/lib/api/purchasing'
import { isPresentDecimal, sumMoney, sumQuantity } from '@/lib/purchasing/decimal'
import type { InvoiceLineItem, InvoiceRecognitionRecordResponse } from '@/types/purchasing'

const { Dragger } = Upload
const { Search } = Input
const DEFAULT_PAGE_SIZE = 20
const MAX_INVOICE_UPLOAD_SIZE_MB = 50
const MAX_INVOICE_UPLOAD_SIZE_BYTES = MAX_INVOICE_UPLOAD_SIZE_MB * 1024 * 1024

type RecognitionStatus = 'recognizing' | 'success' | 'error'

type InvoiceRecognitionRecord = {
  recognitionId: string
  fileName: string
  includeDetails: boolean
  status: RecognitionStatus
  result?: InvoiceRecognitionRecordResponse
  errorMessage?: string
}

type InvoiceSummaryRow = {
  recognitionRowKey: string
  recordId?: string
  fileName: string
  status: RecognitionStatus
  invoiceNumber: string
  invoiceDate: string
  sellerName: string
  totalTaxAmount: string
  totalAmountWithTaxSmall: string
  errorMessage: string
  canDelete: boolean
}

type InvoiceDetailRow = {
  recognitionRowKey: string
  fileName: string
  projectName: string
  unit: string
  quantity: string
}

type SellerSummaryRow = {
  recognitionRowKey: string
  sellerName: string
  invoiceCount: number
  totalTaxAmount: string
  totalAmountWithTaxSmall: string
  totalQuantity: string
}

type ItemQuantitySummaryRow = {
  recognitionRowKey: string
  sellerName: string
  projectName: string
  unit: string
  totalQuantity: string
}

function displayValue(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return '-'
  return String(value)
}

function displayMoney(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === '') return '-'
  return `¥${value}`
}

function statusTag(status: RecognitionStatus) {
  if (status === 'recognizing') {
    return <Tag color="processing">识别中</Tag>
  }
  if (status === 'success') {
    return <Tag color="success">已完成</Tag>
  }
  return <Tag color="error">失败</Tag>
}

function toRecognitionRecord(
  record: InvoiceRecognitionRecordResponse
): InvoiceRecognitionRecord {
  return {
    recognitionId: record.id,
    fileName: record.file_name,
    includeDetails: record.include_details,
    status: 'success',
    result: record,
  }
}

export function InvoiceRecognitionClient({
  initialRecords,
  initialTotal,
  initialLoadFailed = false,
}: {
  initialRecords: InvoiceRecognitionRecordResponse[]
  initialTotal: number
  initialLoadFailed?: boolean
}) {
  const { message } = App.useApp()
  const [pendingCount, setPendingCount] = useState(0)
  const [includeDetails, setIncludeDetails] = useState(false)
  const [uploadRecords, setUploadRecords] = useState<InvoiceRecognitionRecord[]>([])
  const [submittedKeyword, setSubmittedKeyword] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [selectedRowKeys, setSelectedRowKeys] = useState<Key[]>([])
  const [deletingRecordIds, setDeletingRecordIds] = useState<string[]>([])
  const loading = pendingCount > 0
  const deleting = deletingRecordIds.length > 0
  const initialRecordResponse = useMemo(
    () => ({
      code: 200,
      message: 'success',
      data: initialRecords,
      meta: {
        page: 1,
        page_size: DEFAULT_PAGE_SIZE,
        total: initialTotal,
      },
    }),
    [initialRecords, initialTotal]
  )
  const { data: recordResponse, isFetching, refetch } = useQuery({
    queryKey: ['procurement-invoice-recognition-records', submittedKeyword, currentPage],
    queryFn: () =>
      fetchInvoiceRecognitionRecords({
        keyword: submittedKeyword || undefined,
        page: currentPage,
        page_size: DEFAULT_PAGE_SIZE,
      }),
    initialData:
      initialLoadFailed || submittedKeyword || currentPage !== 1
        ? undefined
        : initialRecordResponse,
  })

  const records = useMemo<InvoiceRecognitionRecord[]>(() => {
    const uploadedRecordIds = new Set(
      uploadRecords
        .map((record) => record.result?.id)
        .filter((recordId): recordId is string => Boolean(recordId))
    )
    const persistedRecords = (recordResponse?.data ?? [])
      .map(toRecognitionRecord)
      .filter((record) => !uploadedRecordIds.has(record.result?.id ?? ''))

    return [...uploadRecords, ...persistedRecords]
  }, [recordResponse?.data, uploadRecords])

  const recordTotal = useMemo(() => {
    const total = Number(recordResponse?.meta?.total ?? initialTotal)
    return Number.isFinite(total) ? total : records.length
  }, [initialTotal, recordResponse?.meta?.total, records.length])

  const summaryRows = useMemo<InvoiceSummaryRow[]>(
    () =>
      records.map((record) => ({
        recognitionRowKey: record.recognitionId,
        recordId: record.result?.id,
        fileName: record.fileName,
        status: record.status,
        invoiceNumber: displayValue(record.result?.invoice_number),
        invoiceDate: displayValue(record.result?.invoice_date),
        sellerName: displayValue(record.result?.seller_name),
        totalTaxAmount: displayMoney(record.result?.total_tax_amount),
        totalAmountWithTaxSmall: displayMoney(record.result?.total_amount_with_tax_small),
        errorMessage: record.errorMessage ?? '-',
        canDelete: record.status === 'success' && Boolean(record.result?.id),
      })),
    [records]
  )

  const deletableRecordIdSet = useMemo(
    () =>
      new Set(
        summaryRows
          .filter((row) => row.canDelete && row.recordId)
          .map((row) => row.recordId as string)
      ),
    [summaryRows]
  )

  const selectedRecordIds = useMemo(
    () =>
      selectedRowKeys
        .map(String)
        .filter((recordId) => deletableRecordIdSet.has(recordId)),
    [deletableRecordIdSet, selectedRowKeys]
  )

  useEffect(() => {
    setSelectedRowKeys((currentKeys) =>
      currentKeys.filter((key) => deletableRecordIdSet.has(String(key)))
    )
  }, [deletableRecordIdSet])

  const detailRows = useMemo<InvoiceDetailRow[]>(
    () =>
      records.flatMap((record) =>
        (record.result?.line_items ?? []).map((item: InvoiceLineItem, itemIndex: number) => ({
          recognitionRowKey: `${record.recognitionId}-${itemIndex}`,
          fileName: record.fileName,
          projectName: displayValue(item.project_name),
          unit: displayValue(item.unit),
          quantity: displayValue(item.quantity),
        }))
      ),
    [records]
  )

  const sellerSummaryRows = useMemo<SellerSummaryRow[]>(() => {
    const summaryMap = new Map<
      string,
      {
        sellerName: string
        invoiceCount: number
        totalTaxAmounts: Array<string | number | null | undefined>
        totalAmountWithTaxSmalls: Array<string | number | null | undefined>
        quantities: Array<string | number | null | undefined>
      }
    >()

    records.forEach((record) => {
      if (record.status !== 'success' || !record.result) return

      const sellerName = displayValue(record.result.seller_name)
      const summary = summaryMap.get(sellerName) ?? {
        sellerName,
        invoiceCount: 0,
        totalTaxAmounts: [],
        totalAmountWithTaxSmalls: [],
        quantities: [],
      }

      summary.invoiceCount += 1
      summary.totalTaxAmounts.push(record.result.total_tax_amount)
      summary.totalAmountWithTaxSmalls.push(record.result.total_amount_with_tax_small)
      summary.quantities.push(...(record.result.line_items ?? []).map((item) => item.quantity))
      summaryMap.set(sellerName, summary)
    })

    return Array.from(summaryMap.values()).map((summary) => ({
      recognitionRowKey: summary.sellerName,
      sellerName: summary.sellerName,
      invoiceCount: summary.invoiceCount,
      totalTaxAmount: sumMoney(summary.totalTaxAmounts),
      totalAmountWithTaxSmall: sumMoney(summary.totalAmountWithTaxSmalls),
      totalQuantity: summary.quantities.some(isPresentDecimal) ? sumQuantity(summary.quantities) : '-',
    }))
  }, [records])

  const itemQuantitySummaryRows = useMemo<ItemQuantitySummaryRow[]>(() => {
    const summaryMap = new Map<
      string,
      {
        sellerName: string
        projectName: string
        unit: string
        quantities: Array<string | number | null | undefined>
      }
    >()

    records.forEach((record) => {
      if (record.status !== 'success' || !record.result) return

      const sellerName = displayValue(record.result.seller_name)
      const lineItems = record.result.line_items ?? []
      lineItems.forEach((item) => {
        const projectName = displayValue(item.project_name)
        const unit = displayValue(item.unit)
        const summaryKey = `${sellerName}-${projectName}-${unit}`
        const summary = summaryMap.get(summaryKey) ?? {
          sellerName,
          projectName,
          unit,
          quantities: [],
        }

        summary.quantities.push(item.quantity)
        summaryMap.set(summaryKey, summary)
      })
    })

    return Array.from(summaryMap.entries()).map(([summaryKey, summary]) => ({
      recognitionRowKey: summaryKey,
      sellerName: summary.sellerName,
      projectName: summary.projectName,
      unit: summary.unit,
      totalQuantity: sumQuantity(summary.quantities),
    }))
  }, [records])

  const updateRecord = (
    recognitionId: string,
    patch: Partial<InvoiceRecognitionRecord>
  ) => {
    setUploadRecords((currentRecords) =>
      currentRecords.map((record) =>
        record.recognitionId === recognitionId ? { ...record, ...patch } : record
      )
    )
  }

  const removeDeletedRecords = (recordIds: string[]) => {
    const recordIdSet = new Set(recordIds)
    setSelectedRowKeys((currentKeys) =>
      currentKeys.filter((key) => !recordIdSet.has(String(key)))
    )
    setUploadRecords((currentRecords) =>
      currentRecords.filter((record) => !record.result?.id || !recordIdSet.has(record.result.id))
    )
  }

  const handleDeleteRecords = async (recordIds: string[]) => {
    const deletableIds = recordIds.filter((recordId) => deletableRecordIdSet.has(recordId))
    if (deletableIds.length === 0) {
      message.warning('请选择可删除的识别历史记录')
      return
    }

    setDeletingRecordIds(deletableIds)
    try {
      const response =
        deletableIds.length === 1
          ? await deleteInvoiceRecognitionRecord(deletableIds[0])
          : await deleteInvoiceRecognitionRecords(deletableIds)

      if (response.code !== 200) {
        message.error(response.message || '识别记录删除失败')
        return
      }

      removeDeletedRecords(deletableIds)
      const successCount = response.data?.success_count ?? deletableIds.length
      const failCount = response.data?.fail_count ?? 0
      if (failCount > 0) {
        message.warning(`已删除 ${successCount} 条，${failCount} 条删除失败`)
      } else {
        message.success(`已删除 ${successCount} 条识别历史`)
      }
      await refetch()
    } catch {
      message.error('识别记录删除失败，请稍后重试')
    } finally {
      setDeletingRecordIds([])
    }
  }

  const uploadProps: UploadProps = {
    name: 'file',
    multiple: true,
    accept: '.pdf,application/pdf',
    showUploadList: false,
    beforeUpload: async (file) => {
      if (file.type && file.type !== 'application/pdf') {
        message.error(`${file.name} 不是 PDF 文件`)
        return Upload.LIST_IGNORE
      }
      if (file.size > MAX_INVOICE_UPLOAD_SIZE_BYTES) {
        message.error(`${file.name} 超过 ${MAX_INVOICE_UPLOAD_SIZE_MB}MB，无法上传`)
        return Upload.LIST_IGNORE
      }

      const recognitionId = `${file.uid}-${Date.now()}`
      setPendingCount((count) => count + 1)
      setUploadRecords((currentRecords) => [
        ...currentRecords,
        {
          recognitionId,
          fileName: file.name,
          includeDetails,
          status: 'recognizing',
        },
      ])

      const formData = new FormData()
      formData.append('file', file)
      formData.append('include_details', includeDetails ? 'true' : 'false')

      try {
        const response = await recognizeInvoicePdf(formData)
        if (response.code !== 200) {
          updateRecord(recognitionId, {
            status: 'error',
            errorMessage: response.message || '发票识别失败',
          })
          return Upload.LIST_IGNORE
        }

        updateRecord(recognitionId, {
          recognitionId: response.data.id,
          fileName: response.data.file_name,
          includeDetails: response.data.include_details,
          status: 'success',
          result: response.data,
        })
      } catch {
        updateRecord(recognitionId, {
          status: 'error',
          errorMessage: '发票识别失败，请稍后重试',
        })
      } finally {
        setPendingCount((count) => Math.max(0, count - 1))
      }

      return Upload.LIST_IGNORE
    },
  }

  const summaryColumns = [
    {
      title: '文件',
      dataIndex: 'fileName',
      key: 'fileName',
      width: 120,
      ellipsis: true,
      render: (value: InvoiceSummaryRow['fileName']) => (
        <span className="inline-flex w-[120px] max-w-full min-w-0 items-center gap-2 text-[14px] text-[var(--color-charcoal)]">
          <FilePdfOutlined className="shrink-0 text-[var(--color-primary)]" />
          <span className="min-w-0 truncate" title={value}>
            {value}
          </span>
        </span>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 96,
      render: (value: InvoiceSummaryRow['status']) => statusTag(value),
    },
    {
      title: '发票号码',
      dataIndex: 'invoiceNumber',
      key: 'invoiceNumber',
      width: 190,
    },
    {
      title: '开票日期',
      dataIndex: 'invoiceDate',
      key: 'invoiceDate',
      width: 150,
    },
    {
      title: '销售方名称',
      dataIndex: 'sellerName',
      key: 'sellerName',
      width: 220,
    },
    {
      title: '税额合计',
      dataIndex: 'totalTaxAmount',
      key: 'totalTaxAmount',
      width: 130,
    },
    {
      title: '价税合计（小写）',
      dataIndex: 'totalAmountWithTaxSmall',
      key: 'totalAmountWithTaxSmall',
      width: 160,
    },
    {
      title: '错误信息',
      dataIndex: 'errorMessage',
      key: 'errorMessage',
      width: 88,
      ellipsis: true,
      render: (value: InvoiceSummaryRow['errorMessage']) => (
        <span className="block max-w-[88px] truncate" title={value}>
          {value}
        </span>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 100,
      render: (_: unknown, record: InvoiceSummaryRow) => {
        const recordDeleting = Boolean(record.recordId && deletingRecordIds.includes(record.recordId))
        const disabled = !record.canDelete || deleting || isFetching
        return (
          <Popconfirm
            title="确认删除该识别历史？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ danger: true, loading: recordDeleting }}
            disabled={disabled}
            onConfirm={() => record.recordId && handleDeleteRecords([record.recordId])}
          >
            <Button
              danger
              type="link"
              size="small"
              icon={<DeleteOutlined />}
              disabled={disabled}
              loading={recordDeleting}
            >
              删除
            </Button>
          </Popconfirm>
        )
      },
    },
  ]

  const detailColumns = [
    {
      title: '文件',
      dataIndex: 'fileName',
      key: 'fileName',
      width: 130,
      ellipsis: true,
      render: (value: InvoiceDetailRow['fileName']) => (
        <span className="block max-w-[130px] truncate" title={value}>
          {value}
        </span>
      ),
    },
    {
      title: '项目名称',
      dataIndex: 'projectName',
      key: 'projectName',
    },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 140,
    },
    {
      title: '数量',
      dataIndex: 'quantity',
      key: 'quantity',
      width: 160,
    },
  ]

  const sellerSummaryColumns = [
    {
      title: '销售方名称',
      dataIndex: 'sellerName',
      key: 'sellerName',
      width: 260,
    },
    {
      title: '发票数量',
      dataIndex: 'invoiceCount',
      key: 'invoiceCount',
      width: 110,
    },
    {
      title: '税额合计总和',
      dataIndex: 'totalTaxAmount',
      key: 'totalTaxAmount',
      width: 150,
    },
    {
      title: '价税合计总和（小写）',
      dataIndex: 'totalAmountWithTaxSmall',
      key: 'totalAmountWithTaxSmall',
      width: 190,
    },
    {
      title: '数量总和',
      dataIndex: 'totalQuantity',
      key: 'totalQuantity',
      width: 140,
    },
  ]

  const itemQuantitySummaryColumns = [
    {
      title: '销售方名称',
      dataIndex: 'sellerName',
      key: 'sellerName',
      width: 260,
    },
    {
      title: '项目名称',
      dataIndex: 'projectName',
      key: 'projectName',
    },
    {
      title: '单位',
      dataIndex: 'unit',
      key: 'unit',
      width: 140,
    },
    {
      title: '数量总和',
      dataIndex: 'totalQuantity',
      key: 'totalQuantity',
      width: 160,
    },
  ]

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-[22px] font-semibold text-[var(--color-charcoal)] mb-2">发票识别</h1>
        <p className="text-[14px] text-[var(--color-steel)]">
          批量上传电子发票 PDF，系统会提取发票号码、开票日期、销售方、税额合计和价税合计信息；可按需开启明细识别。
        </p>
      </div>

      <section className="bg-[var(--color-canvas)] border border-[var(--color-hairline)] rounded-[12px] p-6">
        <div className="mb-4 flex items-center justify-between gap-4 rounded-[8px] border border-[var(--color-hairline-soft)] bg-[var(--color-surface-soft)] px-4 py-3">
          <div>
            <div className="text-[14px] font-semibold text-[var(--color-charcoal)]">明细识别</div>
            <p className="mt-1 text-[13px] text-[var(--color-steel)]">
              开启后额外识别项目名称、单位和数量；关闭时只识别发票基础信息。
            </p>
          </div>
          <Switch
            checked={includeDetails}
            disabled={loading}
            checkedChildren="开"
            unCheckedChildren="关"
            onChange={(checked) => setIncludeDetails(checked)}
          />
        </div>

        <Dragger {...uploadProps} disabled={loading} className="invoice-upload">
          <p className="ant-upload-drag-icon">
            <InboxOutlined />
          </p>
          <p className="ant-upload-text">点击或拖拽 PDF 到此处识别</p>
          <p className="ant-upload-hint">
            支持批量上传电子发票 PDF，单个文件不超过 {MAX_INVOICE_UPLOAD_SIZE_MB}MB。
          </p>
        </Dragger>

        {uploadRecords.length > 0 && (
          <div className="mt-4 flex items-center justify-between rounded-[8px] border border-[var(--color-hairline-soft)] bg-[var(--color-surface-soft)] px-4 py-3">
            <div className="text-[14px] text-[var(--color-charcoal)]">
              本次已添加 {uploadRecords.length} 个文件
              {loading ? `，${pendingCount} 个正在识别` : ''}
            </div>
            <Button
              icon={<ReloadOutlined />}
              loading={loading}
              onClick={() => {
                setUploadRecords([])
                setPendingCount(0)
              }}
            >
              清空本次上传
            </Button>
          </div>
        )}
      </section>

      <section className="bg-[var(--color-canvas)] border border-[var(--color-hairline)] rounded-[12px] p-6">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <h2 className="text-[18px] font-semibold text-[var(--color-charcoal)]">识别结果</h2>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <Search
              allowClear
              className="w-full sm:w-[320px]"
              placeholder="搜索文件名、发票号码、销售方"
              enterButton="搜索"
              loading={isFetching}
              onSearch={(value) => {
                setSelectedRowKeys([])
                setSubmittedKeyword(value.trim())
                setCurrentPage(1)
              }}
            />
            {selectedRecordIds.length > 0 && (
              <Popconfirm
                title={`确认删除选中的 ${selectedRecordIds.length} 条识别历史？`}
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true, loading: deleting }}
                onConfirm={() => handleDeleteRecords(selectedRecordIds)}
              >
                <Button danger icon={<DeleteOutlined />} loading={deleting}>
                  批量删除 ({selectedRecordIds.length})
                </Button>
              </Popconfirm>
            )}
            <Button icon={<ReloadOutlined />} loading={isFetching} onClick={() => refetch()}>
              刷新历史
            </Button>
          </div>
        </div>

        <div>
          <h3 className="mb-3 text-[15px] font-semibold text-[var(--color-charcoal)]">销售方汇总</h3>
          <Table
            columns={sellerSummaryColumns}
            dataSource={sellerSummaryRows}
            rowKey="recognitionRowKey"
            pagination={false}
            bordered
            size="middle"
            scroll={{ x: 850 }}
            loading={isFetching}
            locale={{ emptyText: loading || isFetching ? '汇总计算中' : '暂无可汇总数据' }}
          />
        </div>

          {(includeDetails || detailRows.length > 0) && (
            <div className="mt-6">
              <h3 className="mb-3 text-[15px] font-semibold text-[var(--color-charcoal)]">项目数量汇总</h3>
              <Table
                columns={itemQuantitySummaryColumns}
                dataSource={itemQuantitySummaryRows}
                rowKey="recognitionRowKey"
                pagination={false}
                bordered
                size="middle"
                scroll={{ x: 860 }}
                loading={isFetching}
                locale={{ emptyText: loading || isFetching ? '数量汇总中' : '暂无明细数量' }}
              />
            </div>
          )}

          <div className="mt-6">
            <h3 className="mb-3 text-[15px] font-semibold text-[var(--color-charcoal)]">发票基础信息</h3>
            <Table
              columns={summaryColumns}
              dataSource={summaryRows}
              rowKey="recognitionRowKey"
              pagination={{
                current: currentPage,
                pageSize: DEFAULT_PAGE_SIZE,
                total: recordTotal,
                showSizeChanger: false,
                showTotal: (total) => `共 ${total} 条`,
                onChange: (page) => {
                  setSelectedRowKeys([])
                  setCurrentPage(page)
                },
              }}
              bordered
              size="middle"
              scroll={{ x: 1220 }}
              loading={isFetching}
              rowSelection={{
                selectedRowKeys,
                onChange: (keys) => setSelectedRowKeys(keys),
                getCheckboxProps: (record) => ({
                  disabled: !record.canDelete || deleting || isFetching,
                }),
              }}
            />
          </div>

          {(includeDetails || detailRows.length > 0) && (
            <div className="mt-6">
              <h3 className="mb-3 text-[15px] font-semibold text-[var(--color-charcoal)]">发票明细</h3>
              <Table
                columns={detailColumns}
                dataSource={detailRows}
                rowKey="recognitionRowKey"
                pagination={false}
                bordered
                size="middle"
                scroll={{ x: 730 }}
                loading={isFetching}
                locale={{ emptyText: loading || isFetching ? '明细识别中' : '未识别到明细' }}
              />
            </div>
          )}

          <Alert
            className="mt-4"
            type="info"
            showIcon
            title="识别结果请以原始发票为准，提交入账前需要人工核对。"
          />
      </section>
    </div>
  )
}
