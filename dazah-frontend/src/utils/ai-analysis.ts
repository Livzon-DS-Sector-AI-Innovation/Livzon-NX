import { getServerApiBaseUrl } from '@/lib/server-api'
/**
 * AI Analysis utility for deviation analysis
 * Calls backend AI endpoint to analyze deviation descriptions
 */

export interface AiAnalysisResult {
  description: string;
  reason: string;
  riskAssessment: string;
  capaSuggestion: string;
}

const API_BASE_URL = getServerApiBaseUrl()
const AI_TIMEOUT_MS = 30000;

export async function analyzeDeviation(
  description: string,
): Promise<AiAnalysisResult | null> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), AI_TIMEOUT_MS);

    const response = await fetch(`${API_BASE_URL}/api/v1/quality/deviations/ai-analysis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ description }),
      signal: controller.signal,
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      throw new Error(`请求失败: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();
    if (result?.data) {
      return result.data;
    }
    return null;
  } catch (err) {
    if ((err instanceof Error ? err.name : '') === 'AbortError') {
      throw new Error(`AI分析超时（${AI_TIMEOUT_MS / 1000}秒）`);
    }
    throw new Error((err instanceof Error ? err.message : '') || 'AI分析失败');
  }
}
