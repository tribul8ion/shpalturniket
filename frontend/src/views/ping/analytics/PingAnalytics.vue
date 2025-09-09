<template>
  <div class="ping-analytics">
    <!-- Заголовок страницы -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <h1 class="text-h4 font-weight-bold mb-2">
          📊 Аналитика системы
        </h1>
        <p class="text-body-1 text-medium-emphasis">
          Детальная аналитика работы системы мониторинга турникетов
        </p>
      </div>
      
      <VBtn
        color="primary"
        prepend-icon="tabler-refresh"
        @click="refreshData"
        :loading="loading"
      >
        Обновить данные
      </VBtn>
    </div>

    <!-- Метрики -->
    <PingAnalyticsMetrics 
      :stats="analyticsStats"
      :loading="loading"
    />

    <!-- Графики -->
    <PingAnalyticsCharts 
      :data="chartData"
      :loading="loading"
    />

    <!-- События -->
    <PingAnalyticsEvents 
      :events="recentEvents"
      :loading="loading"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { usePingStore } from '@/stores/pingStore'
import { useNotifications } from '@/composables/useNotifications'
import PingAnalyticsMetrics from './PingAnalyticsMetrics.vue'
import PingAnalyticsCharts from './PingAnalyticsCharts.vue'
import PingAnalyticsEvents from './PingAnalyticsEvents.vue'

const pingStore = usePingStore()
const notifications = useNotifications()

// Состояние
const loading = ref(false)

// Вычисляемые свойства
const analyticsStats = computed(() => {
  const devices = pingStore.devices
  const total = devices.length
  const online = devices.filter(d => d.status === 'online').length
  const offline = devices.filter(d => d.status === 'offline').length
  const availability = total > 0 ? (online / total * 100) : 0

  return {
    totalDevices: total,
    onlineDevices: online,
    offlineDevices: offline,
    availabilityPercentage: Math.round(availability * 10) / 10,
    averageResponseTime: calculateAverageResponseTime(devices),
    lastUpdate: new Date().toLocaleString('ru-RU')
  }
})

const chartData = computed(() => {
  // Реальные данные из истории: агрегируем на фронтенде
  const history = pingStore.recentEvents
  const now = new Date()
  const hours = Array.from({ length: 24 }, (_, i) => new Date(now.getTime() - (23 - i) * 3600000))

  // Словари по часу
  const checksByHour: Record<string, { total: number; online: number; offline: number; rtt: number; rttCount: number }> = {}
  hours.forEach(h => {
    const key = `${h.getFullYear()}-${h.getMonth()}-${h.getDate()} ${h.getHours()}`
    checksByHour[key] = { total: 0, online: 0, offline: 0, rtt: 0, rttCount: 0 }
  })

  // recentEvents хранит последние изменения; используем их как прокси истории
  history.forEach(ev => {
    const t = new Date(ev.timestamp || Date.now())
    const key = `${t.getFullYear()}-${t.getMonth()}-${t.getDate()} ${t.getHours()}`
    if (!checksByHour[key]) return
    checksByHour[key].total += 1
    if (ev.type === 'recovery') checksByHour[key].online += 1
    if (ev.type === 'failure') checksByHour[key].offline += 1
    if (typeof ev.response_ms === 'number') {
      checksByHour[key].rtt += ev.response_ms
      checksByHour[key].rttCount += 1
    }
  })

  const labels = hours.map(h => `${h.getHours()}:00`)
  const availabilityData = hours.map(h => {
    const key = `${h.getFullYear()}-${h.getMonth()}-${h.getDate()} ${h.getHours()}`
    const b = checksByHour[key]
    if (!b || b.total === 0) return analyticsStats.value.availabilityPercentage
    return Math.max(0, Math.min(100, (b.online / b.total) * 100))
  })
  const responseTimeData = hours.map(h => {
    const key = `${h.getFullYear()}-${h.getMonth()}-${h.getDate()} ${h.getHours()}`
    const b = checksByHour[key]
    if (!b || b.rttCount === 0) return analyticsStats.value.averageResponseTime
    return Math.round(b.rtt / b.rttCount)
  })

  return {
    availability: { labels, data: availabilityData },
    responseTime: { labels, data: responseTimeData },
  }
})

const recentEvents = computed(() => {
  return pingStore.recentEvents.slice(0, 10)
})

// Методы
const calculateAverageResponseTime = (devices: any[]) => {
  const devicesWithResponseTime = devices.filter(d => d.response_ms && d.response_ms > 0)
  if (devicesWithResponseTime.length === 0) return 0
  
  const total = devicesWithResponseTime.reduce((sum, d) => sum + d.response_ms, 0)
  return Math.round(total / devicesWithResponseTime.length)
}

const refreshData = async () => {
  loading.value = true
  try {
    await Promise.all([
      pingStore.loadDevices(),
      pingStore.loadFullConfig()
    ])
    notifications.success('Данные аналитики обновлены')
  } catch (error) {
    notifications.error('Ошибка обновления данных аналитики')
    console.error('Ошибка обновления аналитики:', error)
  } finally {
    loading.value = false
  }
}

// Инициализация
onMounted(async () => {
  await refreshData()
})
</script>

<style scoped>
.ping-analytics {
  padding: 24px;
}

@media (max-width: 768px) {
  .ping-analytics {
    padding: 16px;
  }
}
</style>
