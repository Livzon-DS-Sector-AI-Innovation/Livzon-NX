import { afterEach, describe, expect, it, vi } from 'vitest'
import { triggerInspectionFeishuSync } from './inspection-feishu'

describe('triggerInspectionFeishuSync', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('returns per-table data on success', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            code: 200,
            data: { today: { synced: 3, total: 3 } },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    await expect(triggerInspectionFeishuSync()).resolves.toEqual({
      today: { synced: 3, total: 3 },
    })
  })

  it('reports readable error when server returns plain-text 500', async () => {
    // 服务端未处理异常时返回纯文本 body，不得当 JSON 解析后抛语法错误
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response('Internal Server Error', { status: 500 })),
    )
    await expect(triggerInspectionFeishuSync()).rejects.toThrow(
      '同步失败（HTTP 500）',
    )
  })

  it('surfaces backend business message on envelope error', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(
          JSON.stringify({ code: 400, message: '巡检飞书镜像同步未配置' }),
          { status: 400, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    )
    await expect(triggerInspectionFeishuSync()).rejects.toThrow(
      '巡检飞书镜像同步未配置',
    )
  })
})
