// Test backend metadata contract; no request bodies or credentials are recorded.
export function operationReceipts() {
  const groups = new Map()
  return (request, response) => {
    const bearer = request.headers.authorization?.replace(/^Bearer /, '')
    const cookie = request.headers.cookie?.match(/(?:^|;\s*)auth_token=([^;]+)/)?.[1]
    const owner = bearer || cookie
    const path = new URL(request.url, 'http://fixture').pathname
    const id = request.headers['x-dazah-operation-id']
    const lookup = path.match(/^\/api\/v1\/system\/operations\/([a-f0-9-]{36})$/)
    if (lookup) {
      const receipts = owner && groups.get(`${owner}:${lookup[1]}`)
      response.statusCode = receipts ? 200 : 404
      response.end(JSON.stringify(receipts
        ? { operation_id: lookup[1], receipts: [...receipts.values()] }
        : { detail: '未找到操作记录，不能据此判断操作未执行' }))
      return true
    }
    if (owner && typeof id === 'string' && /^[a-f0-9-]{36}$/.test(id) && path.startsWith('/api/v1/')) {
      response.once('finish', () => {
        const key = `${owner}:${id}`
        const receipts = groups.get(key) || new Map()
        const status = response.statusCode
        receipts.set(`${request.method}:${path}`, {
          method: request.method, path,
          state: status >= 200 && status < 300 ? 'completed' : status >= 400 && status < 500 ? 'rejected' : 'unknown',
          http_status: status, updated_at: Date.now() / 1000,
        })
        groups.set(key, receipts)
      })
    }
    return false
  }
}
