import { expect, it } from 'vitest'
import { permissionActionResult } from './permission-action-result'

it('returns a serializable conflict without throwing a Server Action error', async () => {
  expect(await permissionActionResult(async () => new Response(JSON.stringify({ detail: '授权版本冲突' }), { status: 409 })))
    .toEqual({ ok: false, status: 409, message: '授权版本冲突' })
})
it('does not report malformed success as a successful save', async () => {
  expect(await permissionActionResult(async () => new Response('invalid JSON'))).toMatchObject({ ok: false, status: 502 })
})
it('hides internal upstream failures and network details', async () => {
  expect(await permissionActionResult(async () => new Response(JSON.stringify({ detail: 'private stack trace' }), { status: 500 })))
    .toEqual({ ok: false, status: 500, message: '权限服务暂时不可用，请稍后重试' })
  expect(await permissionActionResult(async () => { throw new Error('private host') }))
    .toEqual({ ok: false, status: 503, message: '暂时无法连接权限服务，请刷新确认是否已保存' })
})
