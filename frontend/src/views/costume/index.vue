<template>
  <section class="page" data-module="costume">
    <header class="page-head">
      <div>
        <h2>服装造型管理</h2>
        <p class="page-desc">维护戏服，围绕服装编号、服装名称、角色归属、尺码规格做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记戏服</button>
        <button class="btn" type="button" @click="exportRows">导出服装造型清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
      <span class="draft-state" :class="draftState">{{ draftStateText }}</span>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <template v-for="row in rows" :key="String(row.id)">
          <tr :class="{ 'row-active': activeEntryId === Number(row.id) }">
            <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
            <td class="row-actions">
              <button
                v-for="action in actions"
                :key="action"
                class="link"
                type="button"
                @click="runAction(action, row)"
              >
                {{ action }}
              </button>
              <button class="link" type="button" @click="toggleCleaning(row)">
                {{ activeEntryId === Number(row.id) ? '收起清洗' : '清洗登记' }}
              </button>
            </td>
          </tr>
          <tr v-if="activeEntryId === Number(row.id)" class="cleaning-panel">
            <td :colspan="columns.length + 1">
              <div class="cleaning-box">
                <label class="cleaning-editor">
                  <span>清洗记录（未提交部分已存入草稿，离开或刷新后可继续）</span>
                  <textarea
                    :value="cleaningDrafts[Number(row.id)]?.content ?? ''"
                    placeholder="填写本次清洗情况，提交后进入历史清洗记录"
                    @input="onCleaningInput(Number(row.id), ($event.target as HTMLTextAreaElement).value)"
                  ></textarea>
                </label>
                <div class="cleaning-actions">
                  <button
                    class="btn primary"
                    type="button"
                    :disabled="submittingIds.has(Number(row.id))"
                    @click="submitCleaning(Number(row.id))"
                  >
                    {{ submittingIds.has(Number(row.id)) ? '提交中…' : '提交清洗记录' }}
                  </button>
                  <span v-if="cleaningDrafts[Number(row.id)]?.content" class="draft-state">未提交</span>
                </div>
                <div class="cleaning-history-block">
                  <span class="cleaning-history-title">历史清洗记录</span>
                  <ul v-if="cleaningHistory[Number(row.id)]?.length" class="cleaning-history">
                    <li v-for="record in cleaningHistory[Number(row.id)]" :key="record.seq">
                      #{{ record.seq }} {{ record.created_at }} — {{ record.content }}
                    </li>
                  </ul>
                  <p v-else class="cleaning-history-empty">暂无历史清洗记录</p>
                </div>
              </div>
            </td>
          </tr>
        </template>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无服装造型数据，可先登记戏服</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条服装造型记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>
type CleaningRecord = { seq: number; content: string; created_at: string }
type PendingCleaning = { entry_id: number; content: string; submission_id: string }

const ENDPOINT = '/api/costume'
const columns = ["服装编号", "服装名称", "角色归属", "尺码规格", "造型师", "使用场次", "当前状态", "清洗记录"]
const actions = ["安排定妆", "确认使用", "归还服装"]
const statuses = ["待定妆", "已定妆", "使用中", "已归还"]
const stats = [{"label": "待定妆服装", "value": 0}, {"label": "使用中服装", "value": 0}, {"label": "待清洗服装", "value": 0}]

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

// 草稿三要素：当前筛选、正在处理的戏服、未提交的清洗记录。
const activeEntryId = ref<number | null>(null)
const cleaningDrafts = ref<Record<number, PendingCleaning>>({})
const cleaningHistory = ref<Record<number, CleaningRecord[]>>({})
const submittingIds = ref<Set<number>>(new Set())
const draftState = ref<'' | 'saving' | 'saved' | 'failed'>('')

const draftStateText = computed(() => {
  if (draftState.value === 'saving') return '草稿保存中…'
  if (draftState.value === 'saved') return '草稿已保存'
  if (draftState.value === 'failed') return '草稿保存失败，本地内容已保留'
  return ''
})

function newSubmissionId(id: number) {
  return `clean-${id}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// 任何草稿要素变化都防抖落一次草稿；保存失败只提示，绝不清空本地编辑内容。
let draftTimer: number | undefined
function scheduleDraftSave() {
  window.clearTimeout(draftTimer)
  draftTimer = window.setTimeout(() => void saveDraft(), 400)
}

async function saveDraft() {
  draftState.value = 'saving'
  try {
    const response = await request(`${ENDPOINT}/draft`, {
      method: 'PUT',
      body: JSON.stringify({
        values: {
          filters: filters.value,
          active_entry_id: activeEntryId.value,
          // 空内容的编辑框不算未提交记录，不进草稿
          pending_cleaning: Object.values(cleaningDrafts.value).filter((item) => item.content.trim()),
        },
      }),
    })
    const result = await response.json()
    if (!response.ok || result.ok === false) {
      throw new Error(result.message || result.detail || '草稿保存失败')
    }
    draftState.value = 'saved'
  } catch (error) {
    draftState.value = 'failed'
    errorMessage.value = error instanceof Error ? error.message : '草稿保存失败，本地内容已保留'
  }
}

watch([filters, activeEntryId, cleaningDrafts], scheduleDraftSave, { deep: true })

async function restoreDraft() {
  try {
    const response = await request(`${ENDPOINT}/draft`)
    if (!response.ok) return
    const draft = await response.json()
    filters.value = draft.filters ?? {}
    activeEntryId.value = draft.active_entry_id ?? null
    const restored: Record<number, PendingCleaning> = {}
    for (const item of draft.pending_cleaning ?? []) {
      restored[Number(item.entry_id)] = {
        entry_id: Number(item.entry_id),
        content: String(item.content ?? ''),
        submission_id: String(item.submission_id ?? newSubmissionId(Number(item.entry_id))),
      }
    }
    cleaningDrafts.value = restored
  } catch {
    // 草稿读不到就按空状态进入，不挡住列表加载
  }
}

// 草稿与正式记录对齐：正式记录里已有同样内容的，说明之前已提交成功，草稿不再重复挂起。
async function reconcileDrafts() {
  for (const id of Object.keys(cleaningDrafts.value).map(Number)) {
    const history = await loadCleaningHistory(id)
    const draft = cleaningDrafts.value[id]
    if (draft && history.some((record) => record.content === draft.content.trim())) {
      delete cleaningDrafts.value[id]
    }
  }
}

async function loadCleaningHistory(id: number): Promise<CleaningRecord[]> {
  try {
    const response = await request(`${ENDPOINT}/${id}/cleaning`)
    if (!response.ok) return cleaningHistory.value[id] ?? []
    const payload = await response.json()
    cleaningHistory.value[id] = payload.items ?? []
  } catch {
    // 历史记录拉取失败时保留已读到的内容
  }
  return cleaningHistory.value[id] ?? []
}

function toggleCleaning(row: Row) {
  const id = Number(row.id)
  if (activeEntryId.value === id) {
    activeEntryId.value = null
    return
  }
  activeEntryId.value = id
  if (!cleaningDrafts.value[id]) {
    cleaningDrafts.value[id] = { entry_id: id, content: '', submission_id: newSubmissionId(id) }
  }
  void loadCleaningHistory(id)
}

function onCleaningInput(id: number, content: string) {
  const draft = cleaningDrafts.value[id]
  if (!draft) return
  draft.content = content
  // 内容一变就换提交标识：同一内容重复提交靠标识去重，新内容必须能正常写入
  draft.submission_id = newSubmissionId(id)
}

async function submitCleaning(id: number) {
  const draft = cleaningDrafts.value[id]
  if (!draft || submittingIds.value.has(id)) return
  if (!draft.content.trim()) {
    errorMessage.value = '请先填写清洗内容再提交'
    return
  }
  errorMessage.value = ''
  submittingIds.value.add(id)
  try {
    const response = await request(`${ENDPOINT}/${id}/cleaning`, {
      method: 'POST',
      body: JSON.stringify({ values: { content: draft.content, submission_id: draft.submission_id } }),
    })
    const result = await response.json()
    if (!response.ok || !result.ok) {
      throw new Error(result.message || result.detail || '清洗记录提交失败')
    }
    // 提交成功：草稿与正式记录一致，清掉这条未提交草稿
    delete cleaningDrafts.value[id]
    await loadCleaningHistory(id)
    await reload()
  } catch (error) {
    // 失败时草稿原样保留，用户可原样重试
    errorMessage.value = error instanceof Error ? error.message : '清洗记录提交失败，草稿已保留'
  } finally {
    submittingIds.value.delete(id)
  }
}

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '戏服登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  activeEntryId.value = Number(row.id)
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ values: { action } }),
    })
    const result = await response.json()
    if (!response.ok || result.ok === false) {
      throw new Error(result.message || result.detail || '服装造型动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '服装造型操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  try {
    const response = await request(`${ENDPOINT}?${query}`)
    if (!response.ok) {
      throw new Error('戏服列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '服装造型列表读取失败'
  }
}

onMounted(async () => {
  // 先恢复草稿（筛选、正在处理的戏服、未提交清洗记录），再按恢复后的条件拉列表
  await restoreDraft()
  await reload()
  await reconcileDrafts()
  if (activeEntryId.value != null) {
    void loadCleaningHistory(activeEntryId.value)
  }
})
</script>
