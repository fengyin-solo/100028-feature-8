<template>
  <div v-if="detail" class="panel-mask" @click.self="closePanel">
    <aside class="processing-panel" role="dialog" aria-label="戏服办理面板">
      <header class="panel-head">
        <div>
          <h3>戏服办理 · {{ detail.服装编号 }}</h3>
          <p class="panel-sub">{{ detail.服装名称 }} / {{ detail.角色归属 }}</p>
        </div>
        <button class="btn ghost" type="button" @click="closePanel">关闭</button>
      </header>

      <div v-if="panelError" class="panel-alert">{{ panelError }}</div>

      <section class="panel-block">
        <h4>戏服信息</h4>
        <dl class="info-grid">
          <div><dt>当前状态</dt><dd class="state-tag">{{ detail.当前状态 }}</dd></div>
          <div><dt>尺码规格</dt><dd>{{ detail.尺码规格 || '—' }}</dd></div>
          <div><dt>造型师</dt><dd>{{ detail.造型师 || '—' }}</dd></div>
          <div><dt>使用场次</dt><dd>{{ detail.使用场次 || '—' }}</dd></div>
          <div v-if="detail.归还时间" class="full"><dt>归还时间</dt><dd>{{ detail.归还时间 }}</dd></div>
        </dl>

        <div class="action-row">
          <button
            v-for="item in availableActions"
            :key="item.action"
            class="btn"
            :class="{ primary: item.action === primaryAction }"
            type="button"
            :disabled="busyAction === item.action"
            @click="runAction(item.action)"
          >
            {{ busyAction === item.action ? '提交中…' : item.action }}
          </button>
          <span v-if="detail.status === '已归还'" class="return-hint">该戏服已归还，可在下方登记或查看清洗记录</span>
        </div>
      </section>

      <section v-if="detail.status === '已归还'" class="panel-block">
        <h4>登记清洗（未提交内容会存为草稿）</h4>
        <div class="cleaning-form">
          <label class="form-item">
            <span>清洗日期 *</span>
            <input
              v-model="cleaningDraft.清洗日期"
              type="date"
              @input="syncCleaningDraft"
            />
          </label>
          <label class="form-item">
            <span>清洗方式 *</span>
            <select v-model="cleaningDraft.清洗方式" @change="syncCleaningDraft">
              <option value="">请选择</option>
              <option value="干洗">干洗</option>
              <option value="水洗">水洗</option>
              <option value="特殊处理">特殊处理</option>
            </select>
          </label>
          <label class="form-item full">
            <span>经办人</span>
            <input
              v-model="cleaningDraft.经办人"
              placeholder="送洗经办人"
              @input="syncCleaningDraft"
            />
          </label>
          <label class="form-item full">
            <span>清洗说明</span>
            <textarea
              v-model="cleaningDraft.清洗说明"
              rows="2"
              placeholder="污渍、破损等备注"
              @input="syncCleaningDraft"
            ></textarea>
          </label>
        </div>
        <div class="action-row">
          <button class="btn primary" type="button" :disabled="busyCleaning" @click="submitCleaning">
            {{ busyCleaning ? '提交中…' : '提交清洗记录' }}
          </button>
          <span v-if="cleaningSavedAt" class="save-hint">草稿已于 {{ cleaningSavedAt }} 自动保存</span>
        </div>
      </section>

      <section class="panel-block">
        <h4>历史清洗记录（{{ cleaningHistory.length }}）</h4>
        <ul v-if="cleaningHistory.length" class="history-list">
          <li v-for="record in cleaningHistory" :key="record.id">
            <span class="history-main">{{ record.清洗日期 }} · {{ record.清洗方式 }}</span>
            <span class="history-meta">
              {{ record.经办人 || '未登记经办人' }}<template v-if="record.清洗说明"> · {{ record.清洗说明 }}</template>
            </span>
            <span class="history-time">{{ record.登记时间 }}</span>
          </li>
        </ul>
        <p v-else class="empty-hint">暂无清洗记录</p>
      </section>
    </aside>
  </div>

  <div v-else class="panel-mask">
    <aside class="processing-panel loading-panel">
      <p v-if="loadError" class="panel-alert">{{ loadError }}</p>
      <p v-else>正在打开戏服办理位置…</p>
      <button class="btn ghost" type="button" @click="closePanel">关闭</button>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import {
  fetchCleaningRecords,
  fetchCostumeDetail,
  submitCleaningRecord,
  submitCostumeAction,
  type CleaningRecord,
  type CostumeRow,
} from '@/api/costume'
import { useCostumeDraftStore, type CleaningDraft } from '@/stores/costumeDraft'

const props = defineProps<{ entryId: number }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const draftStore = useCostumeDraftStore()

const detail = ref<CostumeRow | null>(null)
const cleaningHistory = ref<CleaningRecord[]>([])
const cleaningDraft = ref<CleaningDraft>(draftStore.ensureCleaningDraft(props.entryId))
const busyAction = ref('')
const busyCleaning = ref(false)
const panelError = ref('')
const loadError = ref('')
const cleaningSavedAt = ref('')

const ACTIONS: Array<{ action: string; expect: string }> = [
  { action: '安排定妆', expect: '待定妆' },
  { action: '确认使用', expect: '已定妆' },
  { action: '归还服装', expect: '使用中' },
]

const availableActions = computed(() =>
  detail.value
    ? ACTIONS.filter((item) => item.expect === detail.value!.status)
    : [],
)
const primaryAction = computed(() => availableActions.value[0]?.action ?? '')

async function reloadDetail() {
  detail.value = await fetchCostumeDetail(props.entryId)
  cleaningHistory.value = await fetchCleaningRecords(props.entryId)
}

async function runAction(action: string) {
  if (!detail.value || busyAction.value) {
    return
  }
  panelError.value = ''
  const requestId = draftStore.actionKey(props.entryId, action) ?? crypto.randomUUID()
  draftStore.rememberActionKey(props.entryId, action, requestId)
  busyAction.value = action
  try {
    const result = await submitCostumeAction(props.entryId, action, requestId)
    if (!result.ok || !result.entry) {
      // 保存失败：服务端没改状态，本地明细也不覆盖，只提示原因。
      panelError.value = result.message
      return
    }
    draftStore.clearActionKey(props.entryId, action)
    await reloadDetail()
    emit('changed')
  } catch (error) {
    // 网络层失败同样保留幂等键与当前状态，下次重试仍是同一次提交。
    panelError.value = error instanceof Error ? error.message : '服装造型操作失败'
  } finally {
    busyAction.value = ''
  }
}

function syncCleaningDraft() {
  draftStore.updateCleaningDraft(props.entryId, { ...cleaningDraft.value })
  cleaningSavedAt.value = new Date().toLocaleTimeString()
}

async function submitCleaning() {
  if (busyCleaning.value) {
    return
  }
  panelError.value = ''
  const { requestId, ...values } = cleaningDraft.value
  if (!values.清洗日期.trim() || !values.清洗方式.trim()) {
    panelError.value = '请填写清洗日期与清洗方式后再提交'
    return
  }
  busyCleaning.value = true
  try {
    const result = await submitCleaningRecord(props.entryId, values, requestId)
    if (!result.ok) {
      panelError.value = result.message
      return
    }
    draftStore.removeCleaningDraft(props.entryId)
    await reloadDetail()
    // 为下一次登记准备一份空草稿，并同步到本地引用。
    cleaningDraft.value = draftStore.ensureCleaningDraft(props.entryId)
    emit('changed')
  } catch (error) {
    panelError.value = error instanceof Error ? error.message : '清洗记录提交失败'
  } finally {
    busyCleaning.value = false
  }
}

function closePanel() {
  draftStore.setProcessing(null)
  emit('close')
}

onMounted(async () => {
  panelError.value = ''
  try {
    await reloadDetail()
    if (detail.value) {
      // 明细为准再对一次账：即使当前筛选没把这件戏服列出来，已正式落库的动作键也要清掉。
      draftStore.reconcileWithRows([{ id: detail.value.id, status: detail.value.status }])
    }
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '戏服明细读取失败'
    // 戏服已不存在时清掉对应的办理位置，避免恢复时反复落在死面板上。
    draftStore.setProcessing(null)
  }
})
</script>

<style scoped>
.panel-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.35);
  display: flex;
  justify-content: flex-end;
  z-index: 20;
}
.processing-panel {
  width: 460px;
  max-width: 92vw;
  height: 100%;
  background: #fff;
  padding: 16px 18px;
  overflow-y: auto;
  box-shadow: -4px 0 16px rgba(15, 23, 42, 0.12);
}
.loading-panel { display: flex; flex-direction: column; gap: 12px; align-items: flex-start; }
.panel-head { display: flex; justify-content: space-between; align-items: flex-start; }
.panel-head h3 { margin: 0; font-size: 16px; }
.panel-sub { margin: 4px 0 0; color: var(--muted); font-size: 12px; }
.panel-block { border-top: 1px solid var(--border); padding: 12px 0; }
.panel-block h4 { margin: 0 0 8px; font-size: 13px; }
.info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; margin: 0 0 10px; }
.info-grid dt { font-size: 12px; color: var(--muted); }
.info-grid dd { margin: 2px 0 0; font-size: 13px; }
.info-grid .full { grid-column: 1 / -1; }
.state-tag { color: var(--brand); font-weight: 600; }
.action-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 6px; }
.return-hint, .save-hint { font-size: 12px; color: var(--muted); }
.cleaning-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 12px; }
.form-item span { display: block; font-size: 12px; color: var(--muted); margin-bottom: 2px; }
.form-item input, .form-item select, .form-item textarea {
  width: 100%; border: 1px solid var(--border); border-radius: 6px; padding: 6px 8px; font: inherit;
}
.form-item.full { grid-column: 1 / -1; }
.history-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.history-list li {
  border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px;
  display: flex; flex-direction: column; gap: 2px; font-size: 13px;
}
.history-main { font-weight: 600; }
.history-meta { color: var(--muted); font-size: 12px; }
.history-time { color: #94a3b8; font-size: 11px; }
.empty-hint { color: var(--muted); font-size: 12px; margin: 0; }
.panel-alert {
  background: #fef3f2; border: 1px solid #fecdca; color: #b42318;
  border-radius: 6px; padding: 8px 10px; font-size: 12px; margin: 8px 0;
}
.btn:disabled { opacity: 0.6; cursor: not-allowed; }
</style>
