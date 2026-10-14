const records = new Map()
const tinyScreenshot = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aK1cAAAAASUVORK5CYII=', 'base64')

export async function handleFeedbackRequest(request, response) {
  const url = new URL(request.url || '/', 'http://localhost')
  if (!/^\/api\/v1\/identity\/(me|admin)\/feedback(?:\/|$)/.test(url.pathname)) return false
  const token = (request.headers.authorization || '').replace('Bearer ', '') || request.headers.cookie?.match(/auth_token=([^;]+)/)?.[1] || ''
  const admin = url.pathname.includes('/admin/')
  const respond = (body, status = 200) => { response.statusCode = status; response.end(JSON.stringify(body)); return true }
  if (!token || (admin && token !== 'admin-no-page-grants')) return respond({ detail: '无权访问' }, 403)
  if (request.method === 'POST') {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    const body = Buffer.concat(chunks).toString('utf8')
    const field = (name) => body.match(new RegExp(`name="${name}"\r\n\r\n([^]*?)\r\n--`))?.[1] || ''
    if (field('description').includes('失败测试')) return respond({ detail: '模拟反馈服务暂不可用，请重试' }, 503)
    const id = field('feedback_id')
    if (!records.has(id)) records.set(id, {
      id, owner: token, reporter_name: 'CI 测试提交者', description: field('description'), occurred_at: field('occurred_at'), page_path: field('page_path'),
      status: 'pending', reply: '', version: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      screenshots: [{ id: '11111111-2222-3333-4444-555555555555', content_type: 'image/png' }],
    })
    return respond(records.get(id), 201)
  }
  const detailId = url.pathname.split('/')[6]
  if (request.method === 'PATCH') {
    const chunks = []
    for await (const chunk of request) chunks.push(chunk)
    const payload = JSON.parse(Buffer.concat(chunks).toString('utf8'))
    const record = records.get(detailId)
    if (!record) return respond({ detail: '反馈不存在' }, 404)
    if (record.version !== payload.version) return respond({ detail: '反馈已被更新' }, 409)
    Object.assign(record, payload, { version: record.version + 1, updated_at: new Date().toISOString() })
    return respond(record)
  }
  if (url.pathname.includes('/screenshots/')) {
    const record = records.get(detailId)
    if (!record || (!admin && record.owner !== token)) return respond({ detail: '截图不存在' }, 404)
    response.setHeader('Content-Type', 'image/png'); response.end(tinyScreenshot); return true
  }
  const owned = [...records.values()].filter((record) => admin || record.owner === token)
  const filtered = owned.filter((record) => !url.searchParams.get('status') || record.status === url.searchParams.get('status'))
  const page = Number(url.searchParams.get('page') || 1)
  const pageSize = Number(url.searchParams.get('page_size') || 10)
  return respond({ items: filtered.slice((page - 1) * pageSize, page * pageSize), total: filtered.length,
    pending_count: owned.filter((record) => record.status === 'pending').length, page, page_size: pageSize })
}
