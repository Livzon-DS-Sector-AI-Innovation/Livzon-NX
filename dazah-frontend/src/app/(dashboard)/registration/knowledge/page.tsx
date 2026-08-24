import {
  fetchKnowledgeArticlesServer,
  fetchKnowledgeCategoriesServer,
  fetchKnowledgeOverviewServer,
} from '@/lib/api/server/registration'
import { KnowledgeBasePage } from '@/components/registration'

export const dynamic = 'force-dynamic'

export default async function KnowledgePage() {
  const [articles, categories, overview] = await Promise.all([
    fetchKnowledgeArticlesServer(),
    fetchKnowledgeCategoriesServer(),
    fetchKnowledgeOverviewServer(),
  ])

  return <KnowledgeBasePage articles={articles} categories={categories} overview={overview} />
}
