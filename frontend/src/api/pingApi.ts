/**
 * API клиент для интеграции с FastAPI backend
 * Интеграция с существующим функционалом из fluent_gui.py и advanced_bot.py
 */

import { ofetch } from 'ofetch'
import { appConfig } from '@/config/app'

// Конфигурация API
const API_BASE_URL = appConfig.apiUrl

// Создаем экземпляр API клиента
const apiClient = ofetch.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    'Content-Type': 'application/json',
  },
})

// ============= Типы данных =============

export interface Device {
  id?: number
  device_id: string
  ip: string
  description: string
  category: string
  status?: 'online' | 'offline' | 'warning' | 'unknown'
  response_ms?: number
  last_check?: string
}

export interface DeviceStats {
  total: number
  online: number
  offline: number
  warning?: number
}

export interface PingResult {
  device_id: string
  ip: string
  status: string
  response_time?: number
  timestamp: string
}

export interface TelegramStatus {
  isRunning: boolean
  botUsername?: string
  connectedUsers: number
  messagesCount: number
  uptime?: string
}

export interface DeviceConfig {
  device_id: string
  ip: string
  description: string
  category: string
  enabled: boolean
}

export interface BotConfig {
  token: string
  time_connect: number
  chat_ids: number[]
}

export interface EventCategory {
  id?: number
  name: string
  description?: string
  is_active: boolean
  created_at?: string
  updated_at?: string
}

export interface EventDevice {
  id?: number
  event_category_id: number
  device_id: string
  is_enabled: boolean
  created_at?: string
}

export interface EventCategoryWithDevices extends EventCategory {
  devices: EventDevice[]
  enabled_devices_count: number
  total_devices_count: number
}

export interface EventCategoryCreate {
  name: string
  description?: string
}

export interface EventDeviceUpdate {
  device_id: string
  is_enabled: boolean
}

export interface ConfigResponse {
  devices: DeviceConfig[]
  bot: BotConfig
  total_devices: number
  enabled_devices: number
}

export interface EventStreamData {
  type: string
  data: any
  timestamp: string
}

// ============= API функции для устройств =============

export const deviceApi = {
  // Получить все устройства
  async getAll(): Promise<Device[]> {
    try {
      return await apiClient<Device[]>('/devices/')
    } catch (error) {
      console.error('Ошибка получения устройств:', error)
      throw error
    }
  },

  // Создать новое устройство
  async create(device: Omit<Device, 'id'>): Promise<Device> {
    try {
      return await apiClient<Device>('/devices/', {
        method: 'POST',
        body: device,
      })
    } catch (error) {
      console.error('Ошибка создания устройства:', error)
      throw error
    }
  },

  // Обновить устройство
  async update(id: number, device: Partial<Device>): Promise<Device> {
    try {
      return await apiClient<Device>(`/devices/${id}`, {
        method: 'PUT',
        body: device,
      })
    } catch (error) {
      console.error('Ошибка обновления устройства:', error)
      throw error
    }
  },

  // Удалить устройство
  async delete(id: number): Promise<void> {
    try {
      await apiClient(`/devices/${id}`, {
        method: 'DELETE',
      })
    } catch (error) {
      console.error('Ошибка удаления устройства:', error)
      throw error
    }
  },

  // Получить статистику устройств
  async getStats(): Promise<DeviceStats> {
    try {
      const devices = await this.getAll()
      const total = devices.length
      const online = devices.filter(d => d.status === 'online').length
      const offline = devices.filter(d => d.status === 'offline').length
      const warning = devices.filter(d => d.status === 'warning').length

      return { total, online, offline, warning }
    } catch (error) {
      console.error('Ошибка получения статистики:', error)
      return { total: 0, online: 0, offline: 0, warning: 0 }
    }
  },
}

// ============= API функции для пинга =============

export const pingApi = {
  // Пинг всех устройств
  async pingAll(): Promise<PingResult[]> {
    try {
      return await apiClient<PingResult[]>('/ping/all', {
        method: 'POST',
      })
    } catch (error) {
      console.error('Ошибка пинга всех устройств:', error)
      throw error
    }
  },

  // Пинг конкретного устройства
  async pingDevice(deviceKey: string): Promise<PingResult> {
    try {
      return await apiClient<PingResult>(`/ping/device/${encodeURIComponent(deviceKey)}`, {
        method: 'GET',
      })
    } catch (error) {
      console.error('Ошибка пинга устройства:', error)
      throw error
    }
  },

  // Пинг по IP адресу
  async pingIp(ip: string): Promise<PingResult> {
    try {
      return await apiClient<PingResult>(`/ping/ip/${ip}`, {
        method: 'GET',
      })
    } catch (error) {
      console.error('Ошибка пинга IP:', error)
      throw error
    }
  },
}

// ============= API функции для мониторинга =============

export const monitoringApi = {
  // Получить статус мониторинга
  async getStatus(): Promise<any> {
    try {
      return await apiClient('/monitoring/status')
    } catch (error) {
      console.error('Ошибка получения статуса мониторинга:', error)
      throw error
    }
  },

  // Запустить мониторинг
  async start(): Promise<{ message: string; success: boolean }> {
    try {
      return await apiClient('/monitoring/start', {
        method: 'POST',
      })
    } catch (error) {
      console.error('Ошибка запуска мониторинга:', error)
      throw error
    }
  },

  // Остановить мониторинг
  async stop(): Promise<{ message: string; success: boolean }> {
    try {
      return await apiClient('/monitoring/stop', {
        method: 'POST',
      })
    } catch (error) {
      console.error('Ошибка остановки мониторинга:', error)
      throw error
    }
  },

  // Выполнить немедленный пинг
  async pingNow(): Promise<any> {
    try {
      return await apiClient('/monitoring/ping-now', {
        method: 'POST',
      })
    } catch (error) {
      console.error('Ошибка выполнения пинга:', error)
      throw error
    }
  },

  // Перезагрузить конфигурацию
  async reloadConfig(): Promise<{ message: string; success: boolean }> {
    try {
      return await apiClient('/monitoring/reload-config', {
        method: 'POST',
      })
    } catch (error) {
      console.error('Ошибка перезагрузки конфигурации:', error)
      throw error
    }
  },
}

// ============= API функции для Telegram =============

export const telegramApi = {
  // Получить статус бота
  async getStatus(): Promise<TelegramStatus> {
    try {
      const response = await apiClient<{
        is_running: boolean
        pid?: number
        last_start?: string
        last_stop?: string
        error?: string
      }>('/bot/status')
      
      return {
        isRunning: response.is_running,
        botUsername: '@ShaplychBot',
        connectedUsers: 0, // TODO: Получать из бота
        messagesCount: 0, // TODO: Получать из бота
        uptime: response.is_running ? 'Активен' : 'Неактивен',
      }
    } catch (error) {
      console.error('Ошибка получения статуса Telegram:', error)
      return {
        isRunning: false,
        botUsername: '@ShaplychBot',
        connectedUsers: 0,
        messagesCount: 0,
        uptime: 'Ошибка',
      }
    }
  },

  // Запустить бота
  async startBot(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await apiClient<{ message: string; pid?: number }>('/bot/start', {
        method: 'POST',
      })
      return { success: true, message: response.message }
    } catch (error) {
      console.error('Ошибка запуска бота:', error)
      return { success: false, message: `Ошибка запуска: ${error}` }
    }
  },

  // Остановить бота
  async stopBot(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await apiClient<{ message: string }>('/bot/stop', {
        method: 'POST',
      })
      return { success: true, message: response.message }
    } catch (error) {
      console.error('Ошибка остановки бота:', error)
      return { success: false, message: `Ошибка остановки: ${error}` }
    }
  },

  // Перезапустить бота
  async restartBot(): Promise<{ success: boolean; message: string }> {
    try {
      const response = await apiClient<{ message: string }>('/bot/restart', {
        method: 'POST',
      })
      return { success: true, message: response.message }
    } catch (error) {
      console.error('Ошибка перезапуска бота:', error)
      return { success: false, message: `Ошибка перезапуска: ${error}` }
    }
  },

  // Получить логи бота
  async getLogs(): Promise<{ logs: string[]; message?: string; error?: string }> {
    try {
      return await apiClient<{ logs: string[]; message?: string; error?: string }>('/bot/logs')
    } catch (error) {
      console.error('Ошибка получения логов бота:', error)
      return { logs: [], error: `Ошибка получения логов: ${error}` }
    }
  },

  // Очистить логи бота
  async clearLogs(): Promise<{ success: boolean; message?: string }> {
    try {
      const res = await apiClient<{ success: boolean; message?: string }>('/bot/logs', { method: 'DELETE' })
      return res
    } catch (error) {
      console.error('Ошибка очистки логов бота:', error)
      return { success: false, message: String(error) }
    }
  },
}

// ============= SSE для реального времени =============

export class EventStreamClient {
  private eventSource: EventSource | null = null
  private listeners: Map<string, Set<(data: any) => void>> = new Map()

  // Подключиться к потоку событий
  connect(): void {
    if (this.eventSource) {
      this.disconnect()
    }

    try {
      this.eventSource = new EventSource(`${API_BASE_URL}/api/events/stream`)

      this.eventSource.onopen = () => {
        console.log('✅ SSE подключение установлено')
      }

      this.eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          this.emit(data.type || 'message', data)
        } catch (error) {
          console.error('Ошибка парсинга SSE сообщения:', error)
        }
      }

      this.eventSource.onerror = (error) => {
        console.error('Ошибка SSE соединения:', error)
        // Переподключение через 5 секунд
        setTimeout(() => {
          if (this.eventSource?.readyState === EventSource.CLOSED) {
            this.connect()
          }
        }, 5000)
      }
    } catch (error) {
      console.error('Ошибка создания SSE соединения:', error)
    }
  }

  // Отключиться от потока событий
  disconnect(): void {
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
    this.listeners.clear()
  }

  // Подписаться на событие
  on(eventType: string, callback: (data: any) => void): void {
    if (!this.listeners.has(eventType)) {
      this.listeners.set(eventType, new Set())
    }
    this.listeners.get(eventType)!.add(callback)
  }

  // Отписаться от события
  off(eventType: string, callback: (data: any) => void): void {
    const listeners = this.listeners.get(eventType)
    if (listeners) {
      listeners.delete(callback)
      if (listeners.size === 0) {
        this.listeners.delete(eventType)
      }
    }
  }

  // Отправить событие подписчикам
  private emit(eventType: string, data: any): void {
    const listeners = this.listeners.get(eventType)
    if (listeners) {
      listeners.forEach(callback => {
        try {
          callback(data)
        } catch (error) {
          console.error('Ошибка в обработчике события:', error)
        }
      })
    }
  }
}

// Глобальный экземпляр SSE клиента
export const eventStream = new EventStreamClient()

// ============= API функции для конфигурации =============

export const configApi = {
  // Получить полную конфигурацию
  async getFullConfig(): Promise<ConfigResponse> {
    try {
      return await apiClient<ConfigResponse>('/config')
    } catch (error) {
      console.error('Ошибка получения конфигурации:', error)
      throw error
    }
  },

  // Получить конфигурацию устройств
  async getDevicesConfig(): Promise<{ devices: DeviceConfig[], total: number }> {
    try {
      return await apiClient<{ devices: DeviceConfig[], total: number }>('/config/devices')
    } catch (error) {
      console.error('Ошибка получения конфигурации устройств:', error)
      throw error
    }
  },

  // Получить конфигурацию бота
  async getBotConfig(): Promise<BotConfig & { exists: boolean }> {
    try {
      return await apiClient<BotConfig & { exists: boolean }>('/config/bot')
    } catch (error) {
      console.error('Ошибка получения конфигурации бота:', error)
      throw error
    }
  },

  // Обновить конфигурацию бота
  async updateBotConfig(botConfig: BotConfig): Promise<{ message: string, success: boolean }> {
    try {
      return await apiClient<{ message: string, success: boolean }>('/config/bot', {
        method: 'PUT',
        body: botConfig,
      })
    } catch (error) {
      console.error('Ошибка обновления конфигурации бота:', error)
      throw error
    }
  },

  // Получить статистику конфигурации
  async getConfigStats(): Promise<{
    total_devices: number
    enabled_devices: number
    disabled_devices: number
    categories: Record<string, { total: number, enabled: number }>
    availability_percentage: number
  }> {
    try {
      return await apiClient('/config/stats')
    } catch (error) {
      console.error('Ошибка получения статистики конфигурации:', error)
      throw error
    }
  },
}

// ============= API для мероприятий =============

export const eventsApi = {
  // Получить все категории мероприятий
  async getCategories(): Promise<EventCategoryWithDevices[]> {
    try {
      return await apiClient('/events/categories')
    } catch (error) {
      console.error('Ошибка получения категорий мероприятий:', error)
      throw error
    }
  },

  // Создать категорию мероприятия
  async createCategory(category: EventCategoryCreate): Promise<EventCategory> {
    try {
      return await apiClient('/events/categories', {
        method: 'POST',
        body: category
      })
    } catch (error) {
      console.error('Ошибка создания категории:', error)
      throw error
    }
  },

  // Обновить категорию мероприятия
  async updateCategory(id: number, category: Partial<EventCategory>): Promise<EventCategory> {
    try {
      return await apiClient(`/events/categories/${id}`, {
        method: 'PUT',
        body: category
      })
    } catch (error) {
      console.error('Ошибка обновления категории:', error)
      throw error
    }
  },

  // Удалить категорию мероприятия
  async deleteCategory(id: number): Promise<{ message: string }> {
    try {
      return await apiClient(`/events/categories/${id}`, {
        method: 'DELETE'
      })
    } catch (error) {
      console.error('Ошибка удаления категории:', error)
      throw error
    }
  },

  // Получить устройства категории
  async getCategoryDevices(categoryId: number): Promise<EventDevice[]> {
    try {
      return await apiClient(`/events/categories/${categoryId}/devices`)
    } catch (error) {
      console.error('Ошибка получения устройств категории:', error)
      throw error
    }
  },

  // Добавить устройства в категорию
  async addDevicesToCategory(categoryId: number, devices: EventDeviceUpdate[]): Promise<{ message: string }> {
    try {
      return await apiClient(`/events/categories/${categoryId}/devices`, {
        method: 'POST',
        body: devices
      })
    } catch (error) {
      console.error('Ошибка добавления устройств в категорию:', error)
      throw error
    }
  },

  // Получить доступные устройства
  async getAvailableDevices(): Promise<{ devices: DeviceConfig[] }> {
    try {
      return await apiClient('/events/devices/available')
    } catch (error) {
      console.error('Ошибка получения доступных устройств:', error)
      throw error
    }
  },

  // Получить статистику категории
  async getCategoryStatistics(categoryId: number): Promise<any> {
    try {
      return await apiClient(`/events/categories/${categoryId}/statistics`)
    } catch (error) {
      console.error('Ошибка получения статистики категории:', error)
      throw error
    }
  },

  // Запустить мониторинг категории
  async startCategoryMonitoring(categoryId: number): Promise<{ message: string; success: boolean }> {
    try {
      return await apiClient(`/events/categories/${categoryId}/monitoring/start`, {
        method: 'POST'
      })
    } catch (error) {
      console.error('Ошибка запуска мониторинга категории:', error)
      throw error
    }
  },

  // Остановить мониторинг категории
  async stopCategoryMonitoring(categoryId: number): Promise<{ message: string; success: boolean }> {
    try {
      return await apiClient(`/events/categories/${categoryId}/monitoring/stop`, {
        method: 'POST'
      })
    } catch (error) {
      console.error('Ошибка остановки мониторинга категории:', error)
      throw error
    }
  },

  // Получить статус мониторинга категорий
  async getCategoriesMonitoringStatus(): Promise<any> {
    try {
      return await apiClient('/events/monitoring/status')
    } catch (error) {
      console.error('Ошибка получения статуса мониторинга категорий:', error)
      throw error
    }
  },
}

// ============= Утилиты =============

export const apiUtils = {
  // Проверить доступность API
  async checkHealth(): Promise<boolean> {
    try {
      await apiClient('/health')
      return true
    } catch (error) {
      console.error('API недоступен:', error)
      return false
    }
  },

  // Форматировать время отклика
  formatResponseTime(ms?: number): string {
    if (!ms) return '—'
    if (ms < 1000) return `${Math.round(ms)}ms`
    return `${(ms / 1000).toFixed(1)}s`
  },

  // Получить иконку статуса
  getStatusIcon(status?: string): string {
    switch (status) {
      case 'online': return '🟢'
      case 'offline': return '🔴'
      case 'warning': return '🟡'
      default: return '⚪'
    }
  },

  // Получить цвет статуса для Vuetify
  getStatusColor(status?: string): string {
    switch (status) {
      case 'online': return 'success'
      case 'offline': return 'error'
      case 'warning': return 'warning'
      default: return 'secondary'
    }
  },
}

// Экспортируем все API
export default {
  devices: deviceApi,
  ping: pingApi,
  telegram: telegramApi,
  config: configApi,
  events: eventStream,
  utils: apiUtils,
}
