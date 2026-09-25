/** 本地草稿的读写封装：所有异常都吞掉，读写失败只回报结果，不影响页面使用。 */

export function loadDraft<T>(key: string): T | null {
  try {
    const raw = window.localStorage.getItem(key)
    if (!raw) {
      return null
    }
    return JSON.parse(raw) as T
  } catch {
    return null
  }
}

/** 写入失败（如存储被禁用、容量超限）返回 false，且不会改动已保存的旧草稿。 */
export function saveDraft(key: string, value: unknown): boolean {
  try {
    window.localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

export function clearDraft(key: string): void {
  try {
    window.localStorage.removeItem(key)
  } catch {
    // 忽略：清不掉也不影响页面继续用
  }
}
