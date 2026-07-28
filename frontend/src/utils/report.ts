import privateManifestData from '../data/private_fund_manifest.json'
import licensedManifestData from '../data/licensed_institution_manifest.json'
import { toRaw } from 'vue'
import type { Manifest, ManifestField, ReportStatus, TemplateType } from '../types'

const manifests: Record<TemplateType, Manifest> = {
  private_fund: privateManifestData as Manifest,
  licensed_institution: licensedManifestData as Manifest,
}

export const getManifest = (type: TemplateType) => manifests[type]
export const getFields = (type: TemplateType) => getManifest(type).bookmarks

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
  ['cover_strategy_futures_options_arbitrage', '期货期权套利', 'option'],
  ['cover_strategy_t0', 'T0', 'quant'],
  ['cover_strategy_bond_pure', '纯债', 'bond'],
  ['cover_strategy_bond_enhanced', '固收增强', 'bond'],
  ['cover_strategy_bond_composite', '固收复合', 'bond'],
  ['cover_strategy_convertible_bond', '可转债', 'bond'],
  ['cover_strategy_futures_quant_trend', '量化 CTA', 'cta'],
  ['cover_strategy_futures_discretionary', '主观 CTA', 'cta'],
  ['cover_strategy_composite', '复合策略', ''],
] as const

export const branchLabels = { quant: '量化策略', cta: 'CTA 策略', bond: '债券策略', option: '期权策略' }

export function imageUrl(reportId: number, value: unknown): string | undefined {
  if (!value || typeof value !== 'object') return undefined
  const path = String((value as { path?: string }).path || '')
  const filename = path.split('/').pop()
  return filename ? `/api/files/images/${reportId}/${encodeURIComponent(filename)}` : undefined
}
