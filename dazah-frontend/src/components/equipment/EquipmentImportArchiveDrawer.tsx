'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Drawer,
  Input,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import {
  ArrowLeftOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  HistoryOutlined,
} from '@ant-design/icons'
import type { ColumnsType } from 'antd/es/table'
import type { TdHTMLAttributes } from 'react'
import {
  deleteEquipmentImportArchive,
  getEquipmentImportArchive,
  getEquipmentImportArchives,
} from '@/actions/equipment'
import type {
  EquipmentImportArchive,
  EquipmentImportArchiveSummary,
} from '@/types/equipment'

interface EquipmentImportArchiveDrawerProps {
  open: boolean
  onClose: () => void
  /** 页面所在车间：默认按该车间过滤存档 */
  workshopCode?: string
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatSummary(item: EquipmentImportArchiveSummary): string {
  const summary = item.import_summary
  if (!summary) return '-'
  const parts = [
    `新建 ${summary.created ?? 0}`,
    `更新 ${summary.updated ?? 0}`,
    `失败 ${summary.failed ?? 0}`,
  ]
  return parts.join(' / ')
}

/** 0-based 合并区域 → 锚点跨度与被覆盖格的隐藏方式。

 * 被上方行合并覆盖的格用 rowSpan:0，被同行左侧合并覆盖的格用
 * colSpan:0（两者混用会导致表格列错位，浏览器把无效 colspan=0 当 1 列）。
 */
export function buildMergeMap(
  merges: EquipmentImportArchive['merges'],
): Map<string, { rowSpan?: number; colSpan?: number }> {
  const map = new Map<string, { rowSpan?: number; colSpan?: number }>()
  for (const merge of merges || []) {
    map.set(`${merge.s.r}:${merge.s.c}`, {
      rowSpan: merge.e.r - merge.s.r + 1,
      colSpan: merge.e.c - merge.s.c + 1,
    })
    for (let r = merge.s.r; r <= merge.e.r; r += 1) {
      for (let c = merge.s.c; c <= merge.e.c; c += 1) {
        if (r === merge.s.r && c === merge.s.c) continue
        map.set(`${r}:${c}`, r > merge.s.r ? { rowSpan: 0 } : { colSpan: 0 })
      }
    }
  }
  return map
}

function SnapshotTable({ archive }: { archive: EquipmentImportArchive }) {
  const { columns, dataSource } = useMemo(() => {
    const mergeMap = buildMergeMap(archive.merges)
    const maxCols = archive.col_count || archive.rows[0]?.length || 0
    const labels = Array.from({ length: maxCols }, (_, ci) => {
      let label = ''
      let n = ci
      do {
        label = String.fromCharCode(65 + (n % 26)) + label
        n = Math.floor(n / 26) - 1
      } while (n >= 0)
      return label
    })
    const builtColumns = labels.map((label, ci) => ({
      title: label,
      dataIndex: label,
      key: label,
      width: Math.max(archive.col_widths?.[ci] || 0, 72),
      onCell: (
        _record: Record<string, unknown>,
        rowIndex?: number,
      ): TdHTMLAttributes<HTMLTableCellElement> => {
        if (rowIndex === undefined) return {}
        return mergeMap.get(`${rowIndex}:${ci}`) ?? {}
      },
      render: (cell: unknown) =>
        cell === null || cell === undefined ? '' : String(cell),
    }))
    const builtDataSource = (archive.rows || []).map((row, ri) => {
      const item: Record<string, unknown> & { key: string } = { key: `r${ri}` }
      labels.forEach((label, ci) => {
        item[label] = row[ci] ?? ''
      })
      return item
    })
    return { columns: builtColumns, dataSource: builtDataSource }
  }, [archive])

  return (
    <Table
      columns={columns}
      dataSource={dataSource}
      rowKey="key"
      size="small"
      bordered
      scroll={{ x: 'max-content', y: 480 }}
      pagination={false}
    />
  )
}

export function EquipmentImportArchiveDrawer({
  open,
  onClose,
  workshopCode,
}: EquipmentImportArchiveDrawerProps) {
  const { message, modal } = App.useApp()
  const [items, setItems] = useState<EquipmentImportArchiveSummary[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState<EquipmentImportArchive | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const pageSize = 10

  const reload = useCallback(
    async (targetPage: number) => {
      setLoading(true)
      try {
        const response = await getEquipmentImportArchives(
          targetPage,
          pageSize,
          workshopCode,
        )
        if (response.code === 200) {
          setItems(response.data)
          setTotal(response.meta?.total ?? response.data.length)
          setPage(targetPage)
        } else {
          message.error(response.message || '加载上传历史失败')
        }
      } catch (error) {
        message.error((error as Error)?.message || '加载上传历史失败')
      } finally {
        setLoading(false)
      }
    },
    [message, workshopCode],
  )

  // 打开抽屉时加载第一页：通过 0ms 定时器把首次 setState 移出
  // effect 体，避免同步级联渲染
  useEffect(() => {
    if (!open) return
    const timer = setTimeout(() => {
      void reload(1)
    }, 0)
    return () => clearTimeout(timer)
  }, [open, reload])

  const handleClose = () => {
    setActive(null)
    onClose()
  }

  const openArchive = async (archiveId: string) => {
    setDetailLoading(true)
    try {
      const response = await getEquipmentImportArchive(archiveId)
      if (response.code === 200 && response.data) {
        setActive(response.data)
      } else {
        message.error(response.message || '打开存档失败')
      }
    } catch {
      message.error('打开存档失败')
    } finally {
      setDetailLoading(false)
    }
  }

  const removeArchive = (record: EquipmentImportArchiveSummary) => {
    modal.confirm({
      title: '确认删除存档',
      content: `仅删除「${record.file_name}」的上传快照，不影响已导入的台账数据。确定删除吗？`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteEquipmentImportArchive(record.id)
          message.success('存档已删除')
          if (active?.id === record.id) setActive(null)
          await reload(page)
        } catch (error) {
          message.error((error as Error)?.message || '删除失败')
        }
      },
    })
  }

  const columns: ColumnsType<EquipmentImportArchiveSummary> = [
    {
      title: '上传时间',
      dataIndex: 'created_at',
      width: 150,
      render: (v: string | null) => formatDateTime(v),
    },
    {
      title: '车间',
      dataIndex: 'workshop_code',
      width: 80,
    },
    {
      title: '文件名',
      dataIndex: 'file_name',
      ellipsis: true,
      render: (v: string) => <Typography.Text copyable={false}>{v}</Typography.Text>,
    },
    {
      title: '规模',
      width: 100,
      render: (_, record) => `${record.row_count} 行 × ${record.col_count} 列`,
    },
    {
      title: '导入结果',
      width: 180,
      render: (_, record) => (
        <Space size={4}>
          {formatSummary(record)}
          {record.import_summary?.failed ? (
            <Tag color="red">失败 {record.import_summary.failed}</Tag>
          ) : null}
        </Space>
      ),
    },
    {
      title: '上传人',
      dataIndex: 'created_by_name',
      width: 100,
      render: (v: string | null) => v || '-',
    },
    {
      title: '操作',
      width: 170,
      render: (_, record) => (
        <Space size={0}>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => void openArchive(record.id)}>
            查看
          </Button>
          <Button
            type="link"
            size="small"
            icon={<DownloadOutlined />}
            href={`/api/v1/equipment/equipments/import-archives/${record.id}/file`}
          >
            原件
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<DeleteOutlined />}
            onClick={() => removeArchive(record)}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <Drawer
      title={
        active ? (
          <Space>
            <Button
              type="text"
              icon={<ArrowLeftOutlined />}
              onClick={() => setActive(null)}
            />
            <span>{active.file_name}</span>
            <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
              {formatDateTime(active.created_at)} · {active.sheet_name}
            </Typography.Text>
          </Space>
        ) : (
          <Space>
            <HistoryOutlined />
            <span>台账上传历史</span>
            {workshopCode ? (
              <Typography.Text type="secondary" style={{ fontWeight: 400 }}>
                （{workshopCode} 车间）
              </Typography.Text>
            ) : null}
          </Space>
        )
      }
      open={open}
      onClose={handleClose}
      width="80%"
      destroyOnClose
    >
      {active ? (
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Input.TextArea
            value={`上传时间 ${formatDateTime(active.created_at)} · 上传人 ${active.created_by_name || '-'} · 导入结果 ${formatSummary(active)}`}
            autoSize
            readOnly
            style={{ background: '#fafaf8' }}
          />
          <SnapshotTable archive={active} />
        </Space>
      ) : (
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          size="small"
          loading={loading || detailLoading}
          pagination={{
            current: page,
            pageSize,
            total,
            showTotal: (t) => `共 ${t} 次上传`,
            onChange: (p) => void reload(p),
          }}
        />
      )}
    </Drawer>
  )
}
