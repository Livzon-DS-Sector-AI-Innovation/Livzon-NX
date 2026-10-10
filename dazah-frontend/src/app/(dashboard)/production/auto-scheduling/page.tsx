'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import dayjs, { type Dayjs } from 'dayjs'
import {
  CalendarOutlined,
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  FileSearchOutlined,
  ImportOutlined,
  PlusOutlined,
  RocketOutlined,
  StopOutlined,
} from '@ant-design/icons'
import Alert from '@/components/shared/PlatformNotice'
import {
  deleteScheduleDraftRecord,
  downloadScheduleDraftRecordFile,
  exportScheduleDraft,
  generateScheduleDraft,
  getScheduleDraftRecord,
  getScheduleDraftRecords,
} from '@/actions/production'
import { downloadBytes } from '@/lib/download'
import {
  PRODUCTION_PAGE_KEYS,
  useProductionPermissions,
} from '@/components/production/useProductionPermissions'
import { alignedPeriodHint, isPeriodOverlong } from './aligned-period'
import type {
  ScheduleDraftDay,
  ScheduleDraftParams,
  ScheduleDraftRecord,
  ScheduleDraftResult,
  ScheduleTankBlock,
} from '@/types/production'

const { Title, Text } = Typography
const { RangePicker } = DatePicker

const FA_TANKS = ['302A', '303A', '304A']
const WEEKDAYS = ['日', '一', '二', '三', '四', '五', '六']

/** 排产校验/约束卡片所在页，提示文案引导跳转 */
const SCHEDULING_PAGE_URL = '/production/scheduling'

function fmtDate(value?: string | null) {
  return value ? value.slice(5).replace('-', '/') : '—'
}

function weekday(value: string) {
  return `周${WEEKDAYS[dayjs(value).day()]}`
}

export default function AutoSchedulingPage() {
  const { authorizationKey, canAccess, canOperate, canExport } =
    useProductionPermissions(PRODUCTION_PAGE_KEYS.autoScheduling)
  if (!canAccess) {
    return (
      <div className="p-6">
        <Alert
          type="warning"
          showIcon
          title="暂无自动排产页面权限，请联系管理员配置页面权限。"
        />
      </div>
    )
  }
  return (
    <AutoSchedulingContent key={authorizationKey} canOperate={canOperate} canExport={canExport} />
  )
}

function AutoSchedulingContent({
  canOperate,
  canExport,
}: {
  canOperate: boolean
  canExport: boolean
}) {
  const { message } = App.useApp()
  // 周期缺省 = 下一扎帐周期（后端解析）；生成后回显实际周期
  const [period, setPeriod] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [batchStartNo, setBatchStartNo] = useState<number | null>(null)
  const [skipDates, setSkipDates] = useState<string[]>([])
  const [pendingSkipDate, setPendingSkipDate] = useState<Dayjs | null>(null)
  const [tankBlocks, setTankBlocks] = useState<ScheduleTankBlock[]>([])
  const [blockTank, setBlockTank] = useState<string>('302A')
  const [blockRange, setBlockRange] = useState<[Dayjs | null, Dayjs | null] | null>(null)
  const [result, setResult] = useState<ScheduleDraftResult | null>(null)
  const [generating, setGenerating] = useState(false)
  const [exporting, setExporting] = useState(false)
  // 生成历史：同参数去重的工作台记录（仅过程留痕，不生效）
  const [records, setRecords] = useState<ScheduleDraftRecord[]>([])
  const [recordsLoading, setRecordsLoading] = useState(false)
  const [viewingRecord, setViewingRecord] = useState<ScheduleDraftRecord | null>(null)

  const params: ScheduleDraftParams = useMemo(
    () => ({
      period_start: period?.[0] ? period[0].format('YYYY-MM-DD') : null,
      period_end: period?.[1] ? period[1].format('YYYY-MM-DD') : null,
      batch_start_no: batchStartNo,
      skip_dates: skipDates,
      tank_blocks: tankBlocks,
    }),
    [period, batchStartNo, skipDates, tankBlocks],
  )

  const reloadRecords = useCallback(async () => {
    setRecordsLoading(true)
    try {
      const res = await getScheduleDraftRecords(1, 20)
      if (res.code === 200) setRecords(res.data || [])
    } catch {
      // 历史加载失败不阻断生成流程，可手动刷新
    } finally {
      setRecordsLoading(false)
    }
  }, [])

  useEffect(() => {
    // 延迟一拍再加载，避免 effect 内同步 setState 引发级联渲染
    const timer = setTimeout(() => void reloadRecords(), 0)
    return () => clearTimeout(timer)
  }, [reloadRecords])

  const generate = useCallback(
    async (override?: Partial<ScheduleDraftParams>) => {
      if (!canOperate) return
      setGenerating(true)
      try {
        const res = await generateScheduleDraft({ ...params, ...override })
        if (res.code === 200) {
          setResult(res.data)
          void reloadRecords()
          const warn = res.data?.validation?.summary?.warn ?? 0
          if (warn > 0) {
            message.warning(`草稿已生成，存在 ${warn} 个需人工确认的问题`, 5)
          }
        } else {
          message.error(res.message || '生成失败', 6)
        }
      } catch {
        message.error('生成请求失败', 6)
      } finally {
        setGenerating(false)
      }
    },
    [canOperate, message, params, reloadRecords],
  )

  const toggleSkip = useCallback(
    async (date: string) => {
      const next = skipDates.includes(date)
        ? skipDates.filter((d) => d !== date)
        : [...skipDates, date]
      setSkipDates(next)
      await generate({ skip_dates: next })
    },
    [generate, skipDates],
  )

  const download = useCallback(async () => {
    if (!canExport) return
    setExporting(true)
    try {
      const file = await exportScheduleDraft(params)
      downloadBytes(file.bytes, file.filename)
      void reloadRecords()
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导出失败', 6)
    } finally {
      setExporting(false)
    }
  }, [canExport, message, params, reloadRecords])

  const addTankBlock = useCallback(() => {
    if (!blockTank || !blockRange?.[0] || !blockRange?.[1]) {
      message.warning('请选择罐号和占用起止日期')
      return
    }
    setTankBlocks((prev) => [
      ...prev,
      {
        tank_no: blockTank,
        from_date: blockRange[0]!.format('YYYY-MM-DD'),
        to_date: blockRange[1]!.format('YYYY-MM-DD'),
      },
    ])
    setBlockRange(null)
  }, [blockRange, blockTank, message])

  /** 从历史记录载入参数，便于在旧方案基础上继续调整 */
  const loadRecordParams = useCallback((record: ScheduleDraftRecord) => {
    const params = record.params
    if (params?.period_start && params?.period_end) {
      setPeriod([dayjs(params.period_start), dayjs(params.period_end)])
    }
    setBatchStartNo(params?.batch_start_no ?? null)
    setSkipDates(params?.skip_dates ?? [])
    setTankBlocks(
      (params?.tank_blocks ?? []).map((b) => ({
        tank_no: b.tank_no,
        from_date: b.from_date,
        to_date: b.to_date,
      })),
    )
    message.success('已载入该方案的生成参数')
  }, [message])

  const openRecordDetail = useCallback(
    async (id: string) => {
      try {
        const res = await getScheduleDraftRecord(id)
        if (res.code === 200) {
          setViewingRecord(res.data)
        } else {
          message.error(res.message || '加载草稿详情失败', 5)
        }
      } catch {
        message.error('加载草稿详情失败', 5)
      }
    },
    [message],
  )

  const removeRecord = useCallback(
    async (id: string) => {
      try {
        const res = await deleteScheduleDraftRecord(id)
        if (res.code === 200) {
          message.success('草稿记录已删除')
          await reloadRecords()
        } else {
          message.error(res.message || '删除失败', 5)
        }
      } catch {
        message.error('删除请求失败', 5)
      }
    },
    [message, reloadRecords],
  )

  const downloadRecordFile = useCallback(
    async (record: ScheduleDraftRecord) => {
      try {
        const file = await downloadScheduleDraftRecordFile(record.id)
        if (!file) {
          message.info('该方案只预览过、未导出过文件；可载入参数后重新导出')
          return
        }
        downloadBytes(file.bytes, file.filename)
      } catch (error) {
        message.error(error instanceof Error ? error.message : '下载失败', 5)
      }
    },
    [message],
  )

  const recordColumns: ColumnsType<ScheduleDraftRecord> = [
    {
      title: '时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 160,
      render: (v?: string) => (v ? new Date(v).toLocaleString() : '—'),
    },
    {
      title: '操作人',
      dataIndex: 'created_by_name',
      key: 'created_by_name',
      width: 100,
      render: (v?: string | null) => v || '—',
    },
    {
      title: '周期',
      key: 'period',
      width: 190,
      render: (_: unknown, record: ScheduleDraftRecord) =>
        `${record.summary?.period?.start ?? '—'}～${record.summary?.period?.end ?? '—'}`,
    },
    {
      title: '方案',
      key: 'plan',
      render: (_: unknown, record: ScheduleDraftRecord) => (
        <Space size={6} wrap>
          <Tag style={{ marginRight: 0 }}>
            移种 {record.summary?.transfer_count ?? 0}
          </Tag>
          {(record.params?.skip_dates?.length ?? 0) > 0 && (
            <Tag color="orange" style={{ marginRight: 0 }}>
              跳过 {record.params!.skip_dates!.length} 天
            </Tag>
          )}
          {(record.params?.tank_blocks?.length ?? 0) > 0 && (
            <Tag color="purple" style={{ marginRight: 0 }}>
              占罐 {record.params!.tank_blocks!.length} 段
            </Tag>
          )}
          {record.downloaded_at ? (
            <Tag color="green" style={{ marginRight: 0 }}>
              已导出
            </Tag>
          ) : (
            <Tag style={{ marginRight: 0 }}>仅预览</Tag>
          )}
        </Space>
      ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 260,
      render: (_: unknown, record: ScheduleDraftRecord) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<EyeOutlined />}
            onClick={() => void openRecordDetail(record.id)}
          >
            查看
          </Button>
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => void downloadRecordFile(record)}
          >
            下载
          </Button>
          <Button
            size="small"
            icon={<ImportOutlined />}
            onClick={() => loadRecordParams(record)}
          >
            载入参数
          </Button>
          {canOperate && (
            <Popconfirm
              title="删除该草稿记录？"
              description="仅删除工作台历史，不影响已上传的排产存档。"
              okText="删除"
              cancelText="取消"
              okButtonProps={{ danger: true }}
              onConfirm={() => void removeRecord(record.id)}
            >
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  const summary = result?.summary
  const warnCount = result?.validation?.summary?.warn ?? 0
  const periodHint = alignedPeriodHint(period)
  const periodOverlong = isPeriodOverlong(period)

  const dayColumns: ColumnsType<ScheduleDraftDay> = [
    {
      title: '日期',
      dataIndex: 'date',
      key: 'date',
      width: 110,
      render: (v: string) => `${fmtDate(v)}（${weekday(v)}）`,
    },
    {
      title: '种子接种',
      key: 'seed',
      width: 150,
      render: (_: unknown, record: ScheduleDraftDay) =>
        record.seed_batch ? (
          <Space size={4}>
            {record.seed_tank ? (
              <Tag style={{ marginRight: 0 }}>{record.seed_tank}</Tag>
            ) : null}
            <span>{record.seed_batch}</span>
          </Space>
        ) : (
          <Text type="secondary">{record.seed_note || '—'}</Text>
        ),
    },
    {
      title: '移种进罐',
      key: 'transfer',
      width: 150,
      render: (_: unknown, record: ScheduleDraftDay) =>
        record.transfer ? (
          <Space size={4}>
            <Tag style={{ marginRight: 0 }}>{record.transfer.tank_no}</Tag>
            <span>{record.transfer.batch_no}</span>
          </Space>
        ) : (
          <Text type="secondary">{record.transfer_note || '—'}</Text>
        ),
    },
    {
      title: '放罐',
      key: 'dump',
      width: 180,
      render: (_: unknown, record: ScheduleDraftDay) =>
        (record.dumps ?? []).length > 0 ? (
          <Space size={4} wrap>
            {(record.dumps ?? []).map((d) => (
              <Tag
                key={d.batch_no}
                color={record.dump_inflight ? 'purple' : 'green'}
                style={{ marginRight: 0 }}
              >
                {d.batch_no}·{d.tank_no}
                {record.dump_inflight ? '（上期在制）' : ''}
              </Tag>
            ))}
          </Space>
        ) : (
          <Text type="secondary">—</Text>
        ),
    },
    {
      title: '操作',
      key: 'actions',
      width: 110,
      render: (_: unknown, record: ScheduleDraftDay) => {
        const skipped = skipDates.includes(record.date)
        return canOperate ? (
          <Button
            size="small"
            danger={!skipped}
            icon={skipped ? undefined : <StopOutlined />}
            onClick={() => void toggleSkip(record.date)}
          >
            {skipped ? '恢复进罐' : '跳过该日'}
          </Button>
        ) : null
      },
    },
  ]

  return (
    <div className="p-6">
      <div className="mb-6">
        <Title level={4} style={{ margin: 0 }}>
          <RocketOutlined className="mr-2" />
          自动排产（FA）
        </Title>
        <Text type="secondary">
          按上月排产无缝接续生成下一周期草稿；改指令即时重算，下载 Excel
          修改后到「排产计划」页上传生效（草稿本身不落库、不生效）
        </Text>
      </div>

      {/* 参数区 */}
      <Card className="mb-4" size="small" title="生成参数" styles={{ body: { padding: 14 } }}>
        <Space size={24} wrap>
          <span>
            目标周期：
            <RangePicker
              className="ml-1"
              value={period}
              onChange={(v) => setPeriod(v as [Dayjs | null, Dayjs] | null)}
              placeholder={['自动（下一周期）', '自动']}
            />
          </span>
          <span>
            起始批号：
            <InputNumber
              className="ml-1"
              min={1}
              max={999999}
              placeholder="自动续号"
              value={batchStartNo}
              onChange={(v) => setBatchStartNo(v)}
            />
          </span>
        </Space>
        {periodHint && (
          <div className="mt-2">
            <Text type={periodOverlong ? 'danger' : 'secondary'}>
              {periodHint}
            </Text>
          </div>
        )}
        <div className="mt-3">
          <Space size={8} wrap>
            <span>跳过进罐日：</span>
            <DatePicker
              value={pendingSkipDate}
              onChange={(v) => setPendingSkipDate(v)}
              placeholder="选择日期"
            />
            <Button
              size="small"
              icon={<PlusOutlined />}
              disabled={!pendingSkipDate}
              onClick={() => {
                if (pendingSkipDate) {
                  const value = pendingSkipDate.format('YYYY-MM-DD')
                  if (!skipDates.includes(value)) {
                    setSkipDates((prev) => [...prev, value].sort())
                  }
                  setPendingSkipDate(null)
                }
              }}
            >
              添加
            </Button>
            {skipDates.map((d) => (
              <Tag
                key={d}
                closable
                onClose={() => setSkipDates((prev) => prev.filter((x) => x !== d))}
              >
                {fmtDate(d)}
              </Tag>
            ))}
          </Space>
        </div>
        <div className="mt-3">
          <Space size={8} wrap>
            <span>罐占用窗口：</span>
            <Select
              value={blockTank}
              onChange={setBlockTank}
              options={FA_TANKS.map((t) => ({ value: t, label: t }))}
              style={{ width: 90 }}
            />
            <RangePicker
              value={blockRange}
              onChange={(v) => setBlockRange(v as [Dayjs | null, Dayjs] | null)}
              placeholder={['占用起', '占用止']}
            />
            <Button size="small" icon={<PlusOutlined />} onClick={addTankBlock}>
              添加
            </Button>
            {tankBlocks.map((b, i) => (
              <Tag
                key={`${b.tank_no}-${b.from_date}-${i}`}
                closable
                onClose={() =>
                  setTankBlocks((prev) => prev.filter((_, idx) => idx !== i))
                }
              >
                {b.tank_no} {fmtDate(b.from_date)}~{fmtDate(b.to_date)}
              </Tag>
            ))}
          </Space>
        </div>
        <div className="mt-3">
          <Space>
            <Button
              type="primary"
              icon={<RocketOutlined />}
              loading={generating}
              disabled={!canOperate || periodOverlong}
              onClick={() => void generate()}
            >
              生成草稿
            </Button>
            <Button
              icon={<DownloadOutlined />}
              loading={exporting}
              disabled={!canExport || !result}
              onClick={() => void download()}
            >
              下载 Excel
            </Button>
            {!canOperate && (
              <Text type="secondary">无操作权限，仅可查看</Text>
            )}
          </Space>
        </div>
        <Alert
          type="info"
          showIcon
          className="mt-3"
          title="看板上进行中的检修（含预计恢复日期）会自动作为罐占用窗口带入；未填恢复日期的检修按整期不排，请在看板补填。"
        />
      </Card>

      {/* 结果区 */}
      {result ? (
        <>
          <Card
            className="mb-4"
            size="small"
            title={
              <Space size={8}>
                <span>生成结果</span>
                <Tag icon={<CalendarOutlined />} style={{ fontWeight: 400 }}>
                  {summary?.period?.start} ～ {summary?.period?.end}
                </Tag>
                <Tag color={warnCount > 0 ? 'orange' : 'green'} style={{ fontWeight: 400 }}>
                  校验：需确认 {warnCount} 项 / 提示{' '}
                  {result.validation?.summary?.info ?? 0} 项
                </Tag>
              </Space>
            }
            styles={{ body: { padding: 14 } }}
          >
            <Space size={24} wrap>
              <span>
                移种 <Text strong>{summary?.transfer_count ?? 0}</Text> 批
              </span>
              <span>
                放罐 <Text strong>{summary?.dump_count ?? 0}</Text> 批
                {summary?.dump_target ? (
                  <Text type="secondary">（月目标 {summary.dump_target}）</Text>
                ) : null}
              </span>
              <span>
                上期在制接续{' '}
                <Text strong>{summary?.inflight_batches?.length ?? 0}</Text> 批
              </span>
              <span>
                跳过 <Text strong>{skipDates.length}</Text> 天
              </span>
              <span>
                空拍 <Text strong>{summary?.idle_tank_days ?? 0}</Text> 罐·天
              </span>
            </Space>
            {(summary?.tank_blocks?.length ?? 0) > 0 && (
              <div className="mt-2">
                <Text type="secondary">
                  罐占用：{summary!.tank_blocks!.map((b) => `${b.tank_no} ${fmtDate(b.from_date)}~${fmtDate(b.to_date)}`).join('；')}
                </Text>
              </div>
            )}
          </Card>

          {(result.validation?.issues?.length ?? 0) > 0 && (
            <Card className="mb-4" size="small" title="校验提示" styles={{ body: { padding: 8 } }}>
              <ul className="m-0 pl-5 text-sm">
                {result.validation!.issues!.slice(0, 10).map((issue, i) => (
                  <li key={i}>
                    <Tag
                      color={issue.level === 'warn' ? 'orange' : 'blue'}
                      style={{ marginRight: 4 }}
                    >
                      {issue.level === 'warn' ? '需确认' : '提示'}
                    </Tag>
                    {issue.text}
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Row gutter={16}>
            <Col span={24}>
              <Card
                size="small"
                title="逐日草稿（点「跳过该日」即时重算，空拍自动摊匀）"
                styles={{ body: { padding: 8 } }}
              >
                <Table
                  rowKey="date"
                  size="small"
                  columns={dayColumns}
                  dataSource={result.days}
                  pagination={{ pageSize: 15, showSizeChanger: false }}
                  scroll={{ x: 760 }}
                />
              </Card>
            </Col>
          </Row>

          <Alert
            type="warning"
            showIcon
            className="mt-4"
            title="草稿不生效：请下载 Excel（必要时人工标注与修改），再到排产计划页上传成为正式排产。"
            description={`上传入口：${SCHEDULING_PAGE_URL}（排产计划页）。上传后自动跑一期校验，历史列冻结规则照常生效。`}
          />
        </>
      ) : (
        <Card styles={{ body: { padding: 32 } }}>
          <div className="text-center text-gray-400">
            <FileSearchOutlined className="mr-2" />
            设置参数后点击「生成草稿」，将基于最新 FA 排产无缝接续生成下一周期计划
          </div>
        </Card>
      )}

      {/* 生成历史：同参数去重的工作台记录，仅过程留痕不生效 */}
      <Card
        className="mt-6"
        size="small"
        title="生成历史"
        extra={
          <Button size="small" onClick={() => void reloadRecords()}>
            刷新
          </Button>
        }
        styles={{ body: { padding: 8 } }}
      >
        <Table
          rowKey="id"
          size="small"
          loading={recordsLoading}
          dataSource={records}
          pagination={{ pageSize: 8, showSizeChanger: false }}
          columns={recordColumns}
          locale={{ emptyText: '暂无生成记录' }}
        />
      </Card>

      {/* 历史详情：当时的参数、摘要、校验与逐日方案快照 */}
      <Modal
        open={viewingRecord !== null}
        title={`草稿方案：${
          viewingRecord?.summary?.period?.start ?? ''
        }～${viewingRecord?.summary?.period?.end ?? ''}`}
        footer={null}
        onCancel={() => setViewingRecord(null)}
        width={860}
      >
        {viewingRecord && (
          <>
            <div className="mb-3">
              <Space size={16} wrap>
                <span>
                  移种 <Text strong>{viewingRecord.summary?.transfer_count ?? 0}</Text> 批
                </span>
                <span>
                  放罐 <Text strong>{viewingRecord.summary?.dump_count ?? 0}</Text> 批
                </span>
                <span>
                  跳过 <Text strong>{viewingRecord.params?.skip_dates?.length ?? 0}</Text> 天
                </span>
                <span>
                  校验需确认{' '}
                  <Text strong>
                    {viewingRecord.validation?.summary?.warn ?? 0}
                  </Text>{' '}
                  项
                </span>
                <Text type="secondary">
                  {viewingRecord.created_at
                    ? new Date(viewingRecord.created_at).toLocaleString()
                    : ''}
                  {viewingRecord.created_by_name
                    ? ` · ${viewingRecord.created_by_name}`
                    : ''}
                </Text>
              </Space>
            </div>
            <Table
              rowKey="date"
              size="small"
              dataSource={viewingRecord.days ?? []}
              pagination={{ pageSize: 10, showSizeChanger: false }}
              columns={dayColumns}
              scroll={{ x: 760 }}
            />
          </>
        )}
      </Modal>
    </div>
  )
}
