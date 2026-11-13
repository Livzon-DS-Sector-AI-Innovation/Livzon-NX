'use client'

/**
 * 监护人名单 Excel 导入弹窗：上传 → 解析预览（子表勾选 + 行数 + 样例）
 * → 确认导入（整表替换）。交互参照 WorkCertificateImportModal；
 * 与证件导入不同，监护人名单以最新导入为准，替换前必须醒目确认。
 */

import { useState } from 'react'
import {
  Alert,
  App,
  Button,
  Modal,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { RcFile } from 'antd/es/upload'
import { ImportOutlined, InboxOutlined } from '@ant-design/icons'
import { importGuardianRoster, parseGuardianRosterImport } from '@/actions/safety'
import { GUARDIAN_ROSTER_PAGE_KEY } from '@/lib/work-permit-api'

const { Text } = Typography

const MAX_FILE_SIZE = 10 * 1024 * 1024

type GuardianSheetInfo = {
  sheet: string
  row_count: number
  workshops?: string[]
  default_selected?: boolean
  sample: {
    person_name?: string
    workshop?: string
    phone?: string
    position?: string
    score?: number
    exam_date?: string
  }[]
  errors: { row?: number; reason?: string }[]
}

type GuardianPreview = {
  sheets: GuardianSheetInfo[]
  duplicate_across_sheets?: number
  current_total?: number
  merged_total?: number
}

type GuardianResult = {
  replaced: number
  imported: number
  duplicates_merged?: number
  row_errors?: { sheet?: string; row?: number; reason?: string }[]
  archive_path?: string
}

interface Props {
  open: boolean
  onClose: () => void
  onImported: () => void
}

export default function GuardianRosterImportModal({
  open,
  onClose,
  onImported,
}: Props) {
  const { message } = App.useApp()
  const [file, setFile] = useState<RcFile | null>(null)
  const [parsing, setParsing] = useState(false)
  const [preview, setPreview] = useState<GuardianPreview | null>(null)
  const [selectedSheets, setSelectedSheets] = useState<string[]>([])
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<GuardianResult | null>(null)

  const resetState = () => {
    setFile(null)
    setParsing(false)
    setPreview(null)
    setSelectedSheets([])
    setImporting(false)
    setResult(null)
  }

  const handleFile = async (selected: RcFile) => {
    const ext = selected.name.toLowerCase()
    if (!ext.endsWith('.xlsx') && !ext.endsWith('.xls')) {
      message.error('仅支持 .xlsx / .xls 格式的名单表')
      return
    }
    if (selected.size > MAX_FILE_SIZE) {
      message.error('文件大小不能超过 10MB')
      return
    }
    setFile(selected)
    setResult(null)
    setPreview(null)
    setParsing(true)
    try {
      const res = await parseGuardianRosterImport(selected, GUARDIAN_ROSTER_PAGE_KEY)
      if (res.code === 200 && res.data) {
        const data = res.data as GuardianPreview
        setPreview(data)
        setSelectedSheets(
          data.sheets
            .filter((sheet) => sheet.row_count > 0 && sheet.default_selected)
            .map((sheet) => sheet.sheet)
        )
        if (data.sheets.every((sheet) => sheet.row_count === 0)) {
          message.warning('未从该文件解析出有效数据行，请检查表格格式')
        }
      } else {
        message.error(res.message || '解析失败')
        setFile(null)
      }
    } catch {
      message.error('解析失败，请稍后重试')
      setFile(null)
    } finally {
      setParsing(false)
    }
  }

  const handleImport = async () => {
    if (!file || selectedSheets.length === 0) return
    setImporting(true)
    try {
      const res = await importGuardianRoster(
        file,
        selectedSheets,
        GUARDIAN_ROSTER_PAGE_KEY
      )
      if (res.code === 200 && res.data) {
        setResult(res.data as GuardianResult)
        onImported()
      } else {
        message.error(res.message || '导入失败')
      }
    } catch {
      message.error('导入失败，请稍后重试')
    } finally {
      setImporting(false)
    }
  }

  const handleClose = () => {
    onClose()
    resetState()
  }

  const columns: ColumnsType<GuardianSheetInfo> = [
    { title: '子表', dataIndex: 'sheet', key: 'sheet', width: 180, ellipsis: true },
    { title: '有效行数', dataIndex: 'row_count', key: 'row_count', width: 85 },
    {
      title: '涉及车间',
      key: 'workshops',
      render: (_, record) => {
        const workshops = record.workshops ?? []
        if (workshops.length === 0) return <Text type="secondary">-</Text>
        const shown = workshops.slice(0, 3)
        return (
          <Space size={4} wrap>
            {shown.map((workshop) => (
              <Tag key={workshop}>{workshop}</Tag>
            ))}
            {workshops.length > shown.length && (
              <Text type="secondary" style={{ fontSize: 12 }}>
                +{workshops.length - shown.length}
              </Text>
            )}
          </Space>
        )
      },
    },
  ]

  const sheetTable = preview && (
    <Table
      size="small"
      columns={columns}
      dataSource={preview.sheets}
      rowKey="sheet"
      pagination={false}
      rowSelection={{
        selectedRowKeys: selectedSheets,
        onChange: (keys) => setSelectedSheets(keys as string[]),
        getCheckboxProps: (record) => ({ disabled: record.row_count === 0 }),
      }}
      expandable={{
        rowExpandable: (record) => record.sample.length > 0 || record.errors.length > 0,
        expandedRowRender: (record) => (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {record.sample.map((sample, idx) => (
              <Text key={idx} style={{ fontSize: 12 }}>
                {idx + 1}. {sample.person_name}｜{sample.workshop || '-'}｜
                {sample.phone || '-'}｜{sample.position || '-'}｜分数：
                {sample.score ?? '-'}｜考试日期：{sample.exam_date || '-'}
              </Text>
            ))}
            {record.errors.map((error, idx) => (
              <Text key={`e${idx}`} type="warning" style={{ fontSize: 12 }}>
                第 {error.row} 行：{error.reason}
              </Text>
            ))}
            <Text type="secondary" style={{ fontSize: 12 }}>
              展开行仅为前 3 行样例；同一人员在多个子表重复出现时会自动合并
              （保留最新一次考试），跨子表重复约 {preview.duplicate_across_sheets ?? 0} 处。
            </Text>
          </div>
        ),
      }}
    />
  )

  return (
    <Modal
      title={
        <span>
          <ImportOutlined style={{ marginRight: 8, color: '#5645D4' }} />
          导入监护人考试合格名单
        </span>
      }
      open={open}
      onCancel={handleClose}
      width={760}
      footer={
        result ? (
          <Button type="primary" onClick={handleClose}>
            完成
          </Button>
        ) : (
          <Space>
            <Button onClick={handleClose}>取消</Button>
            <Button
              type="primary"
              icon={<ImportOutlined />}
              loading={importing}
              disabled={!file || selectedSheets.length === 0 || parsing}
              onClick={handleImport}
            >
              导入选中子表并替换现有名单
            </Button>
          </Space>
        )
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {result ? (
          <>
            <Alert
              type={result.imported > 0 ? 'success' : 'warning'}
              showIcon
              message={
                result.imported > 0
                  ? `导入完成：本次写入 ${result.imported} 人，替换前原有 ${result.replaced} 人`
                  : '没有导入任何人员'
              }
              description={
                <Space direction="vertical" size={2}>
                  <Text style={{ fontSize: 12 }}>
                    文件内跨子表重复合并：{result.duplicates_merged ?? 0} 处
                  </Text>
                  {(result.row_errors ?? []).map((error, idx) => (
                    <Text key={idx} type="warning" style={{ fontSize: 12 }}>
                      {error.sheet} 第 {error.row} 行：{error.reason}
                    </Text>
                  ))}
                </Space>
              }
            />
            <Text type="secondary" style={{ fontSize: 12 }}>
              原始文件已存档（{result.archive_path || 'uploads/safety/guardian-import'}）。
              名单以最新导入为准，如需恢复请重新导入上一期名单。
            </Text>
          </>
        ) : (
          <>
            <Alert
              type="warning"
              showIcon
              message="导入将整表替换现有名单"
              description={`以最新导入为准：${
                preview
                  ? `确认后现有名单（${preview.current_total ?? 0} 人）将被本次解析结果全部替换`
                  : '确认后现有名单将被本次解析结果全部替换，解析后显示受影响人数'
              }，请仔细核对预览数据。`}
            />
            <Upload.Dragger
              accept=".xlsx,.xls"
              multiple={false}
              showUploadList={!!file && { showRemoveIcon: false }}
              fileList={file ? [{ uid: '-1', name: file.name, status: 'done' }] : []}
              beforeUpload={(selected) => {
                queueMicrotask(() => handleFile(selected))
                return false
              }}
              disabled={parsing || importing}
            >
              <p className="ant-upload-drag-icon">
                <InboxOutlined />
              </p>
              <p className="ant-upload-text">
                {parsing ? '正在解析子表结构…' : '点击或拖入监护人考试合格名单 Excel'}
              </p>
              <p className="ant-upload-hint" style={{ fontSize: 12 }}>
                自动识别表头（姓名/部门或车间/联系电话/岗位/分数/考试名称/考试时间），
                支持「汇总 + 按车间分表」多子表工作簿，单文件 ≤ 10MB
              </p>
            </Upload.Dragger>

            {preview && (
              <div>
                <Space style={{ marginBottom: 8 }}>
                  <Text strong>识别到 {preview.sheets.length} 个子表</Text>
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    合并去重后预计导入 {preview.merged_total ?? 0} 人，默认勾选汇总类子表
                  </Text>
                </Space>
                {sheetTable}
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}
