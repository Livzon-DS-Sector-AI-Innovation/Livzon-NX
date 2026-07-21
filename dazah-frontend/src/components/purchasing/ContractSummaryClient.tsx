'use client'

import { useMemo, useRef, useState } from 'react'
import {
  Alert,
  App,
  Button,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Pagination,
  Skeleton,
  Space,
  Tag,
} from 'antd'
import {
  DownloadOutlined,
  EyeOutlined,
  FileWordOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import {
  fetchContractFile,
  fetchContractRecord,
  fetchContractRecords,
} from '@/lib/api/purchasing'
import type { ContractCategory, ContractRecordResponse } from '@/types/purchasing'

const { Search } = Input
const DEFAULT_PAGE_SIZE = 12

const contractCategoryLabels: Record<ContractCategory, string> = {
  'fixed-assets': '固定资产',
  consumables: '耗材',
  hardware: '五金',
  'raw-materials': '原材料',
}

type ContractSummaryClientProps = {
  initialRecords: ContractRecordResponse[]
  initialTotal: number
  initialLoadFailed?: boolean
}

function formatDate(value: string | null | undefined) {
  if (!value) return '-'
  return value
}

function formatFileSize(value: number | null | undefined) {
  if (!value) return '-'
  if (value < 1024) return `${value} B`
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

export function ContractSummaryClient({
  initialRecords,
  initialTotal,
  initialLoadFailed = false,
}: ContractSummaryClientProps) {
  const { message } = App.useApp()
  const previewRef = useRef<HTMLDivElement>(null)
  const [records, setRecords] = useState(initialRecords)
  const [total, setTotal] = useState(initialTotal)
  const [page, setPage] = useState(1)
  const [submittedKeyword, setSubmittedKeyword] = useState('')
  const [loading, setLoading] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [detail, setDetail] = useState<ContractRecordResponse | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [currentFile, setCurrentFile] = useState<{ blob: Blob; filename: string } | null>(null)

  const summaryText = useMemo(() => {
    if (submittedKeyword) return `搜索：${submittedKeyword}`
    return '全部合同'
  }, [submittedKeyword])

  const loadRecords = async (nextPage = page, keyword = submittedKeyword) => {
    setLoading(true)
    try {
      const response = await fetchContractRecords({
        keyword: keyword || undefined,
        page: nextPage,
        page_size: DEFAULT_PAGE_SIZE,
      })
      setRecords(response.data ?? [])
      const nextTotal = Number(response.meta?.total ?? response.data?.length ?? 0)
      setTotal(Number.isFinite(nextTotal) ? nextTotal : 0)
      setPage(nextPage)
      setSubmittedKeyword(keyword)
    } catch {
      message.error('合同汇总加载失败')
    } finally {
      setLoading(false)
    }
  }

  const renderPreview = async (contractId: string) => {
    setPreviewLoading(true)
    setPreviewError(null)
    setCurrentFile(null)
    if (previewRef.current) {
      previewRef.current.innerHTML = ''
    }

    try {
      const file = await fetchContractFile(contractId)
      setCurrentFile(file)
      const buffer = await file.blob.arrayBuffer()
      const docx = await import('docx-preview')
      if (!previewRef.current) return
      previewRef.current.innerHTML = ''
      await docx.renderAsync(buffer, previewRef.current, undefined, {
        className: 'contract-docx-preview',
        inWrapper: true,
        ignoreWidth: false,
        ignoreHeight: false,
        ignoreFonts: false,
        breakPages: true,
        renderHeaders: true,
        renderFooters: true,
      })
    } catch {
      setPreviewError('合同预览加载失败，可下载后查看。')
    } finally {
      setPreviewLoading(false)
    }
  }

  const openDetail = async (record: ContractRecordResponse) => {
    setDrawerOpen(true)
    setDetail(record)
    setDetailLoading(true)
    try {
      const response = await fetchContractRecord(record.id)
      setDetail(response.data)
      await renderPreview(record.id)
    } catch {
      message.error('合同详情加载失败')
      setPreviewError('合同详情加载失败。')
    } finally {
      setDetailLoading(false)
    }
  }

  const handleDownload = async () => {
    if (!detail) return
    try {
      const file = currentFile ?? (await fetchContractFile(detail.id))
      setCurrentFile(file)
      downloadBlob(file.blob, file.filename || detail.filename)
    } catch {
      message.error('合同下载失败')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="mb-2 text-[13px] text-[var(--color-stone)]">
            采购管理 / 合同汇总
          </p>
          <h1 className="mb-2 text-[22px] font-semibold text-[var(--color-charcoal)]">
            合同汇总
          </h1>
          <Space size="small" wrap>
            <Tag color="processing">{summaryText}</Tag>
            <Tag color="success">合同生成记录</Tag>
            <Tag>{total} 份合同</Tag>
          </Space>
        </div>
        <Space wrap>
          <Button
            icon={<ReloadOutlined />}
            loading={loading}
            onClick={() => loadRecords(page)}
          >
            刷新
          </Button>
        </Space>
      </div>

      {initialLoadFailed && (
        <Alert
          type="warning"
          showIcon
          message="合同汇总首屏加载失败"
          description="已显示空列表，可点击刷新或搜索重新加载。"
        />
      )}

      <section className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)]">
        <div className="flex flex-col gap-3 border-b border-[var(--color-hairline)] bg-[var(--color-surface-soft)] px-4 py-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-[18px] font-semibold text-[var(--color-charcoal)]">
              合同列表
            </h2>
            <p className="mt-1 text-[13px] text-[var(--color-steel)]">
              显示由合同生成模块保存的采购合同。
            </p>
          </div>
          <Search
            allowClear
            className="w-full lg:w-[360px]"
            enterButton={
              <span className="inline-flex items-center gap-1">
                <SearchOutlined />
                搜索
              </span>
            }
            loading={loading}
            placeholder="搜索合同标题、编号或卖方"
            onSearch={(value) => {
              void loadRecords(1, value.trim())
            }}
          />
        </div>

        <div className="p-4">
          {loading ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }).map((_, index) => (
                <div
                  key={index}
                  className="rounded-[12px] border border-[var(--color-hairline-soft)] p-4"
                >
                  <Skeleton active paragraph={{ rows: 3 }} title />
                </div>
              ))}
            </div>
          ) : records.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {records.map((record) => (
                <article
                  key={record.id}
                  className="flex min-h-[190px] flex-col justify-between rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-canvas)] p-4"
                >
                  <div>
                    <div className="mb-3 flex items-start justify-between gap-3">
                      <FileWordOutlined className="mt-1 shrink-0 text-[20px] text-[var(--color-primary)]" />
                      <Tag className="shrink-0" color="purple">
                        {contractCategoryLabels[record.category] ?? record.category}
                      </Tag>
                    </div>
                    <h3
                      className="line-clamp-2 text-[16px] font-semibold leading-6 text-[var(--color-charcoal)]"
                      title={record.title}
                    >
                      {record.title}
                    </h3>
                    <dl className="mt-4 grid gap-2 text-[13px]">
                      <div className="flex gap-2">
                        <dt className="shrink-0 text-[var(--color-stone)]">编号</dt>
                        <dd className="min-w-0 truncate text-[var(--color-charcoal)]">
                          {record.contract_number}
                        </dd>
                      </div>
                      <div className="flex gap-2">
                        <dt className="shrink-0 text-[var(--color-stone)]">卖方</dt>
                        <dd className="min-w-0 truncate text-[var(--color-charcoal)]">
                          {record.seller_name || '-'}
                        </dd>
                      </div>
                      <div className="flex gap-2">
                        <dt className="shrink-0 text-[var(--color-stone)]">日期</dt>
                        <dd className="text-[var(--color-charcoal)]">
                          {formatDate(record.contract_date)}
                        </dd>
                      </div>
                    </dl>
                  </div>
                  <div className="mt-4 flex items-center justify-between gap-3 border-t border-[var(--color-hairline-soft)] pt-3">
                    <span className="text-[12px] text-[var(--color-stone)]">
                      {formatFileSize(record.file_size)}
                    </span>
                    <Button
                      type="primary"
                      icon={<EyeOutlined />}
                      onClick={() => openDetail(record)}
                    >
                      详情
                    </Button>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <Empty
              image={Empty.PRESENTED_IMAGE_SIMPLE}
              description={submittedKeyword ? '未找到匹配的合同' : '暂无合同记录'}
            />
          )}

          <div className="mt-5 flex justify-end">
            <Pagination
              current={page}
              pageSize={DEFAULT_PAGE_SIZE}
              total={total}
              showSizeChanger={false}
              showTotal={(value) => `共 ${value} 份`}
              onChange={(nextPage) => loadRecords(nextPage)}
            />
          </div>
        </div>
      </section>

      <Drawer
        destroyOnClose
        size={920}
        title={detail?.title || '合同详情'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          <Button
            type="primary"
            icon={<DownloadOutlined />}
            disabled={!detail}
            onClick={handleDownload}
          >
            下载合同
          </Button>
        }
      >
        {detailLoading && !detail ? (
          <Skeleton active paragraph={{ rows: 5 }} />
        ) : detail ? (
          <div className="space-y-4">
            <Descriptions
              bordered
              size="small"
              column={2}
              items={[
                { key: 'category', label: '合同分类', children: contractCategoryLabels[detail.category] ?? detail.category },
                { key: 'number', label: '合同编号', children: detail.contract_number },
                { key: 'date', label: '签订日期', children: formatDate(detail.contract_date) },
                { key: 'seller', label: '卖方名称', children: detail.seller_name || '-' },
                { key: 'filename', label: '文件名', children: detail.filename },
                { key: 'size', label: '文件大小', children: formatFileSize(detail.file_size) },
              ]}
            />

            <div className="rounded-[12px] border border-[var(--color-hairline)] bg-[var(--color-surface-soft)]">
              <div className="flex items-center justify-between border-b border-[var(--color-hairline)] px-4 py-3">
                <h3 className="text-[15px] font-semibold text-[var(--color-charcoal)]">
                  合同预览
                </h3>
                {previewLoading && (
                  <span className="text-[13px] text-[var(--color-steel)]">加载中</span>
                )}
              </div>
              {previewError && (
                <Alert
                  className="m-4"
                  type="warning"
                  showIcon
                  message={previewError}
                />
              )}
              <div className="max-h-[68vh] overflow-auto p-4">
                {previewLoading && (
                  <div className="rounded-[8px] bg-[var(--color-canvas)] p-6">
                    <Skeleton active paragraph={{ rows: 8 }} />
                  </div>
                )}
                <div
                  ref={previewRef}
                  className="contract-docx-preview-container"
                />
              </div>
            </div>
          </div>
        ) : (
          <Empty description="请选择合同" />
        )}
      </Drawer>

      <style jsx global>{`
        .contract-docx-preview-container {
          max-width: 100%;
        }
        .contract-docx-preview {
          background: #ffffff;
          margin: 0 auto;
          min-height: 297mm;
          padding: 36px 48px;
          width: 210mm;
          box-shadow: 0 1px 3px rgba(15, 15, 15, 0.12);
        }
        .contract-docx-preview table {
          border-collapse: collapse;
          width: 100%;
        }
        .contract-docx-preview td,
        .contract-docx-preview th {
          border: 1px solid #333333;
          padding: 4px 8px;
        }
      `}</style>
    </div>
  )
}
