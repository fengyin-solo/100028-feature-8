<template>
  <section class="page" data-module="costume">
    <header class="page-head">
      <div>
        <h2>服装造型管理</h2>
        <p class="page-desc">维护戏服，围绕服装编号、服装名称、角色归属、尺码规格做登记、筛选与定妆/使用/归还流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记戏服</button>
        <button class="btn" type="button" @click="exportRows">导出服装造型清单</button>
        <button class="btn ghost" type="button" @click="clearDraft">清空本地草稿</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="submitQuery">
      <label v-for="field in filterTextFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" @input="schedulePersistFilters" />
      </label>
      <label class="filter-item">
        <span>当前状态</span>
        <select v-model="filters['当前状态']" @change="persistFilters">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="draftHint" class="draft-hint">草稿已于 {{ draftHint }} 自动保存，离开后重新进入会恢复当前筛选与办理位置</p>
    <p v-if="draftStore.persistError" class="draft-warn">{{ draftStore.persistError }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in visibleRows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ cell(row, column) ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in rowActions(row)"
              :key="action.name"
              class="link"
              type="button"
              @click="openProcessing(row, action.name)"
            >
              {{ action.name }}{{ action.suffix }}
            </button>
          </td>
        </tr>
        <tr v-if="!visibleRows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无符合条件的服装造型数据</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条服装造型记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <ProcessingPanel
      v-if="processingId !== null"
      :entry-id="processingId"
      @close="onPanelClose"
      @changed="reload"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'

import {
  fetchCostumes,
  type CostumeRow,
} from '@/api/costume'
import { useCostumeDraftStore } from '@/stores/costumeDraft'
import ProcessingPanel from './ProcessingPanel.vue'

const ENDPOINT = '/api/costume'
const columns = ["服装编号", "服装名称", "角色归属", "尺码规格", "造型师", "使用场次", "当前状态", "清洗记录"]
const statuses = ["待定妆", "已定妆", "使用中", "已归还"]
const filterTextFields = ["服装编号", "服装名称", "角色归属"]

const draftStore = useCostumeDraftStore()

const rows = ref<CostumeRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const draftHint = ref('')
const processingId = ref<number | null>(draftStore.processingId)
const filters = reactive<Record<string, string>>(draftStore.filters)

let filterPersistTimer: number | undefined
let scrollTimer: number | undefined

const stats = computed(() => {
  const count = (status: string) => rows.value.filter((row) => row.status === status).length
  return [
    { label: "待定妆服装", value: count("待定妆") },
    { label: "使用中服装", value: count("使用中") },
    { label: "待清洗服装", value: count("已归还") },
  ]
})

// 服务端只认服装编号与状态，名称/角色归属在当前页内补充过滤，恢复筛选时结果与上次一致。
const visibleRows = computed(() => {
  const name = (filters['服装名称'] || '').trim()
  const role = (filters['角色归属'] || '').trim()
  return rows.value.filter((row) => {
    if (name && !String(row.服装名称 ?? '').includes(name)) {
      return false
    }
    if (role && !String(row.角色归属 ?? '').includes(role)) {
      return false
    }
    return true
  })
})

function cell(row: CostumeRow, column: string): string | number | null | undefined {
  return (row as unknown as Record<string, string | number | null | undefined>)[column]
}

function persistFilters() {
  draftStore.setFilters({ ...filters })
  draftHint.value = new Date().toLocaleTimeString()
}

function schedulePersistFilters() {
  window.clearTimeout(filterPersistTimer)
  filterPersistTimer = window.setTimeout(persistFilters, 300)
}

function resetFilters() {
  for (const key of Object.keys(filters)) {
    delete filters[key]
  }
  persistFilters()
  void reload()
}

function submitQuery() {
  persistFilters()
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '戏服登记入口尚未接入审批流'
}

/** 每行动作随当前状态给出；已归还的仍保留「归还服装」入口，刷新后可重新打开看归还与清洗历史。 */
function rowActions(row: CostumeRow): Array<{ name: string; suffix: string }> {
  switch (row.status) {
    case '待定妆':
      return [{ name: '安排定妆', suffix: '' }]
    case '已定妆':
      return [{ name: '确认使用', suffix: '' }]
    case '使用中':
      return [{ name: '归还服装', suffix: '' }]
    case '已归还':
      return [{ name: '归还服装', suffix: '（已办）' }]
    default:
      return []
  }
}

function openProcessing(row: CostumeRow, action: string) {
  processingId.value = row.id
  draftStore.setProcessing(row.id)
  if (action !== '归还服装' || row.status !== '已归还') {
    // 预登记动作幂等键：离开回来重试仍然只提交一次。
    draftStore.rememberActionKey(row.id, action, draftStore.actionKey(row.id, action) ?? crypto.randomUUID())
  }
}

function clearDraft() {
  draftStore.resetAll()
  processingId.value = null
  for (const key of Object.keys(filters)) {
    delete filters[key]
  }
  void reload()
}

function onPanelClose() {
  processingId.value = null
}

function onScroll() {
  window.clearTimeout(scrollTimer)
  scrollTimer = window.setTimeout(() => {
    draftStore.setScroll(window.scrollY)
  }, 300)
}

async function reload() {
  errorMessage.value = ''
  try {
    const payload = await fetchCostumes({
      keyword: filters['服装编号'],
      status: filters['当前状态'],
    })
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 以正式记录为准做对账：已落库的动作幂等键、已消失戏服的清洗草稿不再残留在本地。
    draftStore.reconcileWithRows(rows.value)
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '服装造型列表读取失败'
  }
}

onMounted(async () => {
  await reload()
  // 恢复到离开前的滚动位置（列表渲染完成后再滚，保证不是空列表时的位置）。
  if (draftStore.scrollY > 0) {
    window.requestAnimationFrame(() => window.scrollTo({ top: draftStore.scrollY }))
  }
  window.addEventListener('scroll', onScroll, { passive: true })
})

onUnmounted(() => {
  window.clearTimeout(filterPersistTimer)
  window.clearTimeout(scrollTimer)
  window.removeEventListener('scroll', onScroll)
})
</script>

<style scoped>
.draft-hint { font-size: 12px; color: var(--brand); margin: 0 0 8px; }
.draft-warn { font-size: 12px; color: #b42318; margin: 0 0 8px; }
.filter-item select {
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font: inherit;
}
</style>
