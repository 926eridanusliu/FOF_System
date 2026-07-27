import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'
import { cloneReportContent, fieldSection, getFields, strategyOptions } from './report'

describe('report manifest helpers', () => {
  it('uses the full backend manifest field sets', () => {
    expect(getFields('private_fund')).toHaveLength(376)
    expect(getFields('licensed_institution')).toHaveLength(69)
  })

  it('places standalone image bookmarks in their business sections', () => {
    expect(fieldSection({ bookmark: 'image_org_structure', type: 'image', prompt: '' })).toBe(1)
    expect(fieldSection({ bookmark: 'image_performance_comparison', type: 'image', prompt: '' })).toBe(2)
    expect(fieldSection({ bookmark: 'image_equity_structure', type: 'image', prompt: '' })).toBe(5)
  })

  it('maps CTA selections to the CTA dynamic branch', () => {
    const ctaKeys = strategyOptions.filter(([, , branch]) => branch === 'cta').map(([key]) => key)
    expect(ctaKeys).toEqual([
      'cover_strategy_futures_quant_trend',
      'cover_strategy_futures_discretionary',
    ])
  })

  it('converts reactive report content into cloneable plain data', () => {
    const content = reactive({ investigator: '测试人员', nested: { enabled: true } })
    const cloned = cloneReportContent(content)

    expect(cloned).toEqual({ investigator: '测试人员', nested: { enabled: true } })
    expect(cloned).not.toBe(content)
    expect(() => structuredClone(cloned)).not.toThrow()
  })
})
