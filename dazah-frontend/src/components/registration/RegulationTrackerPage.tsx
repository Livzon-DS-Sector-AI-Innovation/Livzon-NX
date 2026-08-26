'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import dayjs, { type Dayjs } from 'dayjs'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import {
  App,
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Drawer,
  Empty,
  InputNumber,
  Input,
  Row,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd'
import type { ColumnsType } from 'antd/es/table'
import { EyeOutlined, LinkOutlined, ReloadOutlined } from '@ant-design/icons'

import {
  analyzeRegulatoryDocumentClient,
  fetchRegulatoryTrackerDocumentDetailClient,
  fetchRegulatoryTrackerDocumentsClient,
  fetchRegulatoryTrackerNotificationRecipientsClient,
  fetchRegulatoryTrackerSyncStatusClient,
  manualSyncRegulatoryTrackerClient,
  updateRegulatoryTrackerNotificationSettingsClient,
  type RegulatoryTrackerDetail,
  type RegulatoryTrackerListItem,
  type RegulatoryTrackerListParams,
  type RegulatoryTrackerManualSyncResult,
  type RegulatoryTrackerNotificationRecipientOption,
  type RegulatoryTrackerNotificationSetting,
  type RegulatoryTrackerPagedResult,
} from '@/lib/api/client/regulatoryTracker'

const { RangePicker } = DatePicker
const DEFAULT_RECENT_WEEK_RANGE: [Dayjs, Dayjs] = [dayjs().subtract(6, 'day'), dayjs()]
const DEFAULT_SYNC_RECENT_DAYS = 7

type DayRange = [Dayjs | null, Dayjs | null] | null
type TrackerFilters = {
  keyword: string
  sourceSite?: string
  publishDateRange: DayRange
  captureDateRange: DayRange
  isNew?: boolean
}

const INITIAL_FILTERS: TrackerFilters = {
  keyword: '',
  sourceSite: undefined,
  publishDateRange: DEFAULT_RECENT_WEEK_RANGE,
  captureDateRange: null,
  isNew: undefined,
}

interface RegulationTrackerPageProps {
  initialResult: RegulatoryTrackerPagedResult<RegulatoryTrackerListItem>
  initialNotificationSettings: RegulatoryTrackerNotificationSetting
  notificationRecipients: RegulatoryTrackerNotificationRecipientOption[]
}

export function formatDate(value?: string | null, withTime?: boolean) {
  if (!value) {
    return '-'
  }

  const parsed = dayjs(value)
  if (!parsed.isValid()) {
    return value
  }

  return parsed.format(withTime ? 'YYYY-MM-DD HH:mm' : 'YYYY-MM-DD')
}

export function renderMultilineText(value?: string | null, clampLines?: number) {
  if (!value) {
    return '-'
  }

  return (
    <div
      title={value}
      style={{
        whiteSpace: 'pre-line',
        wordBreak: 'break-word',
        lineHeight: 1.55,
        display: clampLines ? '-webkit-box' : undefined,
        WebkitBoxOrient: clampLines ? 'vertical' : undefined,
        WebkitLineClamp: clampLines,
        overflow: clampLines ? 'hidden' : undefined,
      }}
    >
      {value}
    </div>
  )
}

export function hasCompletedAnalysis(record?: Pick<RegulatoryTrackerDetail, 'ai_analysis_status' | 'ai_summary'> | null) {
  return (
    record?.ai_analysis_status === 'completed' ||
    Boolean(typeof record?.ai_summary === 'string' && record.ai_summary.trim())
  )
}

export function buildQueryParams(input: TrackerFilters): RegulatoryTrackerListParams {
  const params: RegulatoryTrackerListParams = {}
  const normalizedKeyword = input.keyword.trim()

  if (normalizedKeyword) {
    params.keyword = normalizedKeyword
  }
  if (input.sourceSite) {
    params.sourceSite = input.sourceSite
  }
  if (input.publishDateRange?.[0]) {
    params.publishDateFrom = input.publishDateRange[0].format('YYYY-MM-DD')
  }
  if (input.publishDateRange?.[1]) {
    params.publishDateTo = input.publishDateRange[1].format('YYYY-MM-DD')
  }
  if (input.captureDateRange?.[0]) {
    params.captureDateFrom = input.captureDateRange[0].format('YYYY-MM-DD')
  }
  if (input.captureDateRange?.[1]) {
    params.captureDateTo = input.captureDateRange[1].format('YYYY-MM-DD')
  }
  if (input.isNew !== undefined) {
    params.isNew = input.isNew
  }

  return params
}

export default function RegulationTrackerPage({
  initialResult,
  initialNotificationSettings,
  notificationRecipients,
}: RegulationTrackerPageProps) {
  const { message } = App.useApp()
  const queryClient = useQueryClient()

  const syncPollRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [page, setPage] = useState(initialResult.page)
  const [pageSize, setPageSize] = useState(initialResult.pageSize)
  const [refreshing, setRefreshing] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [analyzingSelected, setAnalyzingSelected] = useState(false)
  const [savingNotificationSettings, setSavingNotificationSettings] = useState(false)

  const [keyword, setKeyword] = useState('')
  const [sourceSite, setSourceSite] = useState<string>()
  const [publishDateRange, setPublishDateRange] = useState<DayRange>(DEFAULT_RECENT_WEEK_RANGE)
  const [captureDateRange, setCaptureDateRange] = useState<DayRange>(null)
  const [isNew, setIsNew] = useState<boolean>()
  const [appliedFilters, setAppliedFilters] = useState<TrackerFilters>(INITIAL_FILTERS)

  const [notificationEnabled, setNotificationEnabled] = useState(initialNotificationSettings.is_enabled)
  const [notificationRecentDays, setNotificationRecentDays] = useState(initialNotificationSettings.recent_days)
  const [notificationRecipientOpenId, setNotificationRecipientOpenId] = useState<string | undefined>(
    initialNotificationSettings.recipient_open_id || undefined
  )
  const [notificationSettingSnapshot, setNotificationSettingSnapshot] =
    useState<RegulatoryTrackerNotificationSetting>(initialNotificationSettings)

  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null)
  const [detailOpen, setDetailOpen] = useState(false)

  const isInitialListState =
    page === initialResult.page &&
    pageSize === initialResult.pageSize &&
    appliedFilters.keyword === INITIAL_FILTERS.keyword &&
    appliedFilters.sourceSite === INITIAL_FILTERS.sourceSite &&
    appliedFilters.captureDateRange === INITIAL_FILTERS.captureDateRange &&
    appliedFilters.isNew === INITIAL_FILTERS.isNew &&
    (appliedFilters.publishDateRange?.[0]?.isSame(INITIAL_FILTERS.publishDateRange![0]!, 'day') ?? false) &&
    (appliedFilters.publishDateRange?.[1]?.isSame(INITIAL_FILTERS.publishDateRange![1]!, 'day') ?? false)

  const listQuery = useQuery({
    queryKey: [
      'registration-regulation',
      'list',
      {
        keyword: appliedFilters.keyword,
        sourceSite: appliedFilters.sourceSite,
        publishDateFrom: appliedFilters.publishDateRange?.[0]?.format('YYYY-MM-DD'),
        publishDateTo: appliedFilters.publishDateRange?.[1]?.format('YYYY-MM-DD'),
        captureFrom: appliedFilters.captureDateRange?.[0]?.format('YYYY-MM-DD'),
        captureTo: appliedFilters.captureDateRange?.[1]?.format('YYYY-MM-DD'),
        isNew: appliedFilters.isNew,
        page,
        pageSize,
      },
    ],
    queryFn: () =>
      fetchRegulatoryTrackerDocumentsClient({
        ...buildQueryParams(appliedFilters),
        page,
        pageSize,
      }),
    initialData: isInitialListState && initialResult.items.length > 0 ? initialResult : undefined,
  })

  const detailQuery = useQuery({
    queryKey: ['registration-regulation', 'detail', selectedDocumentId],
    queryFn: () => fetchRegulatoryTrackerDocumentDetailClient(selectedDocumentId as string),
    enabled: !!selectedDocumentId && detailOpen,
  })

  const recipientsQuery = useQuery({
    queryKey: ['registration-regulation', 'recipients'],
    queryFn: () => fetchRegulatoryTrackerNotificationRecipientsClient(),
    initialData: notificationRecipients,
  })

  const documents = listQuery.data?.items ?? []
  const total = listQuery.data?.total ?? 0
  const loading = listQuery.isFetching
  const notificationRecipientsState = recipientsQuery.data ?? []
  const loadingNotificationRecipients = recipientsQuery.isFetching
  const detailRecord = (detailQuery.data ?? selectedRecordFromList(documents, selectedDocumentId)) as RegulatoryTrackerDetail | null

  const selectedRecord = useMemo(
    () => documents.find((item) => item.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId]
  )
  const hasDocuments = documents.length > 0

  const sourceSiteOptions = useMemo(
    () =>
      Array.from(
        new Set(
          documents
            .map((item) => item.source_site_name?.trim())
            .filter((value): value is string => Boolean(value))
        )
      ).map((value) => ({
        label: value,
        value,
      })),
    [documents]
  )
  const notificationRecipientOptions = useMemo(
    () =>
      notificationRecipientsState.map((item) => ({
        label: item.department ? `${item.name} / ${item.department}` : item.name,
        value: item.open_id,
      })),
    [notificationRecipientsState]
  )

  useEffect(() => {
    setNotificationEnabled(initialNotificationSettings.is_enabled)
    setNotificationRecentDays(initialNotificationSettings.recent_days)
    setNotificationRecipientOpenId(initialNotificationSettings.recipient_open_id || undefined)
    setNotificationSettingSnapshot(initialNotificationSettings)
  }, [initialNotificationSettings])

  useEffect(() => {
    if (listQuery.error) {
      message.error(listQuery.error instanceof Error ? listQuery.error.message : '加载法规台账失败')
    }
  }, [listQuery.error, message])

  useEffect(() => {
    if (detailQuery.error) {
      message.error(detailQuery.error instanceof Error ? detailQuery.error.message : '加载法规详情失败')
    }
  }, [detailQuery.error, message])

  useEffect(() => {
    if (recipientsQuery.error && notificationRecipients.length === 0) {
      message.warning(recipientsQuery.error instanceof Error ? recipientsQuery.error.message : '通知人列表加载失败')
    }
  }, [recipientsQuery.error, message, notificationRecipients.length])

  useEffect(() => {
    return () => {
      if (syncPollRef.current) {
        clearTimeout(syncPollRef.current)
        syncPollRef.current = null
      }
    }
  }, [])

  function clearSelectionAndDetail() {
    setSelectedDocumentId(null)
    setDetailOpen(false)
  }

  function openDetailDrawer() {
    if (!selectedRecord) {
      message.warning('请先选中一条法规记录')
      return
    }
    setDetailOpen(true)
  }

  async function handleRefresh() {
    setRefreshing(true)
    try {
      await queryClient.invalidateQueries({ queryKey: ['registration-regulation', 'list'] })
      message.success('法规台账已刷新')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '法规台账刷新失败')
    } finally {
      setRefreshing(false)
    }
  }

  async function handleTriggerSync() {
    if (syncPollRef.current) {
      clearTimeout(syncPollRef.current)
      syncPollRef.current = null
    }
    setSyncing(true)
    try {
      try {
        const started = await manualSyncRegulatoryTrackerClient(DEFAULT_SYNC_RECENT_DAYS)
        if (started?.status === 'started') {
          message.success('法规抓取任务已在后台启动')
        } else {
          message.success('法规抓取任务已触发')
        }
      } catch (triggerError) {
        const triggerErrMsg = triggerError instanceof Error ? triggerError.message : ''
        if (triggerErrMsg.includes('后端暂未暴露法规跟踪手动同步 API')) {
          message.info('后端暂未开放法规跟踪手动抓取接口，当前页面仅支持查看、筛选和触发现有分析。')
          setSyncing(false)
          return
        }
        // 409: 已有任务正在执行，继续轮询其进度
        if (triggerErrMsg.includes('已有抓取任务正在执行')) {
          message.info('法规抓取任务正在执行中，正在获取进度')
        } else {
          throw triggerError
        }
      }

      const SYNC_POLL_INTERVAL = 5000
      const SYNC_POLL_MAX_ATTEMPTS = 120 // 最长轮询 10 分钟
      let attempts = 0

      const pollStatus = async () => {
        attempts += 1
        try {
          const state = await fetchRegulatoryTrackerSyncStatusClient()
          if (!state) {
            if (attempts >= SYNC_POLL_MAX_ATTEMPTS) {
              syncPollRef.current = null
              message.warning('法规抓取任务状态查询超时，请稍后手动刷新查看结果')
              setSyncing(false)
              return
            }
            syncPollRef.current = setTimeout(pollStatus, SYNC_POLL_INTERVAL)
            return
          }
          if (state.status === 'completed') {
            syncPollRef.current = null
            const result = state.result as RegulatoryTrackerManualSyncResult | null
            if (result) {
              message.success(
                `法规抓取完成：新增 ${result.totals.inserted} 条，更新 ${result.totals.updated} 条，自动分析 ${result.analysis.analyzed} 条`
              )
            } else {
              message.success('法规抓取任务已完成')
            }
            setPage(1)
            clearSelectionAndDetail()
            await queryClient.invalidateQueries({ queryKey: ['registration-regulation', 'list'] })
            setSyncing(false)
          } else if (state.status === 'failed') {
            syncPollRef.current = null
            message.error(state.error ? `法规抓取失败：${state.error}` : '法规抓取任务失败')
            setSyncing(false)
          } else {
            // running / idle，继续轮询
            if (attempts >= SYNC_POLL_MAX_ATTEMPTS) {
              syncPollRef.current = null
              message.warning('法规抓取任务执行时间较长，请稍后手动刷新查看结果')
              setSyncing(false)
              return
            }
            syncPollRef.current = setTimeout(pollStatus, SYNC_POLL_INTERVAL)
          }
        } catch {
          if (attempts >= SYNC_POLL_MAX_ATTEMPTS) {
            syncPollRef.current = null
            message.warning('法规抓取任务状态查询超时，请稍后手动刷新查看结果')
            setSyncing(false)
            return
          }
          syncPollRef.current = setTimeout(pollStatus, SYNC_POLL_INTERVAL)
        }
      }
      syncPollRef.current = setTimeout(pollStatus, SYNC_POLL_INTERVAL)
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : '触发法规抓取失败'
      message.error(errorMessage)
      setSyncing(false)
    }
  }

  async function handleAnalyzeSelected() {
    if (!selectedRecord) {
      message.warning('请先选中一条法规记录')
      return
    }

    setAnalyzingSelected(true)
    try {
      const detail = await queryClient.fetchQuery({
        queryKey: ['registration-regulation', 'detail', selectedRecord.id],
        queryFn: () => fetchRegulatoryTrackerDocumentDetailClient(selectedRecord.id),
      })
      if (detail && hasCompletedAnalysis(detail)) {
        setDetailOpen(true)
        return
      }

      const result = await analyzeRegulatoryDocumentClient(selectedRecord.id)
      if (!result?.analyzed) {
        message.warning('法规分析未返回成功结果，请稍后刷新确认')
        return
      }

      message.success(`已触发《${selectedRecord.title}》分析`)
      await queryClient.invalidateQueries({ queryKey: ['registration-regulation'] })
      setDetailOpen(true)
    } catch (error) {
      message.error(error instanceof Error ? error.message : '触发法规分析失败')
    } finally {
      setAnalyzingSelected(false)
    }
  }

  async function handleSaveNotificationSettings() {
    setSavingNotificationSettings(true)
    try {
      const result = await updateRegulatoryTrackerNotificationSettingsClient({
        is_enabled: notificationEnabled,
        recent_days: notificationRecentDays,
        recipient_open_id: notificationRecipientOpenId || null,
      })
      if (!result) {
        message.warning('推送配置未返回结果，请稍后刷新确认')
        return
      }

      setNotificationSettingSnapshot(result)
      setNotificationEnabled(result.is_enabled)
      setNotificationRecentDays(result.recent_days)
      setNotificationRecipientOpenId(result.recipient_open_id || undefined)
      message.success('法规更新推送配置已保存')
    } catch (error) {
      message.error(error instanceof Error ? error.message : '保存推送配置失败')
    } finally {
      setSavingNotificationSettings(false)
    }
  }

  function handleSearch() {
    setAppliedFilters({ keyword, sourceSite, publishDateRange, captureDateRange, isNew })
    setPage(1)
    clearSelectionAndDetail()
  }

  function handleReset() {
    const nextFilters: TrackerFilters = {
      keyword: '',
      sourceSite: undefined,
      publishDateRange: DEFAULT_RECENT_WEEK_RANGE,
      captureDateRange: null,
      isNew: undefined,
    }

    setKeyword('')
    setSourceSite(undefined)
    setPublishDateRange(DEFAULT_RECENT_WEEK_RANGE)
    setCaptureDateRange(null)
    setIsNew(undefined)
    setAppliedFilters(nextFilters)
    setPage(1)
    clearSelectionAndDetail()
  }

  const columns = useMemo<ColumnsType<RegulatoryTrackerListItem>>(
    () => [
      {
        title: '抓取日期',
        dataIndex: 'capture_date',
        key: 'capture_date',
        width: 160,
        align: 'center',
        render: (value: string | null | undefined) => formatDate(value, true),
      },
      {
        title: '名称',
        dataIndex: 'title',
        key: 'title',
        width: 280,
        render: (value: string, record) => (
          <Space orientation="vertical" size={4} style={{ width: '100%' }}>
            <Typography.Text strong>{value}</Typography.Text>
            {record.is_new ? (
              <Tag color="processing" style={{ width: 'fit-content', marginInlineEnd: 0 }}>
                新增
              </Tag>
            ) : null}
          </Space>
        ),
      },
      {
        title: '版本号',
        dataIndex: 'version_text',
        key: 'version_text',
        width: 120,
        align: 'center',
        render: (value: string | null | undefined) => value || '-',
      },
      {
        title: '发布日期',
        dataIndex: 'publish_date',
        key: 'publish_date',
        width: 120,
        align: 'center',
        render: (value: string | null | undefined) => formatDate(value),
      },
      {
        title: '生效日期',
        dataIndex: 'effective_date',
        key: 'effective_date',
        width: 120,
        align: 'center',
        render: (value: string | null | undefined) => formatDate(value),
      },
      {
        title: '内容总结',
        dataIndex: 'summary_text',
        key: 'summary_text',
        width: 320,
        render: (value: string | null | undefined) => renderMultilineText(value, 3),
      },
      {
        title: '网址',
        dataIndex: 'source_url',
        key: 'source_url',
        width: 260,
        render: (value: string | null | undefined) =>
          value ? (
            <Typography.Link href={value} target="_blank" rel="noreferrer">
              <Space size={4}>
                <LinkOutlined />
                <span
                  style={{
                    display: 'inline-block',
                    maxWidth: 210,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    verticalAlign: 'bottom',
                    whiteSpace: 'nowrap',
                  }}
                  title={value}
                >
                  {value}
                </span>
              </Space>
            </Typography.Link>
          ) : (
            '-'
          ),
      },
      {
        title: '来源网站',
        dataIndex: 'source_site_name',
        key: 'source_site_name',
        width: 160,
        align: 'center',
        render: (value: string | null | undefined) => value || '-',
      },
    ],
    []
  )

  return (
    <Space orientation="vertical" size={16} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ marginBottom: 4 }}>
          法规跟踪
        </Typography.Title>
      </div>

      <Card size="small" title="筛选条件">
        <Row gutter={[12, 12]}>
          <Col xs={24} md={12} lg={8}>
            <Input
              allowClear
              placeholder="关键词搜索法规名称、版本号或内容总结"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onPressEnter={handleSearch}
            />
          </Col>
          <Col xs={24} md={12} lg={8}>
            <Select
              allowClear
              placeholder="来源网站"
              value={sourceSite}
              onChange={(value) => setSourceSite(value)}
              options={sourceSiteOptions}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} md={12} lg={8}>
            <RangePicker
              value={publishDateRange}
              onChange={(dates) => setPublishDateRange((dates as DayRange) ?? null)}
              style={{ width: '100%' }}
              placeholder={['发布日期开始', '发布日期结束']}
            />
          </Col>
          <Col xs={24} md={12} lg={8}>
            <RangePicker
              value={captureDateRange}
              onChange={(dates) => setCaptureDateRange((dates as DayRange) ?? null)}
              style={{ width: '100%' }}
              placeholder={['抓取日期开始', '抓取日期结束']}
            />
          </Col>
          <Col xs={24} md={12} lg={8}>
            <Select
              allowClear
              placeholder="新增状态"
              value={isNew}
              onChange={(value) => setIsNew(value)}
              options={[
                { label: '新增', value: true },
                { label: '非新增', value: false },
              ]}
              style={{ width: '100%' }}
            />
          </Col>
          <Col xs={24} md={12} lg={8}>
            <Space>
              <Button type="primary" onClick={handleSearch}>
                查询
              </Button>
              <Button onClick={handleReset}>重置</Button>
            </Space>
          </Col>
        </Row>
      </Card>

      <Card
        size="small"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} loading={refreshing} onClick={() => void handleRefresh()}>
              刷新数据
            </Button>
            <Button loading={syncing} onClick={() => void handleTriggerSync()}>
              触发抓取
            </Button>
            <Button
              type="primary"
              icon={<EyeOutlined />}
              disabled={!selectedRecord}
              onClick={() => void openDetailDrawer()}
            >
              查看详情
            </Button>
            <Button
              type="default"
              disabled={!selectedRecord}
              loading={analyzingSelected}
              onClick={() => void handleAnalyzeSelected()}
            >
              查看/分析当前选中
            </Button>
          </Space>
        }
      >
        <Table<RegulatoryTrackerListItem>
          rowKey="id"
          size="small"
          className="regulation-tracker-table"
          loading={loading}
          dataSource={documents}
          columns={columns}
          locale={{
            emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无法规记录" />,
          }}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            showQuickJumper: true,
            pageSizeOptions: ['20', '50', '100'],
            showTotal: (count) => `共 ${count} 条`,
            onChange: (nextPage, nextPageSize) => {
              setPage(nextPage)
              setPageSize(nextPageSize)
              clearSelectionAndDetail()
            },
          }}
          scroll={{ x: 1600 }}
          rowClassName={(record) =>
            record.id === selectedDocumentId
              ? 'regulation-tracker-row-selected'
              : 'regulation-tracker-row'
          }
          rowSelection={{
            type: 'radio',
            selectedRowKeys: selectedDocumentId ? [selectedDocumentId] : [],
            onChange: (selectedRowKeys) =>
              setSelectedDocumentId((selectedRowKeys[0] as string | undefined) ?? null),
          }}
          onRow={(record) => ({
            onClick: () => setSelectedDocumentId(record.id),
          })}
        />
      </Card>

      <Card
        size="small"
        title="推送设置"
        extra={
          <Button type="primary" onClick={() => void handleSaveNotificationSettings()} loading={savingNotificationSettings}>
            保存设置
          </Button>
        }
      >
        <Space orientation="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            title="系统会在每天 10:00 自动抓取法规网站更新内容；若存在新增或更新法规，将自动分析并推送到指定 QA 接收人。"
          />
          <Row gutter={[12, 12]} align="middle">
            <Col xs={24} md={6}>
              <Space>
                <Typography.Text strong>启用自动推送</Typography.Text>
                <Switch checked={notificationEnabled} onChange={setNotificationEnabled} />
              </Space>
            </Col>
            <Col xs={24} md={6}>
              <Space>
                <Typography.Text strong>抓取最近</Typography.Text>
                <InputNumber
                  min={1}
                  max={30}
                  value={notificationRecentDays}
                  onChange={(value) => setNotificationRecentDays(value || 7)}
                  style={{ width: 110 }}
                />
                <Typography.Text>天</Typography.Text>
              </Space>
            </Col>
            <Col xs={24} md={12}>
              <Select
                showSearch
                allowClear
                style={{ width: '100%' }}
                placeholder="选择通知人（仅显示 QA 人员）"
                loading={loadingNotificationRecipients}
                value={notificationRecipientOpenId}
                onChange={(value) => setNotificationRecipientOpenId(value)}
                optionFilterProp="label"
                options={notificationRecipientOptions}
              />
            </Col>
          </Row>

          <Space wrap size={[8, 8]}>
            <Tag color={notificationSettingSnapshot.is_enabled ? 'processing' : 'default'}>
              {notificationSettingSnapshot.is_enabled ? '已启用' : '未启用'}
            </Tag>
            <Tag color="purple">执行时间：每日 {notificationSettingSnapshot.schedule_time}</Tag>
            <Tag color="blue">当前规则命中 {notificationSettingSnapshot.pending_count} 条待推送更新</Tag>
            {notificationSettingSnapshot.recipient_name ? (
              <Tag color="gold">
                当前接收人：{notificationSettingSnapshot.recipient_name}
                {notificationSettingSnapshot.recipient_department
                  ? ` / ${notificationSettingSnapshot.recipient_department}`
                  : ''}
              </Tag>
            ) : null}
          </Space>

          <Typography.Text type="secondary">
            通知人直接取自质量管理中的 QA 飞书联系人。人员变动后，直接在这里重新选择即可。
          </Typography.Text>

          {!notificationRecipientOptions.length ? (
            <Alert
              type="warning"
              showIcon
              title="当前没有可用的 QA 飞书联系人，暂时无法启用法规更新自动推送。"
            />
          ) : null}
        </Space>
      </Card>

      <Drawer
        title="法规详情"
        placement="right"
        size={560}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        loading={detailQuery.isFetching}
      >
        {detailRecord ? (
          <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Descriptions
              size="small"
              bordered
              column={1}
              title="基础信息"
              items={[
                { key: 'capture_date', label: '抓取日期', children: formatDate(detailRecord.capture_date, true) },
                { key: 'title', label: '名称', children: detailRecord.title },
                { key: 'version_text', label: '版本号', children: detailRecord.version_text || '-' },
                { key: 'publish_date', label: '发布日期', children: formatDate(detailRecord.publish_date) },
                { key: 'effective_date', label: '生效日期', children: formatDate(detailRecord.effective_date) },
                { key: 'source_site_name', label: '来源网站', children: detailRecord.source_site_name || '-' },
                {
                  key: 'source_url',
                  label: '网址',
                  children: detailRecord.source_url ? (
                    <Typography.Link href={detailRecord.source_url} target="_blank" rel="noreferrer">
                      {detailRecord.source_url}
                    </Typography.Link>
                  ) : (
                    '-'
                  ),
                },
                {
                  key: 'is_new',
                  label: '新增状态',
                  children: detailRecord.is_new ? <Tag color="processing">新增</Tag> : '非新增',
                },
              ]}
            />

            <Card size="small" title="内容总结">
              {renderMultilineText(detailRecord.summary_text)}
            </Card>

            <Card size="small" title="AI 信息">
              <Descriptions
                size="small"
                bordered
                column={1}
                items={[
                  {
                    key: 'ai_analysis_status',
                    label: '分析状态',
                    children: detailRecord.ai_analysis_status || '未分析',
                  },
                  {
                    key: 'ai_analyzed_at',
                    label: '分析时间',
                    children: formatDate(detailRecord.ai_analyzed_at, true),
                  },
                  {
                    key: 'ai_relevance_score',
                    label: '相关性评分',
                    children:
                      detailRecord.ai_relevance_score !== null &&
                      detailRecord.ai_relevance_score !== undefined
                        ? detailRecord.ai_relevance_score.toFixed(2)
                        : '-',
                  },
                  {
                    key: 'ai_summary',
                    label: 'AI 摘要',
                    children: renderMultilineText(detailRecord.ai_summary),
                  },
                  {
                    key: 'ai_key_points',
                    label: '关键要点',
                    children:
                      detailRecord.ai_key_points && detailRecord.ai_key_points.length > 0 ? (
                        <Space orientation="vertical" size={4}>
                          {detailRecord.ai_key_points.map((point, index) => (
                            <Typography.Text key={`${index}-${point}`}>{`${index + 1}. ${point}`}</Typography.Text>
                          ))}
                        </Space>
                      ) : (
                        '-'
                      ),
                  },
                ]}
              />
            </Card>
          </Space>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="未选择法规记录" />
        )}
      </Drawer>

      <style jsx global>{`
        .regulation-tracker-table .ant-table-thead > tr > th {
          background: #fafafa;
          border-bottom: 1px solid #e8e8e8;
          text-align: center;
          font-size: 13px;
          line-height: 1.45;
          font-weight: 600;
          padding: 10px 8px;
        }

        .regulation-tracker-table .ant-table-tbody > tr > td {
          vertical-align: top;
          font-size: 13px;
          line-height: 1.55;
          padding: 14px 10px;
          border-bottom: 1px solid #f0f0f0;
        }

        .regulation-tracker-table .ant-table-tbody > tr.regulation-tracker-row:nth-child(even) > td {
          background: #fcfcfc;
        }

        .regulation-tracker-table .ant-table-tbody > tr.regulation-tracker-row:hover > td {
          background: #f7f7f7;
        }

        .regulation-tracker-table .ant-table-tbody > tr.regulation-tracker-row-selected > td {
          background: #f0f5ff !important;
        }
      `}</style>
    </Space>
  )
}

function selectedRecordFromList(
  documents: RegulatoryTrackerListItem[],
  selectedDocumentId: string | null
): RegulatoryTrackerListItem | null {
  if (!selectedDocumentId) return null
  return documents.find((item) => item.id === selectedDocumentId) ?? null
}
