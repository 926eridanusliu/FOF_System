import privateManifestData from '../data/private_fund_manifest.json'
import licensedManifestData from '../data/licensed_institution_manifest.json'
import tableDefinitionsData from '../data/table_definitions.json'
import { toRaw } from 'vue'
import type { Manifest, ManifestField, ReportStatus, TableDefinition, TableInputType, TemplateType } from '../types'

const manifests: Record<TemplateType, Manifest> = {
  private_fund: privateManifestData as Manifest,
  licensed_institution: licensedManifestData as Manifest,
}

export const getManifest = (type: TemplateType) => manifests[type]
export const getFields = (type: TemplateType) => getManifest(type).bookmarks
export const getTableDefinitions = (type: TemplateType): Record<string, TableDefinition> =>
  (tableDefinitionsData as Record<TemplateType, Record<string, TableDefinition>>)[type]

export function tableApplies(definition: TableDefinition, content: Record<string, unknown>): boolean {
  return !definition.strategy_keys?.length || definition.strategy_keys.some((key) => Boolean(content[key]))
}

export function normalizeTableInput(value: unknown, inputType: TableInputType): unknown {
  if (typeof value !== 'string') return value
  const text = value.trim().replace(/,/g, '')
  if (inputType === 'percent') return text.replace(/[％%]\s*$/, '').trim()
  if (inputType === 'integer' || inputType === 'number') {
    const match = text.match(/^([+-]?\d+(?:\.\d+)?)\s*(?:人|年|次|只|家|亿元|亿)?$/)
    return match ? match[1] : text
  }
  return value
}

export function formatTableOutput(value: unknown, inputType: TableInputType): unknown {
  if (value === '' || value == null) return ''
  const normalized = normalizeTableInput(value, inputType)
  return inputType === 'percent' ? `${normalized}%` : normalized
}

export function cloneReportContent<T extends Record<string, unknown>>(content: T): T {
  return structuredClone(toRaw(content))
}

export function fieldSection(field: ManifestField): number | undefined {
  const standaloneImages: Record<string, number> = {
    image_org_structure: 1,
    image_performance_comparison: 2,
    image_equity_structure: 5,
  }
  if (standaloneImages[field.bookmark]) return standaloneImages[field.bookmark]
  if (field.section) return field.section
  const match = field.bookmark.match(/qa_section(\d+)/)
  return match ? Number(match[1]) : undefined
}

export const statusLabel: Record<ReportStatus, string> = {
  draft: '草稿', submitted: '已提交', archived: '已归档',
}

export const templateLabel: Record<TemplateType, string> = {
  private_fund: '附件 1-1 · 私募基金',
  licensed_institution: '附件 1-2 · 持牌金融机构',
}

export const strategyOptions = [
  ['cover_strategy_stock_index_enhanced', '指数增强', 'quant'],
  ['cover_strategy_stock_quant', '股票量化选股', 'quant'],
  ['cover_strategy_stock_discretionary', '股票主观多头', ''],
  ['cover_strategy_macro_hedge', '宏观对冲', ''],
  ['cover_strategy_market_neutral', '市场中性', 'quant'],
  ['cover_strategy_futures_options_arbitrage', '期货及期权套利', 'option'],
  ['cover_strategy_t0', '日内回转（T0）', 'quant'],
  ['cover_strategy_bond_pure', '纯债', 'bond'],
  ['cover_strategy_bond_enhanced', '债券增强', 'bond'],
  ['cover_strategy_bond_composite', '债券复合', 'bond'],
  ['cover_strategy_convertible_bond', '可转债', 'bond'],
  ['cover_strategy_futures_quant_trend', '期货量化趋势', 'cta'],
  ['cover_strategy_futures_discretionary', '期货主观', 'cta'],
  ['cover_strategy_composite', '复合策略', ''],
] as const

export const OTHER_PRODUCT_STRATEGY_KEY = 'cover_strategy_other'

export const productStrategyGroups = [
  { label: '股票多空策略', keys: ['cover_strategy_stock_index_enhanced', 'cover_strategy_stock_quant', 'cover_strategy_stock_discretionary', 'cover_strategy_macro_hedge'] },
  { label: '相对价值策略', keys: ['cover_strategy_market_neutral', 'cover_strategy_futures_options_arbitrage', 'cover_strategy_t0'] },
  { label: '债券策略', keys: ['cover_strategy_bond_pure', 'cover_strategy_bond_enhanced', 'cover_strategy_bond_composite', 'cover_strategy_convertible_bond'] },
  { label: '管理期货策略', keys: ['cover_strategy_futures_quant_trend', 'cover_strategy_futures_discretionary'] },
  { label: '', keys: ['cover_strategy_composite'] },
  { label: '', keys: [OTHER_PRODUCT_STRATEGY_KEY] },
] as const

export const productStrategyLabel: Record<string, string> = {
  ...Object.fromEntries(strategyOptions.map(([key, label]) => [key, label])),
  [OTHER_PRODUCT_STRATEGY_KEY]: '其他投资策略（）',
}

export const branchLabels = { quant: '量化策略', cta: 'CTA 策略', bond: '债券策略', option: '期权策略' }

export function fieldIsOptional(field: Pick<ManifestField, 'prompt'>): boolean {
  return /[（(]如有[）)]/.test(field.prompt || '')
}

export function fieldIsRequired(field: Pick<ManifestField, 'type' | 'prompt'>): boolean {
  return field.type !== 'cover_checkbox' && !fieldIsOptional(field)
}

export function selectedStrategyBranches(content: Record<string, unknown>): Set<string> {
  return new Set(
    strategyOptions
      .filter(([key, , branch]) => Boolean(branch) && Boolean(content[key]))
      .map(([, , branch]) => branch),
  )
}

export function imageUrl(reportId: number, value: unknown): string | undefined {
  if (!value || typeof value !== 'object') return undefined
  const path = String((value as { path?: string }).path || '')
  const filename = path.split('/').pop()
  return filename ? `/api/files/images/${reportId}/${encodeURIComponent(filename)}` : undefined
}
