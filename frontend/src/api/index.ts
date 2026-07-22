import type {
  GenerateResult,
  GenerationJob,
  ImageUploadResult,
  Manager,
  Product,
  Report,
  ReportStatus,
  ValidationResult,
} from '../types'

export class ApiError extends Error {
  status: number
  detail: unknown
  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `请求失败（${status}）`)
    this.status = status
    this.detail = detail
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: init?.body && typeof init.body === 'string'
      ? { 'Content-Type': 'application/json', ...init.headers }
      : init?.headers,
  })
  if (!response.ok) {
    let detail: unknown = response.statusText
    try {
      const body = await response.json()
      detail = body.detail ?? body
    } catch { /* non-JSON response */ }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  managers: {
    list: () => request<Manager[]>('/api/managers?limit=200'),
    get: (id: number) => request<Manager>(`/api/managers/${id}`),
    create: (body: Partial<Manager>) => request<Manager>('/api/managers', json('POST', body)),
    update: (id: number, body: Partial<Manager>) => request<Manager>(`/api/managers/${id}`, json('PUT', body)),
    remove: (id: number) => request<void>(`/api/managers/${id}`, { method: 'DELETE' }),
  },
  products: {
    list: (managerId?: number) => request<Product[]>(`/api/products?limit=200${managerId ? `&manager_id=${managerId}` : ''}`),
    create: (body: Partial<Product>) => request<Product>('/api/products', json('POST', body)),
    update: (id: number, body: Partial<Product>) => request<Product>(`/api/products/${id}`, json('PUT', body)),
  },
  reports: {
    list: (filters: { managerId?: number; productId?: number; status?: ReportStatus } = {}) => {
      const params = new URLSearchParams({ limit: '200' })
      if (filters.managerId) params.set('manager_id', String(filters.managerId))
      if (filters.productId) params.set('product_id', String(filters.productId))
      if (filters.status) params.set('status', filters.status)
      return request<Report[]>(`/api/reports?${params}`)
    },
    get: (id: number) => request<Report>(`/api/reports/${id}`),
    create: (body: Partial<Report>) => request<Report>('/api/reports', json('POST', body)),
    update: (id: number, body: Partial<Report>) => request<Report>(`/api/reports/${id}`, json('PUT', body)),
    validate: (id: number) => request<ValidationResult>(`/api/reports/${id}/validate`, { method: 'POST' }),
    submit: (id: number) => request<Report>(`/api/reports/${id}/submit`, { method: 'POST' }),
    archive: (id: number) => request<Report>(`/api/reports/${id}/archive`, { method: 'POST' }),
    generate: (id: number) => request<GenerateResult>(`/api/reports/${id}/generate`, { method: 'POST' }),
    createGenerationJob: (id: number) => request<GenerationJob>(`/api/reports/${id}/generation-jobs`, { method: 'POST' }),
    getGenerationJob: (reportId: number, jobId: number) => request<GenerationJob>(`/api/reports/${reportId}/generation-jobs/${jobId}`),
    uploadImage: (id: number, field: string, file: File) => request<ImageUploadResult>(
      `/api/reports/${id}/images/${encodeURIComponent(field)}`,
      { method: 'POST', body: file, headers: { 'Content-Type': file.type, 'X-Filename': encodeURIComponent(file.name) } },
    ),
    removeImage: (id: number, field: string) => request<void>(`/api/reports/${id}/images/${encodeURIComponent(field)}`, { method: 'DELETE' }),
  },
}

export function apiMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (typeof error.detail === 'string') return error.detail
    const detail = error.detail as { message?: string; errors?: Array<{ message: string }> } | undefined
    return detail?.message || detail?.errors?.map((item) => item.message).join('；') || error.message
  }
  return error instanceof Error ? error.message : '未知错误'
}
