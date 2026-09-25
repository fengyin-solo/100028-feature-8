import { defineStore } from 'pinia'

import type { CleaningFormValues } from '@/api/costume'
import { clearDraft, loadDraft, saveDraft } from '@/utils/draftStorage'

const STORAGE_KEY = 'costume-draft:v1'
const DRAFT_VERSION = 1

export interface CleaningDraft extends CleaningFormValues {
  /** 清洗提交用的幂等键：同一件戏服未提交成功的表单共用同一个键，重复提交只落一条。 */
  requestId: string
}

interface DraftSnapshot {
  version: number
  filters: Record<string, string>
  processingId: number | null
  cleaningDrafts: Record<string, CleaningDraft>
  pendingActionKeys: Record<string, string>
  scrollY: number
}

interface CostumeDraftState extends Omit<DraftSnapshot, 'version'> {
  /** 草稿落盘失败时的提示，不随快照持久化。 */
  persistError: string
}

function emptySnapshot(): DraftSnapshot {
  return {
    version: DRAFT_VERSION,
    filters: {},
    processingId: null,
    cleaningDrafts: {},
    pendingActionKeys: {},
    scrollY: 0,
  }
}

function initialState(): CostumeDraftState {
  const stored = loadDraft<DraftSnapshot>(STORAGE_KEY)
  if (stored && stored.version === DRAFT_VERSION) {
    return {
      filters: { ...(stored.filters ?? {}) },
      processingId: typeof stored.processingId === 'number' ? stored.processingId : null,
      cleaningDrafts: { ...(stored.cleaningDrafts ?? {}) },
      pendingActionKeys: { ...(stored.pendingActionKeys ?? {}) },
      scrollY: typeof stored.scrollY === 'number' ? stored.scrollY : 0,
      persistError: '',
    }
  }
  return { ...emptySnapshot(), persistError: '' }
}

function snapshotOf(state: CostumeDraftState): DraftSnapshot {
  const cleaningDrafts: Record<string, CleaningDraft> = {}
  for (const [key, draft] of Object.entries(state.cleaningDrafts)) {
    cleaningDrafts[key] = { ...draft }
  }
  return {
    version: DRAFT_VERSION,
    filters: { ...state.filters },
    processingId: state.processingId,
    cleaningDrafts,
    pendingActionKeys: { ...state.pendingActionKeys },
    scrollY: state.scrollY,
  }
}

export const useCostumeDraftStore = defineStore('costumeDraft', {
  state: (): CostumeDraftState => initialState(),
  getters: {
    /** 是否有任何草稿内容，供页面提示「草稿已自动保存」。 */
    hasDraft: (state) =>
      Object.keys(state.filters).length > 0 ||
      state.processingId !== null ||
      Object.keys(state.cleaningDrafts).length > 0,
  },
  actions: {
    /** 把当前状态写进 localStorage；失败时只记提示，不回滚页面上的任何状态。 */
    persist() {
      const ok = saveDraft(STORAGE_KEY, snapshotOf(this.$state))
      this.persistError = ok ? '' : '草稿未能保存到本地，离开页面前请留意'
    },
    setFilters(filters: Record<string, string>) {
      this.filters = { ...filters }
      this.persist()
    },
    setProcessing(id: number | null) {
      this.processingId = id
      this.persist()
    },
    setScroll(y: number) {
      this.scrollY = Math.max(0, Math.round(y))
      this.persist()
    },
    /** 取某件戏服的清洗草稿；没有时新建一份（含幂等键）并立即落盘。 */
    ensureCleaningDraft(id: number): CleaningDraft {
      const key = String(id)
      const existing = this.cleaningDrafts[key]
      if (existing) {
        return existing
      }
      const draft: CleaningDraft = {
        requestId: crypto.randomUUID(),
        清洗日期: new Date().toISOString().slice(0, 10),
        清洗方式: '',
        清洗说明: '',
        经办人: '',
      }
      this.cleaningDrafts[key] = draft
      this.persist()
      return draft
    },
    updateCleaningDraft(id: number, patch: Partial<CleaningDraft>) {
      const draft = this.ensureCleaningDraft(id)
      Object.assign(draft, patch)
      this.persist()
    },
    removeCleaningDraft(id: number) {
      if (delete this.cleaningDrafts[String(id)]) {
        this.persist()
      }
    },
    /** 登记某件戏服某个动作本次提交的幂等键，重试沿用同一个键。 */
    rememberActionKey(id: number, action: string, requestId: string) {
      this.pendingActionKeys[`${id}:${action}`] = requestId
      this.persist()
    },
    actionKey(id: number, action: string): string | undefined {
      return this.pendingActionKeys[`${id}:${action}`]
    },
    clearActionKey(id: number, action: string) {
      if (delete this.pendingActionKeys[`${id}:${action}`]) {
        this.persist()
      }
    },
    /** 草稿与正式记录对账：列表里已经是目标状态的动作键、戏服已消失的清洗草稿都清掉。 */
    reconcileWithRows(rows: Array<{ id: number; status: string }>) {
      const byId = new Map(rows.map((row) => [row.id, row.status]))
      let changed = false
      const targets: Record<string, string> = {
        安排定妆: '已定妆',
        确认使用: '使用中',
        归还服装: '已归还',
      }
      for (const key of Object.keys(this.pendingActionKeys)) {
        const [idText, action] = key.split(':')
        const status = byId.get(Number(idText))
        if (status !== undefined && targets[action] === status) {
          delete this.pendingActionKeys[key]
          changed = true
        }
      }
      for (const idText of Object.keys(this.cleaningDrafts)) {
        if (!byId.has(Number(idText))) {
          delete this.cleaningDrafts[idText]
          changed = true
        }
      }
      if (changed) {
        this.persist()
      }
    },
    /** 清空全部本地草稿（不动服务端正式记录）。 */
    resetAll() {
      const fresh = emptySnapshot()
      this.filters = fresh.filters
      this.processingId = fresh.processingId
      this.cleaningDrafts = fresh.cleaningDrafts
      this.pendingActionKeys = fresh.pendingActionKeys
      this.scrollY = fresh.scrollY
      clearDraft(STORAGE_KEY)
      this.persistError = ''
    },
  },
})
