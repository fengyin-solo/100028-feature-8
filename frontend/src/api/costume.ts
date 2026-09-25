import { request } from '@/api/client'

const ENDPOINT = '/api/costume'

export interface CleaningRecord {
  id: number
  清洗日期: string
  清洗方式: string
  清洗说明?: string
  经办人?: string
  登记时间: string
}

export interface CostumeRow {
  id: number
  status: string
  pending?: boolean
  abnormal?: boolean
  服装编号: string
  服装名称: string
  角色归属: string
  尺码规格?: string
  造型师?: string
  使用场次?: string
  当前状态: string
  清洗记录: string
  清洗次数?: number
  清洗历史?: CleaningRecord[]
  归还时间?: string | null
}

export interface CostumeListPayload {
  items: CostumeRow[]
  total: number
  page: number
  size: number
}

export interface CostumeQuery {
  keyword?: string
  status?: string
}

export interface CleaningFormValues {
  清洗日期: string
  清洗方式: string
  清洗说明?: string
  经办人?: string
}

export interface ActionResponse<T> {
  ok: boolean
  message: string
  entry: T | null
  replayed: boolean
}

async function parseAction<T>(response: Response): Promise<ActionResponse<T>> {
  const payload = (await response.json()) as ActionResponse<T>
  return {
    ok: payload.ok,
    message: payload.message,
    entry: payload.entry,
    replayed: Boolean(payload.replayed),
  }
}

export async function fetchCostumes(query: CostumeQuery): Promise<CostumeListPayload> {
  const params = new URLSearchParams()
  params.set('page', '1')
  params.set('size', '200')
  if (query.keyword?.trim()) {
    params.set('keyword', query.keyword.trim())
  }
  if (query.status) {
    params.set('status', query.status)
  }
  const response = await request(`${ENDPOINT}?${params.toString()}`)
  if (!response.ok) {
    throw new Error('戏服列表读取失败')
  }
  return (await response.json()) as CostumeListPayload
}

export async function fetchCostumeDetail(id: number): Promise<CostumeRow> {
  const response = await request(`${ENDPOINT}/${id}`)
  if (response.status === 404) {
    throw new Error('该戏服不存在或已归档')
  }
  if (!response.ok) {
    throw new Error('戏服明细读取失败')
  }
  return (await response.json()) as CostumeRow
}

export async function submitCostumeAction(
  id: number,
  action: string,
  requestId: string,
): Promise<ActionResponse<CostumeRow>> {
  const response = await request(`${ENDPOINT}/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values: { action, request_id: requestId } }),
  })
  if (!response.ok) {
    throw new Error('服装造型动作未送达，请稍后重试')
  }
  return parseAction<CostumeRow>(response)
}

export async function fetchCleaningRecords(id: number): Promise<CleaningRecord[]> {
  const response = await request(`${ENDPOINT}/${id}/cleaning`)
  if (response.status === 404) {
    throw new Error('该戏服不存在或已归档')
  }
  if (!response.ok) {
    throw new Error('清洗记录读取失败')
  }
  const payload = (await response.json()) as { items: CleaningRecord[] }
  return payload.items ?? []
}

export async function submitCleaningRecord(
  id: number,
  values: CleaningFormValues,
  requestId: string,
): Promise<ActionResponse<CleaningRecord>> {
  const response = await request(`${ENDPOINT}/${id}/cleaning`, {
    method: 'POST',
    body: JSON.stringify({ values: { ...values, request_id: requestId } }),
  })
  if (!response.ok) {
    throw new Error('清洗记录未送达，请稍后重试')
  }
  return parseAction<CleaningRecord>(response)
}
