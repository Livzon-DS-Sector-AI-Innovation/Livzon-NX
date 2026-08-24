/** 候选人列表导航辅助函数 */

import type { Candidate } from '@/types/hr'

/** 保存候选人列表上下文到 sessionStorage，供详情页导航使用。 */
export function storeCandidateListContext(candidates: Candidate[], currentId: string) {
  const ids = candidates.map((c) => c.id)
  const currentIndex = ids.indexOf(currentId)
  sessionStorage.setItem(
    'candidate_list_context',
    JSON.stringify({ ids, currentIndex })
  )
}
