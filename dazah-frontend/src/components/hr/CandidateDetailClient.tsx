'use client'

import { useState, useEffect, useRef, useCallback } from 'react'
import { useRouter } from 'next/navigation'
import { App, Button, Descriptions, Tag, Input, Select, Modal } from 'antd'
import { ArrowLeftOutlined, ArrowUpOutlined, ArrowDownOutlined, EditOutlined, SaveOutlined, CloseOutlined, FilePdfOutlined, FileWordOutlined, EyeOutlined, SendOutlined } from '@ant-design/icons'
import { Candidate } from '@/types/hr'
import { updateCandidateAction, sendCandidateNoticeAction } from '@/actions/hr'

interface CandidateDetailClientProps {
  candidate: Candidate
}

const FIT_LEVEL_OPTIONS = [
  { value: '非常满足', label: '非常满足' },
  { value: '高', label: '高' },
  { value: '中', label: '中' },
  { value: '低', label: '低' },
]

const INTERVIEW_STATUS_OPTIONS = [
  { value: '待安排', label: '待安排' },
  { value: '已安排', label: '已安排' },
  { value: '已完成', label: '已完成' },
  { value: '通过', label: '通过' },
  { value: '未通过', label: '未通过' },
]

const EDUCATION_OPTIONS = [
  { value: '大专', label: '大专' },
  { value: '本科', label: '本科' },
  { value: '硕士', label: '硕士' },
  { value: '博士', label: '博士' },
  { value: '其他', label: '其他' },
]

export default function CandidateDetailClient({ candidate }: CandidateDetailClientProps) {
  const { message } = App.useApp()
  const router = useRouter()
  const [navContext, setNavContext] = useState<{ ids: string[]; currentIndex: number } | null>(null)
  const [isEditing, setIsEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [previewOpen, setPreviewOpen] = useState(false)
  const [docxLoading, setDocxLoading] = useState(false)
  const [sendingNotice, setSendingNotice] = useState(false)
  const docxContainerRef = useRef<HTMLDivElement>(null)

  const renderDocx = useCallback(async () => {
    if (!previewOpen || !candidate.resume_attachment) return
    const isDocx = candidate.resume_attachment.type?.includes('wordprocessingml') ||
                   candidate.resume_attachment.name?.toLowerCase().endsWith('.docx')
    if (!isDocx) return

    setDocxLoading(true)
    try {
      const res = await fetch(`/api/v1/hr/candidates/${candidate.id}/resume-file`)
      if (!res.ok) throw new Error('Failed to fetch resume file')
      const blob = await res.blob()
      const { renderAsync } = await import('docx-preview')
      if (docxContainerRef.current) {
        docxContainerRef.current.innerHTML = ''
        await renderAsync(blob, docxContainerRef.current, undefined, {
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          useBase64URL: true,
        })
      }
    } catch (err) {
      console.error('DOCX preview error:', err)
    } finally {
      setDocxLoading(false)
    }
  }, [previewOpen, candidate.id, candidate.resume_attachment])

  useEffect(() => {
    if (previewOpen) {
      queueMicrotask(renderDocx)
    }
  }, [previewOpen, renderDocx])
  const [formData, setFormData] = useState({
    name: candidate.name || '',
    contact: candidate.contact || '',
    email: candidate.email || '',
    job_id: candidate.job_id || '',
    education: candidate.education || '',
    work_years: candidate.work_years ?? undefined as number | undefined,
    skills: (Array.isArray(candidate.skills) ? candidate.skills : typeof candidate.skills === 'string' ? candidate.skills.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean) : []) as string[],
    fit_level: candidate.fit_level || '',
    interview_status: candidate.interview_status || '',
    remark: candidate.remark || '',
  })

  useEffect(() => {
    const raw = sessionStorage.getItem('candidate_list_context')
    if (raw) {
      try {
        const parsed = JSON.parse(raw)
        if (parsed.ids?.includes(candidate.id)) {
          queueMicrotask(() => setNavContext(parsed))
        }
      } catch { /* ignore */ }
    }
  }, [candidate.id])

  const handlePrev = () => {
    if (!navContext) return
    const prevIndex = navContext.currentIndex - 1
    const prevId = navContext.ids[prevIndex]
    if (prevId) {
      sessionStorage.setItem('candidate_list_context', JSON.stringify({ ...navContext, currentIndex: prevIndex }))
      router.push(`/hr/recruitment/${prevId}`)
    }
  }
  const handleNext = () => {
    if (!navContext) return
    const nextIndex = navContext.currentIndex + 1
    const nextId = navContext.ids[nextIndex]
    if (nextId) {
      sessionStorage.setItem('candidate_list_context', JSON.stringify({ ...navContext, currentIndex: nextIndex }))
      router.push(`/hr/recruitment/${nextId}`)
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await updateCandidateAction(candidate.id, {
        name: formData.name || undefined,
        contact: formData.contact || undefined,
        email: formData.email || undefined,
        job_id: formData.job_id || undefined,
        education: formData.education || undefined,
        work_years: formData.work_years,
        skills: formData.skills.length > 0 ? formData.skills : undefined,
        fit_level: formData.fit_level || undefined,
        interview_status: formData.interview_status || undefined,
        remark: formData.remark || undefined,
      })
      message.success('保存成功')
      setIsEditing(false)
      router.refresh()
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleCancel = () => {
    setFormData({
      name: candidate.name || '',
      contact: candidate.contact || '',
      email: candidate.email || '',
      job_id: candidate.job_id || '',
      education: candidate.education || '',
      work_years: candidate.work_years ?? undefined,
      skills: (Array.isArray(candidate.skills) ? candidate.skills : typeof candidate.skills === 'string' ? candidate.skills.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean) : []) as string[],
      fit_level: candidate.fit_level || '',
      interview_status: candidate.interview_status || '',
      remark: candidate.remark || '',
    })
    setIsEditing(false)
  }

  const handleSendNotice = async (sceneCode: string) => {
    setSendingNotice(true)
    try {
      const result = await sendCandidateNoticeAction(candidate.id, sceneCode)
      const data = (result.data || {}) as {
        email_sent?: boolean
        email_recipient?: string
        email_error?: string
        feishu_sent?: boolean
        feishu_recipients?: string[]
        feishu_errors?: string[]
      }
      const parts: string[] = []
      if (data.email_sent) parts.push(`邮件已发送至 ${data.email_recipient}`)
      else if (data.email_error) parts.push(`邮件发送失败: ${data.email_error}`)
      if (data.feishu_sent) parts.push(`飞书已发送至 ${data.feishu_recipients?.length || 0} 人`)
      if (data.feishu_errors?.length) parts.push(`飞书部分失败: ${data.feishu_errors.length} 人`)
      message.success(parts.join('；') || '发送完成')
    } catch (err) {
      message.error((err instanceof Error ? err.message : '') || '发送失败')
    } finally {
      setSendingNotice(false)
    }
  }

  const fitColors: Record<string, string> = { '非常满足': 'purple', '高': 'green', '中': 'orange', '低': 'red' }
  const statusColors: Record<string, string> = { '待安排': 'default', '已安排': 'processing', '已完成': 'blue', '通过': 'green', '未通过': 'red' }

  const skillsStr = Array.isArray(formData.skills) ? formData.skills.join(', ') : formData.skills

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <Button icon={<ArrowLeftOutlined />} onClick={() => router.push('/hr/recruitment')}>返回列表</Button>
        {navContext && (
          <>
            <Button icon={<ArrowUpOutlined />} onClick={handlePrev} disabled={navContext.currentIndex <= 0}>上一条</Button>
            <Button icon={<ArrowDownOutlined />} onClick={handleNext} disabled={navContext.currentIndex >= navContext.ids.length - 1}>下一条</Button>
          </>
        )}
        <div className="flex-1" />
        {isEditing ? (
          <>
            <Button icon={<SaveOutlined />} type="primary" loading={saving} onClick={handleSave}>保存修改</Button>
            <Button icon={<CloseOutlined />} onClick={handleCancel} disabled={saving}>取消</Button>
          </>
        ) : (
          <>
            <Button icon={<EditOutlined />} onClick={() => setIsEditing(true)}>编辑</Button>
            {candidate.interview_status === '已安排' && (
              <Button icon={<SendOutlined />} loading={sendingNotice} onClick={() => handleSendNotice('interview_notice')}>
                发送面试通知
              </Button>
            )}
            {candidate.interview_status === '通过' && (
              <Button type="primary" icon={<SendOutlined />} loading={sendingNotice} onClick={() => handleSendNotice('offer_notice')}>
                发送Offer
              </Button>
            )}
          </>
        )}
      </div>

      <div className="bg-white rounded-xl border border-[#e5e3df] p-6">
        <div className="flex items-center gap-3 mb-6">
          <h2 className="text-xl font-semibold">{candidate.name}</h2>
          {candidate.fit_level && <Tag color={fitColors[candidate.fit_level] || 'default'}>{candidate.fit_level}</Tag>}
          {candidate.interview_status && <Tag color={statusColors[candidate.interview_status] || 'default'}>{candidate.interview_status}</Tag>}
        </div>

        <Descriptions bordered size="small" column={3} labelStyle={{ width: 120, fontWeight: 500 }}>
          <Descriptions.Item label="姓名">
            {isEditing ? <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} /> : (candidate.name || '-')}
          </Descriptions.Item>
          <Descriptions.Item label="应聘职位">
            {isEditing ? <Input value={formData.job_id} onChange={(e) => setFormData({ ...formData, job_id: e.target.value })} placeholder="职位关联ID" /> : (candidate.job_position || candidate.job_id || '-')}
          </Descriptions.Item>
          <Descriptions.Item label="联系方式">
            {isEditing ? <Input value={formData.contact} onChange={(e) => setFormData({ ...formData, contact: e.target.value })} placeholder="手机号" /> : (candidate.contact || '-')}
          </Descriptions.Item>
          <Descriptions.Item label="邮箱">
            {isEditing ? <Input value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} /> : (candidate.email || '-')}
          </Descriptions.Item>
          <Descriptions.Item label="学历">
            {isEditing ? <Select style={{ width: '100%' }} value={formData.education || undefined} onChange={(v) => setFormData({ ...formData, education: v || '' })} options={EDUCATION_OPTIONS} allowClear /> : (<Tag color="blue">{candidate.education || '-'}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label="工作经验(年)">
            {isEditing ? <Input type="number" value={formData.work_years} onChange={(e) => setFormData({ ...formData, work_years: e.target.value ? Number(e.target.value) : undefined })} /> : (candidate.work_years != null ? candidate.work_years : '-')}
          </Descriptions.Item>
          <Descriptions.Item label="技能标签" span={2}>
            {isEditing ? (
              <Input value={skillsStr} onChange={(e) => setFormData({ ...formData, skills: e.target.value ? e.target.value.split(/[,，]/).map((s: string) => s.trim()).filter(Boolean) : [] })} placeholder="逗号分隔" />
            ) : (
              <div className="flex gap-1 flex-wrap">{skillsStr ? skillsStr.split(', ').map((s, i) => <Tag key={i}>{s.trim()}</Tag>) : '-'}</div>
            )}
          </Descriptions.Item>
          <Descriptions.Item label="技能匹配度">{candidate.match_rate != null ? `${candidate.match_rate}%` : '-'}</Descriptions.Item>
          <Descriptions.Item label="简历评分">{candidate.resume_score != null ? `${candidate.resume_score}分` : '-'}</Descriptions.Item>
          <Descriptions.Item label="招聘符合程度">
            {isEditing ? <Select style={{ width: '100%' }} value={formData.fit_level || undefined} onChange={(v) => setFormData({ ...formData, fit_level: v || '' })} options={FIT_LEVEL_OPTIONS} allowClear /> : (<Tag color={fitColors[candidate.fit_level || ''] || 'default'}>{candidate.fit_level || '-'}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label="面试状态">
            {isEditing ? <Select style={{ width: '100%' }} value={formData.interview_status || undefined} onChange={(v) => setFormData({ ...formData, interview_status: v || '' })} options={INTERVIEW_STATUS_OPTIONS} allowClear /> : (<Tag color={statusColors[candidate.interview_status || ''] || 'default'}>{candidate.interview_status || '-'}</Tag>)}
          </Descriptions.Item>
          <Descriptions.Item label="简历附件">
            {candidate.resume_attachment ? (
              <Button
                type="link"
                size="small"
                icon={candidate.resume_attachment.type?.includes('pdf') ? <FilePdfOutlined /> : <FileWordOutlined />}
                onClick={() => setPreviewOpen(true)}
                style={{ padding: 0, height: 'auto' }}
              >
                <span className="text-blue-600 hover:text-blue-800">{candidate.resume_attachment.name}</span>
                <EyeOutlined className="ml-1 text-gray-400" />
              </Button>
            ) : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="备注" span={3}>
            {isEditing ? <Input.TextArea value={formData.remark} onChange={(e) => setFormData({ ...formData, remark: e.target.value })} rows={4} /> : (candidate.remark || '-')}
          </Descriptions.Item>
        </Descriptions>

        {candidate.remark && (
          <div className="mt-6">
            <h3 className="text-lg font-medium mb-3">AI 匹配度报告</h3>
            <div className="bg-gray-50 rounded-lg p-4 text-sm leading-relaxed whitespace-pre-wrap">{candidate.remark}</div>
          </div>
        )}
      </div>

      {/* Resume Preview Modal */}
      <Modal
        title={candidate.resume_attachment?.name || '简历预览'}
        open={previewOpen}
        onCancel={() => setPreviewOpen(false)}
        footer={null}
        width="90vw"
        style={{ top: 20 }}
        styles={{ body: { height: '80vh', padding: 0 } }}
        destroyOnHidden
      >
        {candidate.resume_attachment && (
          candidate.resume_attachment.type?.includes('pdf') ? (
            <iframe
              src={`/api/v1/hr/candidates/${candidate.id}/resume-file`}
              style={{ width: '100%', height: '100%', border: 'none' }}
              title="简历预览"
            />
          ) : (
            <div className="w-full h-full overflow-auto bg-white">
              {docxLoading && (
                <div className="flex items-center justify-center h-full">
                  <span className="text-gray-400">加载中...</span>
                </div>
              )}
              <div ref={docxContainerRef} className="docx-preview-container" />
            </div>
          )
        )}
      </Modal>
    </div>
  )
}
