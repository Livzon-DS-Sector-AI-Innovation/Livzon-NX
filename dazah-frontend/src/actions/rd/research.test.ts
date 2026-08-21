import { afterEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  revalidatePath: vi.fn(),
}))

vi.mock('next/cache', () => ({ revalidatePath: mocks.revalidatePath }))

import { createPilotWorkflow, createResearchProject, deleteResearchProject, startPilotWorkflow } from './research'

const API_BASE = process.env.API_BASE_URL || 'http://localhost:8000'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

describe('rd research actions', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.clearAllMocks()
  })

  it('creates a research project', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'p-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    const payload = { name: '工艺优化', stage: 'lab' }
    await createResearchProject(payload as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/research/projects`,
      expect.objectContaining({ method: 'POST', body: JSON.stringify(payload) }),
    )
  })

  it('deletes a research project', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await deleteResearchProject('p-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/research/projects/p-1`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('creates a pilot workflow', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: { id: 'wf-1' } }))
    vi.stubGlobal('fetch', fetchMock)

    await createPilotWorkflow({ project_id: 'p-1' } as never)
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/research/pilot/workflow`,
      expect.objectContaining({ method: 'POST' }),
    )
  })

  it('starts a pilot workflow', async () => {
    const fetchMock = vi.fn(() => jsonResponse({ code: 200, data: null }))
    vi.stubGlobal('fetch', fetchMock)

    await startPilotWorkflow('wf-1')
    expect(fetchMock).toHaveBeenCalledWith(
      `${API_BASE}/api/v1/research/pilot/workflow/wf-1/start`,
      expect.objectContaining({ method: 'POST' }),
    )
  })
})
