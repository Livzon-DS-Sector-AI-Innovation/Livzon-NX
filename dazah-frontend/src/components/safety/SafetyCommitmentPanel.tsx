'use client'

/**
 * 安全承诺页（应急〔2018〕74号 承诺公告制度）。
 *
 * 布局：页头（日期/状态/操作）→ 企业状态（结构化编辑）→ 左右滚动信息卡
 * （安全承诺信息 / 重大危险源信息）→ AI 安全风险研判 → 企业安全承诺公告。
 * 历史日期只读；写操作走 canOperate 权限。
 */

import { useCallback, useMemo, useState } from 'react'
import {
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Radio,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from 'antd'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  ReloadOutlined,
  SendOutlined,
} from '@ant-design/icons'
import dayjs from 'dayjs'
import PlatformNotice from '@/components/shared/PlatformNotice'
import { usePagePermissions } from '@/hooks/usePagePermissions'
import { SAFETY_COMMITMENT_PAGE_KEY, formatCnDateTime, todayStr, type CommitmentCardType, type EnterpriseStatus, type SafetyCommitmentCard, type SafetyCommitmentReport } from '@/lib/safety-commitment'
import {
  createCommitmentCard,
  deleteCommitmentCard,
  getCommitmentByDate,
  getCommitmentCards,
  getCommitmentToday,
  publishCommitment,
  regenerateCommitmentRiskAssessment,
  updateCommitment,
  updateCommitmentCard,
} from '@/actions/safety'

const PAGE_KEY = SAFETY_COMMITMENT_PAGE_KEY

const RISK_LEVEL_COLOR: Record<string, string> = {
  低: 'green',
  中: 'gold',
  较高: 'orange',
  高: 'red',
}

type TriState = 'yes' | 'no' | 'unknown'

function triToBool(value: TriState | undefined): boolean | null {
  if (value === 'yes') return true
  if (value === 'no') return false
  return null
}

function boolToTri(value: boolean | null | undefined): TriState {
  if (value === true) return 'yes'
  if (value === false) return 'no'
  return 'unknown'
}

interface SafetyCommitmentPanelProps {
  initialReport: SafetyCommitmentReport | null
  initialCreatedToday?: boolean
  initialCards: SafetyCommitmentCard[]
  initialError?: string | null
}

export function SafetyCommitmentPanel({
  initialReport,
  initialCards,
  initialError,
}: SafetyCommitmentPanelProps) {
  const { message } = App.useApp()
  const permissions = usePagePermissions(PAGE_KEY)
  const [report, setReport] = useState<SafetyCommitmentReport | null>(
    initialReport
  )
  const [cards, setCards] = useState<SafetyCommitmentCard[]>(initialCards)
  const [error, setError] = useState<string | null>(initialError ?? null)
  const [viewDate, setViewDate] = useState<string>(todayStr())
  const isToday = viewDate === todayStr()

  // ── 企业状态编辑 ──
  const [statusEditing, setStatusEditing] = useState(false)
  const [statusForm, setStatusForm] = useState<EnterpriseStatus>(
    () => ({
      ...(initialReport?.enterprise_status ?? {}),
    } as EnterpriseStatus)
  )
  const [statusSaving, setStatusSaving] = useState(false)

  // ── 承诺正文编辑 ──
  const [commitmentEditing, setCommitmentEditing] = useState(false)
  const [commitmentDraft, setCommitmentDraft] = useState(
    initialReport?.commitment_text ?? ''
  )
  const [commitmentSaving, setCommitmentSaving] = useState(false)

  // ── 发布 ──
  const [publishOpen, setPublishOpen] = useState(false)
  const [publisherName, setPublisherName] = useState(
    initialReport?.publisher_name ?? ''
  )
  const [publishing, setPublishing] = useState(false)

  // ── AI 研判 ──
  const [assessing, setAssessing] = useState(false)

  // ── 信息卡 ──
  const [cardEditingId, setCardEditingId] = useState<string | null>(null)
  const [cardDraft, setCardDraft] = useState({ title: '', content: '' })
  const [creatingType, setCreatingType] = useState<CommitmentCardType | null>(null)
  const [newCard, setNewCard] = useState({ title: '', content: '' })
  const [savingCard, setSavingCard] = useState(false)

  const readOnly = !isToday || !permissions.canOperate

  const reload = useCallback(async () => {
    const [todayRes, cardsRes] = await Promise.all([
      getCommitmentToday(PAGE_KEY),
      getCommitmentCards(undefined, PAGE_KEY),
    ])
    if (todayRes.code === 200 && todayRes.data) {
      setReport(todayRes.data.report)
      setStatusForm({
        ...(todayRes.data.report.enterprise_status ?? {}),
      } as EnterpriseStatus)
      setCommitmentDraft(todayRes.data.report.commitment_text ?? '')
      setPublisherName(todayRes.data.report.publisher_name ?? '')
      setError(null)
    } else {
      setError(todayRes.message || '安全承诺日报加载失败')
    }
    if (cardsRes.code === 200 && cardsRes.data) {
      setCards(cardsRes.data.cards)
    }
  }, [])

  const loadByDate = useCallback(async (date: string) => {
    setError(null)
    if (date === todayStr()) {
      await reload()
      return
    }
    const res = await getCommitmentByDate(date, PAGE_KEY)
    if (res.code === 200 && res.data) {
      // 兼容两种返回形态：直接对象或 {report}
      const payload = res.data as unknown as
        | SafetyCommitmentReport
        | { report: SafetyCommitmentReport }
      const item = 'report' in payload ? payload.report : payload
      setReport(item)
    } else {
      setReport(null)
      setError(res.message || '该日期暂无安全承诺日报')
    }
  }, [reload])

  const saveStatus = async () => {
    if (!report) return
    setStatusSaving(true)
    const res = await updateCommitment(
      report.id,
      { enterprise_status: statusForm as unknown as Record<string, unknown> },
      PAGE_KEY
    )
    setStatusSaving(false)
    if (res.code === 200 && res.data) {
      // 后端 PUT 返回的 data 即日报对象本身
      setReport(res.data)
      setStatusEditing(false)
      message.success('企业状态已保存')
    } else {
      message.error(res.message || '保存失败')
    }
  }

  const saveCommitmentText = async () => {
    if (!report) return
    setCommitmentSaving(true)
    const res = await updateCommitment(
      report.id,
      { commitment_text: commitmentDraft },
      PAGE_KEY
    )
    setCommitmentSaving(false)
    if (res.code === 200 && res.data) {
      setReport(res.data)
      setCommitmentEditing(false)
      message.success('企业安全承诺已保存')
    } else {
      message.error(res.message || '保存失败')
    }
  }

  const runAssessment = async () => {
    if (!report) return
    setAssessing(true)
    const res = await regenerateCommitmentRiskAssessment(report.id, PAGE_KEY)
    setAssessing(false)
    if (res.code === 200 && res.data?.success && res.data.report) {
      setReport(res.data.report)
      message.success('AI 风险研判已完成')
    } else {
      message.error(res.data?.message || res.message || 'AI 研判失败')
    }
  }

  const doPublish = async () => {
    if (!report) return
    const name = publisherName.trim()
    if (!name) {
      message.warning('请填写承诺人（主要负责人）姓名')
      return
    }
    setPublishing(true)
    const res = await publishCommitment(report.id, name, PAGE_KEY)
    setPublishing(false)
    if (res.code === 200 && res.data) {
      // 后端 publish 返回的 data 即日报对象本身
      setReport(res.data)
      setPublishOpen(false)
      message.success('承诺公告已发布')
    } else {
      message.error(res.message || '发布失败')
    }
  }

  // ── 信息卡操作 ──

  const beginEditCard = (card: SafetyCommitmentCard) => {
    setCardEditingId(card.id)
    setCardDraft({ title: card.title, content: card.content })
  }

  const saveCard = async (cardId: string) => {
    setSavingCard(true)
    const res = await updateCommitmentCard(cardId, cardDraft, PAGE_KEY)
    setSavingCard(false)
    if (res.code === 200 && res.data) {
      setCards((prev) =>
        prev.map((item) => (item.id === cardId ? res.data! : item))
      )
      setCardEditingId(null)
      message.success('信息卡已保存')
    } else {
      message.error(res.message || '保存失败')
    }
  }

  const removeCard = async (cardId: string) => {
    const res = await deleteCommitmentCard(cardId, PAGE_KEY)
    if (res.code === 200) {
      setCards((prev) => prev.filter((item) => item.id !== cardId))
      message.success('信息卡已删除')
    } else {
      message.error(res.message || '删除失败')
    }
  }

  const addCard = async () => {
    if (!creatingType) return
    setSavingCard(true)
    const res = await createCommitmentCard(
      { card_type: creatingType, title: newCard.title, content: newCard.content },
      PAGE_KEY
    )
    setSavingCard(false)
    if (res.code === 200 && res.data) {
      setCards((prev) => [...prev, res.data!])
      setCreatingType(null)
      setNewCard({ title: '', content: '' })
      message.success('信息卡已新增')
    } else {
      message.error(res.message || '新增失败')
    }
  }

  const status = report?.enterprise_status ?? {}
  const special = status.special_work ?? {
    hot_work_level1: 0,
    hot_work_level2: 0,
    height_work: 0,
    confined_space: 0,
    other: 0,
  }
  const risk = report?.risk_assessment ?? null
  const published = report?.status === 'published'

  const numField = (
    label: string,
    value: number | undefined,
    onChange: (v: number | null) => void
  ) => (
    <Col span={6} key={label}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {label}
      </Typography.Text>
      <div>
        {statusEditing && !readOnly ? (
          <InputNumber
            min={0}
            style={{ width: '100%', marginTop: 4 }}
            value={value ?? 0}
            onChange={(v) => onChange(v)}
          />
        ) : (
          <div style={{ fontSize: 18, fontWeight: 600 }}>{value ?? 0}</div>
        )}
      </div>
    </Col>
  )

  const triField = (
    label: string,
    value: TriState,
    onChange: (v: TriState) => void,
    extra?: string
  ) => (
    <Col span={12} key={label}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span>{label}</span>
        {statusEditing && !readOnly ? (
          <Radio.Group
            size="small"
            value={value}
            options={[
              { label: '是', value: 'yes' },
              { label: '否', value: 'no' },
              { label: '未确认', value: 'unknown' },
            ]}
            optionType="button"
            buttonStyle="solid"
            onChange={(e) => onChange(e.target.value as TriState)}
          />
        ) : (
          <Tag color={value === 'yes' ? 'green' : value === 'no' ? 'red' : 'default'}>
            {value === 'yes' ? '是' : value === 'no' ? '否' : '未确认'}
          </Tag>
        )}
        {extra && (
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {extra}
          </Typography.Text>
        )}
      </div>
    </Col>
  )

  const personField = (label: string, key: 'person_main' | 'person_tech' | 'person_ops') => (
    <Col span={8} key={key}>
      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
        {label}
      </Typography.Text>
      {statusEditing && !readOnly ? (
        <Input
          style={{ marginTop: 4 }}
          value={status[key] ?? ''}
          onChange={(e) =>
            setStatusForm((prev) => ({ ...prev, [key]: e.target.value }))
          }
        />
      ) : (
        <div style={{ fontWeight: 600 }}>{status[key] || '—'}</div>
      )}
    </Col>
  )

  const updateNum = (key: keyof EnterpriseStatus, value: number | null) =>
    setStatusForm((prev) => ({ ...prev, [key]: value ?? 0 }))

  const updateSpecial = (key: string, value: number | null) =>
    setStatusForm((prev) => ({
      ...prev,
      special_work: { ...prev.special_work, [key]: value ?? 0 },
    }))

  const carouselSection = (
    title: string,
    cardType: CommitmentCardType,
    description: string
  ) => {
    const items = cards.filter((item) => item.card_type === cardType)
    return (
      <Card
        size="small"
        title={
          <Space>
            <span>{title}</span>
            <Tag color="blue">可编辑</Tag>
          </Space>
        }
        extra={
          !readOnly && (
            <Button
              size="small"
              icon={<PlusOutlined />}
              onClick={() => {
                setCreatingType(cardType)
                setNewCard({ title: '', content: '' })
              }}
            >
              新增
            </Button>
          )
        }
      >
        <Typography.Paragraph type="secondary" style={{ marginBottom: 8, fontSize: 12 }}>
          {description}
        </Typography.Paragraph>
        {items.length === 0 ? (
          <div
            style={{
              border: '1px dashed #d9d9d9',
              borderRadius: 8,
              padding: 24,
              textAlign: 'center',
              color: '#999',
            }}
          >
            暂无内容，点击「新增」创建第一张信息卡
          </div>
        ) : (
          <div
            data-testid={`commitment-carousel-${cardType}`}
            style={{ display: 'flex', gap: 12, overflowX: 'auto', paddingBottom: 8 }}
          >
            {items.map((card) => (
              <div
                key={card.id}
                style={{
                  minWidth: 320,
                  maxWidth: 420,
                  flex: '0 0 auto',
                  border: '1px solid #f0f0f0',
                  borderRadius: 8,
                  padding: 12,
                }}
              >
                {cardEditingId === card.id ? (
                  <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
                    <Input
                      value={cardDraft.title}
                      placeholder="卡片标题"
                      onChange={(e) =>
                        setCardDraft((prev) => ({ ...prev, title: e.target.value }))
                      }
                    />
                    <Input.TextArea
                      rows={5}
                      value={cardDraft.content}
                      placeholder="卡片内容"
                      onChange={(e) =>
                        setCardDraft((prev) => ({ ...prev, content: e.target.value }))
                      }
                    />
                    <Space>
                      <Button
                        size="small"
                        type="primary"
                        loading={savingCard}
                        onClick={() => void saveCard(card.id)}
                      >
                        保存
                      </Button>
                      <Button size="small" onClick={() => setCardEditingId(null)}>
                        取消
                      </Button>
                    </Space>
                  </Space>
                ) : (
                  <>
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 8,
                      }}
                    >
                      <Typography.Text strong>{card.title || '（未命名）'}</Typography.Text>
                      {!readOnly && (
                        <Space size={4}>
                          <Button
                            type="text"
                            size="small"
                            icon={<EditOutlined />}
                            onClick={() => beginEditCard(card)}
                          />
                          <Popconfirm
                            title="删除这张信息卡？"
                            description="删除后网页端不可恢复。"
                            onConfirm={() => void removeCard(card.id)}
                          >
                            <Button
                              type="text"
                              size="small"
                              danger
                              icon={<DeleteOutlined />}
                            />
                          </Popconfirm>
                        </Space>
                      )}
                    </div>
                    <div style={{ whiteSpace: 'pre-wrap', fontSize: 13, lineHeight: 1.7 }}>
                      {card.content}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </Card>
    )
  }

  const riskBasis = useMemo(() => {
    if (!risk?.data_basis) return null
    const parts: string[] = []
    const basis = risk.data_basis
    if (typeof basis.ops_report_total === 'number')
      parts.push(`特殊作业报备 ${basis.ops_report_total} 项`)
    if (typeof basis.permit_total === 'number')
      parts.push(`作业票 ${basis.permit_total} 张`)
    if (typeof basis.hazard_total === 'number')
      parts.push(`未关闭隐患 ${basis.hazard_total} 条`)
    if (typeof basis.over_limit_total === 'number')
      parts.push(`超储化学品 ${basis.over_limit_total} 种`)
    if (typeof basis.accident_total === 'number')
      parts.push(`当日事故 ${basis.accident_total} 起`)
    return parts.join(' · ')
  }, [risk])

  return (
    // 内联 flexDirection：antd cssinjs 按组件挂载顺序插入样式，本页顺序下
    // `.ant-space` 基础规则会排在 `.ant-space-vertical` 之后把方向覆盖为 row
    <Space
      orientation="vertical"
      size={16}
      style={{ display: 'flex', flexDirection: 'column' }}
    >
      {!permissions.canAccess && (
        <PlatformNotice
          type="warning"
          message="无权访问安全承诺页面"
          description="请联系管理员在系统设置中为你授予「安全承诺」页面权限。"
        />
      )}
      {error && (
        <PlatformNotice
          type="error"
          message="安全承诺加载失败"
          description={error}
          showRulesLink={false}
          action={
            <Button size="small" onClick={() => void loadByDate(viewDate)}>
              重试
            </Button>
          }
        />
      )}
      {!isToday && !error && (
        <PlatformNotice
          type="info"
          message={`正在查看 ${viewDate} 的历史日报（只读）`}
          description="历史日报不可编辑；切换回今天可继续填报与发布。"
          showRulesLink={false}
        />
      )}

      {/* ── 页头 ── */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <Space size={12} wrap>
          <Typography.Title level={4} style={{ margin: 0 }}>
            安全承诺
          </Typography.Title>
          <DatePicker
            value={dayjs(viewDate)}
            allowClear={false}
            disabledDate={(current) => current.isAfter(dayjs(), 'day')}
            onChange={(d) => {
              if (d) {
                const next = d.format('YYYY-MM-DD')
                setViewDate(next)
                void loadByDate(next)
              }
            }}
          />
          {published ? (
            <Tag color="green">已发布{report?.publisher_name ? ` · ${report.publisher_name}` : ''}</Tag>
          ) : (
            <Tag color="orange">草稿</Tag>
          )}
          {report?.fill_source && (
            <Tag>{report.fill_source === 'feishu' ? '飞书填报' : '网页填报'}</Tag>
          )}
        </Space>
        <Space wrap>
          {!readOnly && report && (
            <>
              <Button
                icon={<ReloadOutlined />}
                loading={assessing}
                onClick={() => void runAssessment()}
              >
                {risk ? '重新 AI 研判' : 'AI 风险研判'}
              </Button>
              {published ? (
                <Button icon={<SendOutlined />} disabled>
                  承诺公告已发布
                </Button>
              ) : (
                <Button
                  type="primary"
                  icon={<SendOutlined />}
                  onClick={() => setPublishOpen(true)}
                >
                  发布承诺公告
                </Button>
              )}
            </>
          )}
        </Space>
      </div>

      {!report && !error && (
        <div style={{ textAlign: 'center', padding: 48 }}>
          <Spin tip="加载安全承诺日报…" />
        </div>
      )}

      {report && (
        <>
          {/* ── 企业状态 ── */}
          <Card
            size="small"
            title="企业状态"
            extra={
              isToday &&
              permissions.canOperate && (
                <Space>
                  {statusEditing ? (
                    <>
                      <Button
                        size="small"
                        type="primary"
                        loading={statusSaving}
                        onClick={() => void saveStatus()}
                      >
                        保存
                      </Button>
                      <Button
                        size="small"
                        onClick={() => {
                          setStatusEditing(false)
                          setStatusForm({
                            ...(report.enterprise_status ?? {}),
                          } as EnterpriseStatus)
                        }}
                      >
                        取消
                      </Button>
                    </>
                  ) : (
                    <Button
                      size="small"
                      icon={<EditOutlined />}
                      onClick={() => {
                        setStatusForm({
                          ...(report.enterprise_status ?? {}),
                        } as EnterpriseStatus)
                        setStatusEditing(true)
                      }}
                    >
                      编辑
                    </Button>
                  )}
                </Space>
              )
            }
          >
            <Row gutter={[16, 16]}>
              {numField('生产车间总数', status.workshop_total, (v) =>
                updateNum('workshop_total', v)
              )}
              {numField('运行车间', status.workshop_running, (v) =>
                updateNum('workshop_running', v)
              )}
              {numField('停产车间', status.workshop_stopped, (v) =>
                updateNum('workshop_stopped', v)
              )}
              {numField('检修车间', status.workshop_maintenance, (v) =>
                updateNum('workshop_maintenance', v)
              )}
              {numField('试生产装置', status.trial_production_count, (v) =>
                updateNum('trial_production_count', v)
              )}
              {numField('开车装置', status.startup_count, (v) =>
                updateNum('startup_count', v)
              )}
              {numField('停车装置', status.shutdown_count, (v) =>
                updateNum('shutdown_count', v)
              )}
            </Row>
            <div style={{ margin: '16px 0 8px', fontWeight: 600 }}>
              当日特殊危险作业
            </div>
            <Row gutter={[16, 16]}>
              {numField('特殊作业总数', status.special_work_total, (v) =>
                updateNum('special_work_total', v)
              )}
              {numField('一级动火', special.hot_work_level1, (v) =>
                updateSpecial('hot_work_level1', v)
              )}
              {numField('二级动火', special.hot_work_level2, (v) =>
                updateSpecial('hot_work_level2', v)
              )}
              {numField('登高作业', special.height_work, (v) =>
                updateSpecial('height_work', v)
              )}
              {numField('受限空间', special.confined_space, (v) =>
                updateSpecial('confined_space', v)
              )}
              {numField('其他危险作业', special.other, (v) =>
                updateSpecial('other', v)
              )}
            </Row>
            <div style={{ margin: '16px 0 8px', fontWeight: 600 }}>
              隐患 / 承包商 / 重大危险源
            </div>
            <Row gutter={[16, 16]}>
              {numField('一般安全生产隐患条数', status.hazard_count, (v) =>
                updateNum('hazard_count', v)
              )}
              {triField('隐患是否整改', boolToTri(status.hazard_rectified), (v) =>
                setStatusForm((prev) => ({
                  ...prev,
                  hazard_rectified: triToBool(v),
                }))
              )}
              {triField(
                '未整改隐患是否制定临时安全措施',
                boolToTri(status.hazard_temp_measures),
                (v) =>
                  setStatusForm((prev) => ({
                    ...prev,
                    hazard_temp_measures: triToBool(v),
                  }))
              )}
              {triField('今日是否有承包商作业', boolToTri(status.contractor_work ?? false), (v) =>
                setStatusForm((prev) => ({
                  ...prev,
                  contractor_work: triToBool(v) ?? false,
                }))
              )}
              {triField(
                '承包商是否已培训及落实现场安全措施',
                boolToTri(status.contractor_trained),
                (v) =>
                  setStatusForm((prev) => ({
                    ...prev,
                    contractor_trained: triToBool(v),
                  }))
              )}
              {triField(
                '储区、仓库等重大危险源是否处于安全状态',
                boolToTri(status.major_hazard_safe),
                (v) =>
                  setStatusForm((prev) => ({
                    ...prev,
                    major_hazard_safe: triToBool(v),
                  }))
              )}
              {triField(
                '重大危险源安全包保责任制是否落实',
                boolToTri(status.responsibility_implemented),
                (v) =>
                  setStatusForm((prev) => ({
                    ...prev,
                    responsibility_implemented: triToBool(v),
                  }))
              )}
            </Row>
            <div style={{ margin: '16px 0 8px', fontWeight: 600 }}>
              重大危险源安全包保责任人
            </div>
            <Row gutter={[16, 16]}>
              {personField('主要负责人', 'person_main')}
              {personField('技术负责人', 'person_tech')}
              {personField('操作负责人', 'person_ops')}
            </Row>
          </Card>

          {/* ── 左右滚动信息卡 ── */}
          {carouselSection(
            '安全承诺信息',
            'commitment',
            '按左右滚动查看；点击卡片右上角编辑，内容即时保存。'
          )}
          {carouselSection(
            '重大危险源信息',
            'major_hazard',
            '重大危险源台账要点与管控要求；支持多张卡片左右滚动。'
          )}

          {/* ── AI 风险研判 ── */}
          <Card
            size="small"
            title={
              <Space>
                <span>安全风险研判</span>
                <Tag color="purple">AI 生成</Tag>
              </Space>
            }
            extra={
              risk?.generated_at && (
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  生成于 {formatCnDateTime(risk.generated_at)}
                </Typography.Text>
              )
            }
          >
            {risk ? (
              <Space orientation="vertical" size={8} style={{ display: 'flex' }}>
                <Space size={12}>
                  <Tag color={RISK_LEVEL_COLOR[risk.risk_level] ?? 'default'}>
                    综合风险等级：{risk.risk_level}
                  </Tag>
                  {riskBasis && (
                    <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                      数据依据：{riskBasis}
                    </Typography.Text>
                  )}
                </Space>
                <Typography.Paragraph style={{ marginBottom: 0 }}>
                  {risk.summary}
                </Typography.Paragraph>
                {risk.key_risks.length > 0 && (
                  <div>
                    <Typography.Text strong>主要风险点</Typography.Text>
                    <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
                      {risk.key_risks.map((item, idx) => (
                        <li key={idx} style={{ fontSize: 13 }}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {risk.suggestions.length > 0 && (
                  <div>
                    <Typography.Text strong>管控建议</Typography.Text>
                    <ul style={{ margin: '4px 0 0', paddingLeft: 20 }}>
                      {risk.suggestions.map((item, idx) => (
                        <li key={idx} style={{ fontSize: 13 }}>{item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                  AI 研判仅作辅助参考，不替代人工确认与审批责任。
                </Typography.Text>
              </Space>
            ) : (
              <Typography.Text type="secondary">
                尚未生成 AI 风险研判；点击页头「AI 风险研判」根据当日作业与危化品库存自动生成。
              </Typography.Text>
            )}
          </Card>

          {/* ── 企业安全承诺 ── */}
          <Card
            size="small"
            title="企业安全承诺"
            extra={
              isToday &&
              permissions.canOperate && (
                commitmentEditing ? (
                  <Space>
                    <Button
                      size="small"
                      type="primary"
                      loading={commitmentSaving}
                      onClick={() => void saveCommitmentText()}
                    >
                      保存
                    </Button>
                    <Button
                      size="small"
                      onClick={() => {
                        setCommitmentEditing(false)
                        setCommitmentDraft(report.commitment_text ?? '')
                      }}
                    >
                      取消
                    </Button>
                  </Space>
                ) : (
                  <Button
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => {
                      setCommitmentDraft(report.commitment_text ?? '')
                      setCommitmentEditing(true)
                    }}
                  >
                    编辑
                  </Button>
                )
              )
            }
          >
            {published && report.published_at && (
              <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
                由 {report.publisher_name || '—'} 于{' '}
                {formatCnDateTime(report.published_at)} 发布
              </Typography.Paragraph>
            )}
            {commitmentEditing ? (
              <Input.TextArea
                rows={10}
                value={commitmentDraft}
                onChange={(e) => setCommitmentDraft(e.target.value)}
              />
            ) : (
              <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.9, fontSize: 13 }}>
                {report.commitment_text || '尚未填写承诺正文，点击「编辑」填写。'}
              </div>
            )}
          </Card>
        </>
      )}

      {/* ── 发布确认弹窗 ── */}
      <Modal
        title="发布当日承诺公告"
        open={publishOpen}
        onCancel={() => setPublishOpen(false)}
        confirmLoading={publishing}
        onOk={() => void doPublish()}
        okText="确认发布"
        cancelText="取消"
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Typography.Paragraph>
            依据《危险化学品企业安全风险研判与承诺公告制度》（应急〔2018〕74号），
            请确认当日装置、罐区、仓库处于安全运行状态，重大隐患已落实治理措施，
            主要风险得到有效管控后，以主要负责人名义发布当日承诺公告。
          </Typography.Paragraph>
          <div>
            <Typography.Text strong>承诺人（主要负责人）</Typography.Text>
            <Input
              style={{ marginTop: 4 }}
              value={publisherName}
              placeholder="请输入主要负责人姓名"
              onChange={(e) => setPublisherName(e.target.value)}
            />
          </div>
        </Space>
      </Modal>

      {/* ── 新增信息卡弹窗 ── */}
      <Modal
        title={creatingType === 'commitment' ? '新增安全承诺信息卡' : '新增重大危险源信息卡'}
        open={creatingType !== null}
        onCancel={() => setCreatingType(null)}
        confirmLoading={savingCard}
        onOk={() => void addCard()}
        okText="创建"
        cancelText="取消"
      >
        <Space orientation="vertical" size={12} style={{ display: 'flex' }}>
          <Input
            value={newCard.title}
            placeholder="卡片标题"
            onChange={(e) => setNewCard((prev) => ({ ...prev, title: e.target.value }))}
          />
          <Input.TextArea
            rows={6}
            value={newCard.content}
            placeholder="卡片内容"
            onChange={(e) => setNewCard((prev) => ({ ...prev, content: e.target.value }))}
          />
        </Space>
      </Modal>
    </Space>
  )
}

export default SafetyCommitmentPanel
