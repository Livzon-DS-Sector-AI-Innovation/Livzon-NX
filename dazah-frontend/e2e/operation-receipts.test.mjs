import { test } from 'node:test'
import assert from 'node:assert/strict'
import { EventEmitter } from 'node:events'
import { operationReceipts } from './operation-receipts.mjs'

const id = '10000000-0000-4000-8000-000000000001'
function response(statusCode = 200) {
  const result = new EventEmitter()
  result.statusCode = statusCode
  result.end = value => { result.body = JSON.parse(value); result.emit('finish') }
  return result
}

test('Action receipts can be queried via browser cookies and remain owner scoped', () => {
  const record = operationReceipts()
  const read = response()
  record({ method: 'GET', url: '/api/v1/quality/records', headers: { authorization: 'Bearer fixture-a', 'x-dazah-operation-id': id } }, read)
  read.end('{}')
  const lookup = response()
  assert.equal(record({ url: `/api/v1/system/operations/${id}`, headers: { cookie: 'auth_token=fixture-a' } }, lookup), true)
  assert.equal(lookup.body.receipts[0].method, 'GET')
  assert.equal(lookup.body.receipts[0].state, 'completed')
  assert.equal(JSON.stringify(lookup.body).includes('fixture-a'), false)
  const other = response()
  record({ url: `/api/v1/system/operations/${id}`, headers: { cookie: 'auth_token=fixture-b' } }, other)
  assert.equal(other.statusCode, 404)
})

test('partial writes remain distinguishable from confirmed reads', () => {
  const record = operationReceipts()
  for (const [method, status] of [['GET', 200], ['POST', 502]]) {
    const result = response(status)
    record({ method, url: '/api/v1/quality/records', headers: { authorization: 'Bearer fixture-a', 'x-dazah-operation-id': id } }, result)
    result.end('{}')
  }
  const lookup = response()
  record({ url: `/api/v1/system/operations/${id}`, headers: { authorization: 'Bearer fixture-a' } }, lookup)
  assert.deepEqual(lookup.body.receipts.map(item => [item.method, item.state]), [['GET', 'completed'], ['POST', 'unknown']])
})
