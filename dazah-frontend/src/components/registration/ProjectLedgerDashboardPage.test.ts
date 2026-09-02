import { describe, expect, it } from 'vitest'

import { checkSuccess } from '@/components/registration/ProjectLedgerDashboardPage'

const base = {
  certificateStatus: '',
  certificateName: '',
  resultText: '',
  historyText: '',
  activityType: '',
}

describe('checkSuccess 申报台账成功判定', () => {
  it('证书状态为"是"直接判成功', () => {
    expect(checkSuccess({ ...base, certificateStatus: '是' })).toBe(true)
  })

  it('有证书名称直接判成功', () => {
    expect(checkSuccess({ ...base, certificateName: 'GMP 证书' })).toBe(true)
  })

  it('明确成功表述判成功', () => {
    expect(checkSuccess({ ...base, resultText: '已获批，批准文号已下发' })).toBe(
      true
    )
    expect(checkSuccess({ ...base, resultText: '注册成功' })).toBe(true)
    expect(checkSuccess({ ...base, resultText: '审评通过' })).toBe(true)
  })

  it('"待批准/不批准/未通过"等不得判成功（旧正则的误报场景）', () => {
    expect(checkSuccess({ ...base, resultText: '待批准' })).toBe(false)
    expect(checkSuccess({ ...base, resultText: '不批准' })).toBe(false)
    expect(checkSuccess({ ...base, resultText: '未通过审评' })).toBe(false)
    expect(
      checkSuccess({ ...base, resultText: '拟批准，等待国家局签发' })
    ).toBe(false)
  })

  it('"计划接受 GMP 检查"不得因 gmp 关键词判成功', () => {
    expect(
      checkSuccess({ ...base, activityType: '计划接受 GMP 检查' })
    ).toBe(false)
    expect(
      checkSuccess({ ...base, historyText: '预计 2026 年现场核查' })
    ).toBe(false)
  })

  it('空文本不判成功', () => {
    expect(checkSuccess(base)).toBe(false)
  })

  it('无否定词且含明确成功词的混合文本判成功', () => {
    expect(
      checkSuccess({ ...base, resultText: '完成现场核查', historyText: '已获批' })
    ).toBe(true)
  })
})
