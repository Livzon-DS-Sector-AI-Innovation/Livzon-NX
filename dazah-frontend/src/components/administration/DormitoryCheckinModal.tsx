'use client'

import { useState } from 'react'

import {
  Modal,
  Form,
  Input,
  Radio,
  Select,
  Button,
  Tag,
  Typography,
  Space,
  message,
} from 'antd'
import { RobotOutlined } from '@ant-design/icons'

import PlatformNotice from '@/components/shared/PlatformNotice'
import {
  recommendDormitoryRooms,
  submitDormitoryCheckin,
} from '@/lib/api/mapped-feishu'
import { getUserErrorMessage } from '@/lib/user-error'
import type {
  DormitoryCheckinInput,
  DormitoryRecommendationItem,
} from '@/types/administration'

const MODULE_CODE = 'administration'

interface DormitoryCheckinModalProps {
  open: boolean
  onClose: () => void
  /** 入住成功后通知父级刷新仪表盘与台账。 */
  onCheckedin: () => void
}

interface RecommendationState {
  items: DormitoryRecommendationItem[]
  message: string
  /** ai=模型推荐 / rule=规则兜底（LLM 不可用时的降级）。 */
  source: 'ai' | 'rule'
}

/** 新员工入住办理：填写信息 → AI 按住宿标准推荐房间 → 用户确认后回写飞书。 */
export default function DormitoryCheckinModal({
  open,
  onClose,
  onCheckedin,
}: DormitoryCheckinModalProps) {
  const [form] = Form.useForm<DormitoryCheckinInput>()
  const [recommendations, setRecommendations] = useState<RecommendationState | null>(null)
  const [selectedRoom, setSelectedRoom] = useState<string>('')
  const [recommending, setRecommending] = useState(false)
  const [submitting, setSubmitting] = useState(false)

  const resetRecommendation = () => {
    setRecommendations(null)
    setSelectedRoom('')
  }

  const handleRecommend = async () => {
    try {
      const values = await form.validateFields([
        'name',
        'gender',
        'department',
        'job_title',
        'shift_type',
      ])
      setRecommending(true)
      resetRecommendation()
      const result = await recommendDormitoryRooms(MODULE_CODE, values)
      setRecommendations({
        items: result.recommendations || [],
        message: result.message || '',
        source: result.source === 'ai' ? 'ai' : 'rule',
      })
      if (result.recommendations?.length === 1) {
        setSelectedRoom(result.recommendations[0].room_no)
      }
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(getUserErrorMessage(error, '获取推荐失败，请稍后重试'))
    } finally {
      setRecommending(false)
    }
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (!selectedRoom) {
        message.warning('请先选择要分配的房间（可先获取 AI 推荐）')
        return
      }
      setSubmitting(true)
      const result = await submitDormitoryCheckin(MODULE_CODE, {
        ...values,
        room_no: selectedRoom,
      })
      message.success(
        result.synced
          ? `已办理入住：${result.room_no}（台账已同步）`
          : `已办理入住：${result.room_no}（台账将在数分钟内同步）`,
      )
      form.resetFields()
      resetRecommendation()
      onCheckedin()
      onClose()
    } catch (error: unknown) {
      if (error && typeof error === 'object' && 'errorFields' in error) return
      message.error(getUserErrorMessage(error, '办理入住失败，请稍后重试'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      title="新员工入住办理"
      open={open}
      onCancel={() => {
        onClose()
      }}
      width={680}
      footer={[
        <Button key="recommend" onClick={handleRecommend} loading={recommending}>
          <RobotOutlined /> 获取 AI 房间推荐
        </Button>,
        <Button
          key="submit"
          type="primary"
          onClick={handleSubmit}
          loading={submitting}
          disabled={!selectedRoom}
        >
          确认办理入住
        </Button>,
      ]}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={{ gender: '男', shift_type: '正常班', deposit_paid: '否', agreement_signed: '否' }}
        onValuesChange={(changed) => {
          // 岗位/性别变了，旧推荐可能不再成立
          if ('gender' in changed || 'job_title' in changed) resetRecommendation()
        }}
      >
        <div className="grid grid-cols-2 gap-x-4">
          <Form.Item name="name" label="姓名" rules={[{ required: true, message: '请输入姓名' }]}>
            <Input placeholder="员工姓名" maxLength={100} />
          </Form.Item>
          <Form.Item name="gender" label="性别" rules={[{ required: true, message: '请选择性别' }]}>
            <Radio.Group options={[{ label: '男', value: '男' }, { label: '女', value: '女' }]} />
          </Form.Item>
          <Form.Item name="employee_id" label="员工ID">
            <Input placeholder="选填" maxLength={100} />
          </Form.Item>
          <Form.Item name="phone" label="联系方式">
            <Input placeholder="选填" maxLength={100} />
          </Form.Item>
          <Form.Item name="department" label="部门">
            <Input placeholder="如 安全办 / 201车间" maxLength={100} />
          </Form.Item>
          <Form.Item name="job_title" label="岗位">
            <Input placeholder="如 主管 / 工艺员（用于匹配住宿标准）" maxLength={100} />
          </Form.Item>
          <Form.Item name="shift_type" label="倒班类型">
            <Select
              options={[{ label: '正常班', value: '正常班' }, { label: '倒班', value: '倒班' }]}
            />
          </Form.Item>
          <Form.Item name="address" label="居住地址">
            <Input placeholder="选填" maxLength={255} />
          </Form.Item>
          <Form.Item name="deposit_paid" label="押金是否缴纳">
            <Radio.Group options={[{ label: '是', value: '是' }, { label: '否', value: '否' }]} />
          </Form.Item>
          <Form.Item name="agreement_signed" label="是否签订协议">
            <Radio.Group options={[{ label: '是', value: '是' }, { label: '否', value: '否' }]} />
          </Form.Item>
          <Form.Item name="remark" label="备注" className="col-span-2">
            <Input placeholder="选填" maxLength={255} />
          </Form.Item>
        </div>
      </Form>

      {recommendations ? (
        <div className="mt-2 rounded border border-[var(--color-hairline)] p-3">
          <Space size={8} className="mb-2">
            <Typography.Text strong>推荐房间</Typography.Text>
            <Tag color={recommendations.source === 'ai' ? 'geekblue' : 'default'}>
              {recommendations.source === 'ai' ? 'AI 推荐' : '规则推荐'}
            </Tag>
            <Typography.Text type="secondary" className="text-xs">
              {recommendations.message}
            </Typography.Text>
          </Space>
          {recommendations.items.length === 0 ? (
            <PlatformNotice type="warning" title={recommendations.message || '没有符合条件的空床位房间'} />
          ) : (
            <Radio.Group
              value={selectedRoom}
              onChange={(event) => setSelectedRoom(event.target.value)}
              className="flex w-full flex-col gap-2"
            >
              {recommendations.items.map((item) => (
                <Radio key={item.room_no} value={item.room_no} className="items-start">
                  <Space size={6} wrap>
                    <Typography.Text strong>{item.room_no}</Typography.Text>
                    <Tag>{item.dorm_type || '未知类型'}</Tag>
                    <Tag>{item.room_type || '未知房型'}</Tag>
                    <Tag color="green">剩余 {item.vacant_beds} 床</Tag>
                    <Typography.Text type="secondary" className="text-xs">
                      {item.reason}
                    </Typography.Text>
                  </Space>
                </Radio>
              ))}
            </Radio.Group>
          )}
          <Typography.Text type="secondary" className="mt-2 block text-xs">
            推荐仅供参考：确认前请核对房间与人员信息，办理后记录写入飞书「员工住宿退宿清单」。
          </Typography.Text>
        </div>
      ) : null}
    </Modal>
  )
}
