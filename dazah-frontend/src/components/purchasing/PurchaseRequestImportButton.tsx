'use client'

import { useState } from 'react'
import { Alert, App, Button, Modal, Space, Table, Typography, Upload } from 'antd'
import type { UploadProps } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { importPurchaseRequestTable } from '@/actions/purchasing'
import type {
  PurchaseRequestImportResult,
  PurchaseRequestImportSummary,
} from '@/types/purchasing'

const ACCEPTED_EXTENSIONS = '.xlsx,.xls,.csv'

type PurchaseRequestImportButtonProps = {
  onImported?: () => void
}

export function PurchaseRequestImportButton({
  onImported,
}: PurchaseRequestImportButtonProps) {
  const { message } = App.useApp()
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<PurchaseRequestImportResult | null>(null)

  const handleImport: UploadProps['customRequest'] = async ({ file, onSuccess }) => {
    const rawFile = file as File
    const lowerName = rawFile.name.toLowerCase()
    if (!ACCEPTED_EXTENSIONS.split(',').some((ext) => lowerName.endsWith(ext))) {
      message.error('请上传 xlsx、xls 或 csv 格式的表格文件')
      return
    }

    const formData = new FormData()
    formData.append('file', rawFile)
    setImporting(true)
    try {
      const response = await importPurchaseRequestTable(formData)
      if (response.code !== 200 || !response.data) {
        message.error(response.message || '采购申请导入失败')
        return
      }
      setResult(response.data)
      onSuccess?.(response.data)
      onImported?.()
    } catch {
      message.error('采购申请导入失败，请稍后重试')
    } finally {
      setImporting(false)
    }
  }

  const importedCount = result?.imported_requests?.length ?? 0
  const importedItems = result?.imported_requests?.reduce(
    (sum, item) => sum + item.items_count,
    0
  ) ?? 0
  const failedCount = result?.failed_rows?.length ?? 0

  const failedColumns = [
    { title: '工作表', dataIndex: 'sheet_name', key: 'sheet_name', width: 140 },
    {
      title: '行号',
      dataIndex: 'row',
      key: 'row',
      width: 80,
      render: (row: number | null | undefined) => row ?? '整表',
    },
    { title: '原因', dataIndex: 'message', key: 'message' },
  ]

  const importedColumns = [
    { title: '工作表', dataIndex: 'sheet_name', key: 'sheet_name', width: 140 },
    {
      title: '采购类型',
      dataIndex: 'category_label',
      key: 'category_label',
      width: 140,
      render: (label: string, record: PurchaseRequestImportSummary) =>
        record.category_source === 'inferred' ? `${label}（按字段推断）` : label,
    },
    { title: '申购部门', dataIndex: 'request_department', key: 'request_department', width: 150 },
    { title: '申请日期', dataIndex: 'request_date', key: 'request_date', width: 110 },
    { title: '明细条数', dataIndex: 'items_count', key: 'items_count', width: 90 },
  ]

  return (
    <>
      <Upload
        accept={ACCEPTED_EXTENSIONS}
        showUploadList={false}
        customRequest={handleImport}
        disabled={importing}
      >
        <Button icon={<UploadOutlined />} loading={importing}>
          导入
        </Button>
      </Upload>

      <Modal
        title="采购申请导入结果"
        open={result !== null}
        onCancel={() => setResult(null)}
        footer={null}
        width={720}
      >
        {result && (
          <div className="space-y-4">
            <Alert
              type={importedCount > 0 ? 'success' : 'warning'}
              showIcon
              message={
                importedCount > 0
                  ? `成功导入 ${importedCount} 份采购申请草稿，共 ${importedItems} 条明细`
                  : '没有成功导入任何采购申请'
              }
              description="导入的申请以草稿状态保存，请在工作台列表核对后提交审批。"
            />
            {importedCount > 0 && (
              <section>
                <Typography.Title level={5}>成功导入</Typography.Title>
                <Table
                  size="small"
                  rowKey="request_id"
                  columns={importedColumns}
                  dataSource={result.imported_requests ?? []}
                  pagination={false}
                />
              </section>
            )}
            {failedCount > 0 && (
              <section>
                <Typography.Title level={5}>失败明细（{failedCount} 条）</Typography.Title>
                <Table
                  size="small"
                  rowKey={(record, index) => `${record.sheet_name}-${record.row ?? 0}-${index}`}
                  columns={failedColumns}
                  dataSource={result.failed_rows ?? []}
                  pagination={false}
                />
              </section>
            )}
            <Space>
              <Button type="primary" onClick={() => setResult(null)}>
                知道了
              </Button>
            </Space>
          </div>
        )}
      </Modal>
    </>
  )
}
