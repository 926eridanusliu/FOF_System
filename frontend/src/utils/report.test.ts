import { describe, expect, it } from 'vitest'
import { reactive } from 'vue'
import { cloneReportContent, fieldIsOptional, fieldIsRequired, fieldSection, formatTableOutput, getFields, getTableDefinitions, normalizeTableInput, productStrategyGroups, productStrategyLabel, selectedStrategyBranches, strategyOptions, tableApplies } from './report'

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

  it('matches the product strategy labels and ordering used by the Word cover', () => {
    expect(productStrategyGroups.map((group) => group.label)).toEqual([
      '股票多空策略', '相对价值策略', '债券策略', '管理期货策略', '', '',
    ])
    expect(productStrategyGroups.map((group) => group.keys.map((key) => productStrategyLabel[key]))).toEqual([
      ['指数增强', '股票量化选股', '股票主观多头', '宏观对冲'],
      ['市场中性', '期货及期权套利', '日内回转（T0）'],
      ['纯债', '债券增强', '债券复合', '可转债'],
      ['期货量化趋势', '期货主观'],
      ['复合策略'],
      ['其他投资策略（）'],
    ])
  })

  it('converts reactive report content into cloneable plain data', () => {
    const content = reactive({ investigator: '测试人员', nested: { enabled: true } })
    const cloned = cloneReportContent(content)

    expect(cloned).toEqual({ investigator: '测试人员', nested: { enabled: true } })
    expect(cloned).not.toBe(content)
    expect(() => structuredClone(cloned)).not.toThrow()
  })

  it('opens the quantitative questions for market neutral and T0', () => {
    const branches = Object.fromEntries(strategyOptions.map(([key, , branch]) => [key, branch]))
    expect(branches.cover_strategy_market_neutral).toBe('quant')
    expect(branches.cover_strategy_t0).toBe('quant')
  })

  it('supports the union of several product strategy branches', () => {
    const selected = new Set([
      'cover_strategy_stock_quant',
      'cover_strategy_market_neutral',
      'cover_strategy_futures_quant_trend',
      'cover_strategy_futures_options_arbitrage',
    ])
    const active = new Set(
      strategyOptions
        .filter(([key, , branch]) => selected.has(key) && Boolean(branch))
        .map(([, , branch]) => branch),
    )
    expect(active).toEqual(new Set(['quant', 'cta', 'option']))
  })

  it('marks every field required except prompts explicitly containing （如有）', () => {
    expect(fieldIsOptional({ prompt: '补充说明（如有）' })).toBe(true)
    expect(fieldIsRequired({ type: 'qa', prompt: '补充说明（如有）' })).toBe(false)
    expect(fieldIsRequired({ type: 'qa', prompt: '基本信息' })).toBe(true)
  })

  it('returns only branches selected by the current strategy values', () => {
    expect(selectedStrategyBranches({
      cover_strategy_stock_quant: true,
      cover_strategy_bond_pure: true,
      cover_strategy_futures_quant_trend: false,
    })).toEqual(new Set(['quant', 'bond']))
  })

  it('provides business labels and unlimited-row modes for every template table', () => {
    const privateTables = getTableDefinitions('private_fund')
    const licensedTables = getTableDefinitions('licensed_institution')
    expect(Object.keys(privateTables)).toHaveLength(12)
    expect(Object.keys(licensedTables)).toHaveLength(3)
    expect(privateTables['2'].title).toBe('管理人各部门员工数量及主要职能')
    expect(privateTables['2'].mode).toBe('dynamic')
    expect(privateTables['2'].columns.map((column) => column.label)).toEqual(['部门名称', '部门人数', '部门主要职能', '负责人'])
  })

  it('shows strategy-specific product tables only for selected strategies', () => {
    const tables = getTableDefinitions('private_fund')
    expect(tableApplies(tables['8'], { cover_strategy_stock_quant: true })).toBe(true)
    expect(tableApplies(tables['8'], { cover_strategy_bond_pure: true })).toBe(false)
    expect(tableApplies(tables['10'], { cover_strategy_bond_pure: true })).toBe(true)
  })

  it('normalizes imported percentages and common numeric units for direct entry', () => {
    expect(normalizeTableInput('13.51%', 'percent')).toBe('13.51')
    expect(normalizeTableInput('7.69％', 'percent')).toBe('7.69')
    expect(normalizeTableInput('11年', 'integer')).toBe('11')
    expect(normalizeTableInput('3人', 'integer')).toBe('3')
    expect(formatTableOutput('13.51', 'percent')).toBe('13.51%')
  })
})
