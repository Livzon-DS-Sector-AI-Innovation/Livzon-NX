import { describe, expect, it } from 'vitest'

import {
  buildLLMConfigPayload,
  getNewLLMConfigFormValues,
  type LLMConfigFormValues,
} from './llmConfigForm'

const baseValues: LLMConfigFormValues = {
  config_name: '测试配置',
  api_base_url: 'https://llm.example/v1',
  api_key: 'test-key',
  model_name: 'test-model',
  temperature: 0.7,
  use_temperature: false,
  timeout_seconds: 120,
  enable_thinking: false,
  context_window_tokens: 200000,
  compress_threshold: 0.8,
  stream_output: true,
  is_active: true,
  notes: null,
}

describe('LLM config form values', () => {
  it('defaults new configurations to active with provider temperature', () => {
    expect(getNewLLMConfigFormValues()).toEqual({
      temperature: 0.1,
      use_temperature: false,
      timeout_seconds: 120,
      is_active: true,
    })
  })

  it('uses zero sentinel when the temperature override is disabled', () => {
    expect(buildLLMConfigPayload(baseValues)).toEqual(
      expect.objectContaining({ temperature: 0 }),
    )
    expect(buildLLMConfigPayload(baseValues)).not.toHaveProperty('use_temperature')
  })

  it('preserves the entered temperature when the override is enabled', () => {
    expect(
      buildLLMConfigPayload({ ...baseValues, use_temperature: true }),
    ).toEqual(expect.objectContaining({ temperature: 0.7 }))
  })
})
