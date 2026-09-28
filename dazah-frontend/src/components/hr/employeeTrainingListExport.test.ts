import { describe, expect, it } from 'vitest'
import { exportErrorMessage } from './EmployeeTrainingListClient'

// 导出失败提示：后端统一响应 {code,message}，FastAPI 原生校验 {detail}，
// 其余一律回退通用文案（曾因只读 detail 把真实原因吞成「导出失败」）
describe('导出错误信息提取', () => {
  it('优先读取统一响应体的 message', () => {
    expect(
      exportErrorMessage({ code: 400, message: '101一车间 在筛选条件下暂无培训记录，无法导出' }),
    ).toBe('101一车间 在筛选条件下暂无培训记录，无法导出')
  })

  it('回退读取 FastAPI 校验错误的 detail', () => {
    expect(exportErrorMessage({ detail: 'department: Field required' })).toBe(
      'department: Field required',
    )
  })

  it('空对象/非对象/网络错误回退通用文案', () => {
    expect(exportErrorMessage({})).toBe('导出失败')
    expect(exportErrorMessage(null)).toBe('导出失败')
    expect(exportErrorMessage('网络中断')).toBe('导出失败')
  })

  it('非字符串 message 不采纳，避免渲染异常值', () => {
    expect(exportErrorMessage({ message: 123, detail: '有效信息' })).toBe('有效信息')
  })
})
