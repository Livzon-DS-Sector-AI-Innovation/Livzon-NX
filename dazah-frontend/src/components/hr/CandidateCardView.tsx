'use client'

import { useRouter } from 'next/navigation'
import { Card, Tag, Pagination, Spin, Empty, Popconfirm, Button } from 'antd'
import { UserOutlined, DeleteOutlined } from '@ant-design/icons'
import { Candidate } from '@/types/hr'
import { storeCandidateListContext } from './candidateHelpers'

interface CandidateCardViewProps {
  candidates: Candidate[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  onPageChange: (page: number, pageSize: number) => void
  onDelete: (id: string) => void
}

export default function CandidateCardView({
  candidates,
  total,
  page,
  pageSize,
  loading,
  onPageChange,
  onDelete,
}: CandidateCardViewProps) {
  const router = useRouter()

  const handleCardClick = (id: string) => {
    storeCandidateListContext(candidates, id)
    router.push(`/hr/recruitment/${id}`)
  }

  const fitLevelColors: Record<string, string> = {
    '非常满足': 'purple',
    '高': 'green',
    '中': 'orange',
    '低': 'red',
  }

  const interviewStatusColors: Record<string, string> = {
    '待安排': 'default',
    '已安排': 'processing',
    '已完成': 'blue',
    '通过': 'green',
    '未通过': 'red',
  }

  if (loading) {
    return (
      <div className="flex justify-center py-20">
        <Spin size="large" />
      </div>
    )
  }

  if (candidates.length === 0) {
    return <Empty description="暂无候选人数据" className="py-20" />
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {candidates.map((candidate) => (
          <Card
            key={candidate.id}
            hoverable
            onClick={() => handleCardClick(candidate.id)}
            className="cursor-pointer"
            bodyStyle={{ padding: '16px' }}
          >
            <div className="flex items-center gap-3 mb-3">
              <div className="w-10 h-10 rounded-full bg-gray-200 flex items-center justify-center">
                <UserOutlined className="text-lg text-gray-500" />
              </div>
              <div>
                <div className="font-medium text-base">{candidate.name}</div>
                <div className="text-sm text-gray-500">{candidate.job_position}</div>
              </div>
            </div>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500">联系方式</span>
                <span className="truncate max-w-[140px]">{candidate.contact || candidate.phone || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">邮箱</span>
                <span className="truncate max-w-[140px]">{candidate.email || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">学历</span>
                <span>{candidate.education || '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">工作年限</span>
                <span>{candidate.work_years != null ? `${candidate.work_years}年` : '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">技能匹配度</span>
                <span className="font-medium text-blue-600">{candidate.match_rate != null ? `${candidate.match_rate}%` : '-'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">简历评分</span>
                <span className="font-medium text-blue-600">{candidate.resume_score != null ? `${candidate.resume_score}分` : '-'}</span>
              </div>
            </div>
            <div className="mt-3 pt-3 border-t border-gray-100 flex items-center justify-between">
              <div className="flex gap-2">
                {candidate.fit_level && (
                  <Tag color={fitLevelColors[candidate.fit_level] || 'default'}>
                    符合度: {candidate.fit_level}
                  </Tag>
                )}
                {candidate.interview_status && (
                  <Tag color={interviewStatusColors[candidate.interview_status] || 'default'}>
                    {candidate.interview_status}
                  </Tag>
                )}
              </div>
              <Popconfirm
                title="确认删除"
                description={`确定要删除候选人「${candidate.name}」的简历吗？`}
                onConfirm={() => onDelete(candidate.id)}
                okText="删除"
                cancelText="取消"
                okButtonProps={{ danger: true }}
              >
                <Button
                  size="small"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={(e) => e.stopPropagation()}
                >
                  删除
                </Button>
              </Popconfirm>
            </div>
          </Card>
        ))}
      </div>
      <div className="flex justify-end">
        <Pagination
          current={page}
          pageSize={pageSize}
          total={total}
          showSizeChanger
          showTotal={(t) => `共 ${t} 条`}
          onChange={onPageChange}
        />
      </div>
    </div>
  )
}
