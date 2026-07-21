import { ResearchPage } from '@/components/rd'
import { fetchResearchProjects } from '@/actions/rd'
import { ResearchProject } from '@/types/rd'

export const dynamic = 'force-dynamic'

export default async function RdProjectsPage() {
  let initialProjects: ResearchProject[] = []
  let initialTotal = 0

  try {
    const result = await fetchResearchProjects({ page: 1, page_size: 20 })
    initialProjects = result.items
    initialTotal = result.total
  } catch (error) {
    console.warn('研发项目加载失败:', error)
  }

  return <ResearchPage initialProjects={initialProjects} initialTotal={initialTotal} />
}
