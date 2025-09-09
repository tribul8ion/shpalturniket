/**
 * Pinia store для управления состоянием ping мониторинга
 * Интеграция с функционалом из fluent_gui.py и advanced_bot.py
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { deviceApi, pingApi, telegramApi, configApi, eventStream, eventsApi, type Device, type DeviceStats, type TelegramStatus, type DeviceConfig, type BotConfig, type EventCategory, type EventCategoryWithDevices, type EventDevice, type EventCategoryCreate, type EventDeviceUpdate, type StatusLogEntry } from '@/api/pingApi'
import { useNotifications } from '@/composables/useNotifications'

export const usePingStore = defineStore('ping', () => {
  // Инициализируем уведомления
  const notifications = useNotifications()
  
  // ============= Состояние устройств =============
  
  const devices = ref<Device[]>([])
  const devicesLoading = ref(false)
  const devicesError = ref<string | null>(null)

  // ============= Состояние пинга =============
  
  const pingLoading = ref(false)
  const pingResults = ref<Map<string, any>>(new Map())

  // ============= Состояние Telegram =============
  
  const telegramStatus = ref<TelegramStatus>({
    isRunning: false,
    botUsername: '@PingMonitorBot',
    connectedUsers: 0,
    messagesCount: 0,
    uptime: '0m',
  })
  const telegramLoading = ref(false)

  // ============= Состояние событий =============
  
  const recentEvents = ref<Array<{ id: string; type: 'recovery' | 'failure' | string; device: string; ip: string; message: string; timestamp: string; response_ms?: number }>>([])
  const isConnectedToEvents = ref(false)

  // ============= Состояние конфигурации =============
  
  const configDevices = ref<DeviceConfig[]>([])
  const botConfig = ref<BotConfig>({
    token: '',
    time_connect: 50,
    chat_ids: []
  })
  const configLoading = ref(false)

  // ============= Состояние мероприятий =============
  
  const eventCategories = ref<EventCategoryWithDevices[]>([])
  const availableDevices = ref<DeviceConfig[]>([])
  const eventsLoading = ref(false)

  // ============= Computed свойства =============

  // Статистика устройств
  const deviceStats = computed((): DeviceStats => {
    const total = devices.value.length
    const online = devices.value.filter((d: Device) => d.status === 'online').length
    const offline = devices.value.filter((d: Device) => d.status === 'offline').length
    const warning = devices.value.filter((d: Device) => d.status === 'warning').length
    
    return { total, online, offline, warning }
  })

  // Устройства онлайн
  const onlineDevices = computed(() => devices.value.filter((d: Device) => d.status === 'online'))

  // Устройства офлайн
  const offlineDevices = computed(() => devices.value.filter((d: Device) => d.status === 'offline'))

  // Устройства с предупреждениями
  const warningDevices = computed(() => devices.value.filter((d: Device) => d.status === 'warning'))

  // Процент доступности
  const availabilityPercentage = computed(() => {
    const total = deviceStats.value.total
    if (total === 0) return 0
    return Math.round((deviceStats.value.online / total) * 100)
  })

  // Среднее время отклика
  const averageResponseTime = computed(() => {
    const responseTimes = devices.value
      .filter((d: Device) => d.status === 'online' && typeof d.response_ms === 'number')
      .map((d: Device) => d.response_ms as number)
    if (responseTimes.length === 0) return 0
    return Math.round(responseTimes.reduce((a: number, b: number) => a + b, 0) / responseTimes.length)
  })

  // ============= Действия для устройств =============

  // Загрузить все устройства
  async function loadDevices() {
    devicesLoading.value = true
    devicesError.value = null

    try {
      // Сначала загружаем конфигурационные данные
      const configResponse = await configApi.getDevicesConfig()
      const configDevices = configResponse.devices || []
      
      // Преобразуем конфигурационные устройства в формат Device
      const convertedDevices: Device[] = configDevices.map((configDevice: DeviceConfig) => ({
        // локально сохраняем device_id в device_id, а числового id у конфиг-устройств нет
        device_id: configDevice.device_id,
        ip: configDevice.ip,
        description: configDevice.description,
        category: configDevice.category,
        status: 'unknown', // Будет обновлено при пинге
        response_ms: undefined,
        last_check: undefined,
      }))
      
      devices.value = convertedDevices
      // Убираем уведомление при загрузке, чтобы не спамить при обновлении страницы
      // notifications.success('Устройства загружены', `Загружено ${devices.value.length} устройств из конфигурации`)
    } catch (error) {
      devicesError.value = 'Ошибка загрузки устройств'
      console.error('Ошибка загрузки устройств:', error)
      notifications.error('Ошибка загрузки', devicesError.value)
    } finally {
      devicesLoading.value = false
    }
  }

  // Создать новое устройство
  async function createDevice(device: Omit<Device, 'id'>) {
    try {
      const newDevice = await deviceApi.create(device)
      devices.value.push(newDevice)
      return newDevice
    } catch (error) {
      console.error('Ошибка создания устройства:', error)
      throw error
    }
  }

  // Обновить устройство
  async function updateDevice(id: number, updates: Partial<Device>) {
    try {
      const updatedDevice = await deviceApi.update(id, updates)
      const index = devices.value.findIndex((d: Device) => d.id === id)
      if (index !== -1) {
        devices.value[index] = updatedDevice
      }
      return updatedDevice
    } catch (error) {
      console.error('Ошибка обновления устройства:', error)
      throw error
    }
  }

  // Удалить устройство
  async function deleteDevice(id: number) {
    try {
      await deviceApi.delete(id)
      devices.value = devices.value.filter((d: Device) => d.id !== id)
    } catch (error) {
      console.error('Ошибка удаления устройства:', error)
      throw error
    }
  }

  // ============= Действия для пинга =============

  // Пинг всех устройств
  async function pingAllDevices() {
    pingLoading.value = true
    notifications.pingAllStarted()

    try {
      const results = await pingApi.pingAll()
      
      // Обновляем статусы устройств на основе результатов пинга
      results.forEach(result => {
        const device = devices.value.find((d: Device) => d.device_id === result.device_id)
        if (device) {
          const oldStatus = device.status
          device.status = result.status as any
          device.response_ms = result.response_time
          device.last_check = result.timestamp

          // Показываем уведомления при изменении статуса
          if (oldStatus !== result.status) {
            if (result.status === 'online' && oldStatus === 'offline') {
              notifications.deviceOnline(result.device_id, result.ip)
            } else if (result.status === 'offline' && oldStatus === 'online') {
              notifications.deviceOffline(result.device_id, result.ip)
            }
          }
        }
      })

      // Сохраняем результаты
      results.forEach(result => {
        pingResults.value.set(result.device_id, result)
      })

      // Показываем итоговое уведомление
      const stats = deviceStats.value
      notifications.pingAllCompleted(stats)

    } catch (error) {
      console.error('Ошибка пинга всех устройств:', error)
      notifications.error('Ошибка пинга', 'Не удалось выполнить пинг всех устройств')
      throw error
    } finally {
      pingLoading.value = false
    }
  }

  // Пинг конкретного устройства
  async function pingDevice(deviceKey: string) {
    try {
      const result = await pingApi.pingDevice(deviceKey)
      
      // Обновляем статус устройства
      const device = devices.value.find((d: Device) => d.device_id === deviceKey || String(d.id) === deviceKey)
      if (device) {
        device.status = result.status as any
        device.response_ms = result.response_time
        device.last_check = result.timestamp
      }

      pingResults.value.set(result.device_id, result)
      return result
    } catch (error) {
      console.error('Ошибка пинга устройства:', error)
      throw error
    }
  }

  // ============= Действия для Telegram =============

  // Загрузить статус Telegram бота
  async function loadTelegramStatus() {
    telegramLoading.value = true

    try {
      const status = await telegramApi.getStatus()
      telegramStatus.value = status
    } catch (error) {
      console.error('Ошибка загрузки статуса Telegram:', error)
    } finally {
      telegramLoading.value = false
    }
  }

  // Запустить Telegram бота
  async function startTelegramBot() {
    telegramLoading.value = true

    try {
      const result = await telegramApi.startBot()
      if (result.success) {
        telegramStatus.value.isRunning = true
        await loadTelegramStatus() // Обновляем статус
        // Уведомление покажет компонент
      } else {
        notifications.error('Ошибка запуска', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка запуска бота:', error)
      notifications.error('Ошибка запуска бота', 'Не удалось запустить Telegram бота')
      throw error
    } finally {
      telegramLoading.value = false
    }
  }

  // Остановить Telegram бота
  async function stopTelegramBot() {
    telegramLoading.value = true

    try {
      const result = await telegramApi.stopBot()
      if (result.success) {
        telegramStatus.value.isRunning = false
        await loadTelegramStatus() // Обновляем статус
        // Уведомление покажет компонент
      } else {
        notifications.error('Ошибка остановки', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка остановки бота:', error)
      notifications.error('Ошибка остановки бота', 'Не удалось остановить Telegram бота')
      throw error
    } finally {
      telegramLoading.value = false
    }
  }

  // Перезапустить Telegram бота
  async function restartTelegramBot() {
    telegramLoading.value = true

    try {
      const result = await telegramApi.restartBot()
      if (result.success) {
        await loadTelegramStatus() // Обновляем статус
        // Уведомление покажет компонент
      } else {
        notifications.error('Ошибка перезапуска', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка перезапуска бота:', error)
      notifications.error('Ошибка перезапуска бота', 'Не удалось перезапустить Telegram бота')
      throw error
    } finally {
      telegramLoading.value = false
    }
  }

  // Получить логи бота
  async function getBotLogs() {
    try {
      const result = await telegramApi.getLogs()
      return result
    } catch (error) {
      console.error('Ошибка получения логов:', error)
      notifications.error('Ошибка получения логов', 'Не удалось загрузить логи бота')
      throw error
    }
  }

  // Очистить логи бота
  async function clearBotLogs() {
    try {
      const res = await telegramApi.clearLogs()
      if (!res.success)
        notifications.error('Ошибка очистки логов', res.message || 'Не удалось очистить логи')
      return res
    } catch (error) {
      console.error('Ошибка очистки логов:', error)
      notifications.error('Ошибка очистки логов', 'Не удалось очистить логи бота')
      throw error
    }
  }

  // ============= Действия для событий =============

  // Подключиться к потоку событий
  function connectToEventStream() {
    if (isConnectedToEvents.value) return

    eventStream.connect()
    isConnectedToEvents.value = true

    // Подписываемся на события изменения статуса устройств
    eventStream.on('device_status', (event) => {
      const data = event.data || event
      const device = devices.value.find((d: Device) => d.device_id === data.device_id)
      if (device) {
        device.status = data.status
        device.response_ms = data.response_time
        device.last_check = new Date().toISOString()
      }

      // Добавляем в список последних событий
      recentEvents.value.unshift({
        id: Date.now().toString(),
        type: data.status === 'online' ? 'recovery' : 'failure',
        device: data.device_id,
        ip: data.ip,
        message: data.status === 'online' ? 'Устройство восстановлено' : 'Устройство недоступно',
        timestamp: new Date().toISOString(),
        response_ms: data.response_time,
      })

      // Ограничиваем количество событий
      if (recentEvents.value.length > 50) {
        recentEvents.value = recentEvents.value.slice(0, 50)
      }
    })

    // Подписываемся на другие события
    eventStream.on('telegram_status', (event) => {
      const data = event.data || event
      telegramStatus.value = { ...telegramStatus.value, ...data }
    })
  }

  // Отключиться от потока событий
  function disconnectFromEventStream() {
    eventStream.disconnect()
    isConnectedToEvents.value = false
  }

  // ============= Действия для конфигурации =============

  // Загрузить полную конфигурацию
  async function loadFullConfig() {
    configLoading.value = true
    try {
      const config = await configApi.getFullConfig()
      configDevices.value = config.devices
      botConfig.value = config.bot
    } catch (error) {
      console.error('Ошибка загрузки конфигурации:', error)
      notifications.error('Ошибка загрузки', 'Не удалось загрузить конфигурацию')
    } finally {
      configLoading.value = false
    }
  }

  // Загрузить конфигурацию устройств
  async function loadDevicesConfig() {
    try {
      const result = await configApi.getDevicesConfig()
      configDevices.value = result.devices
    } catch (error) {
      console.error('Ошибка загрузки конфигурации устройств:', error)
      throw error
    }
  }

  // Загрузить конфигурацию бота
  async function loadBotConfig() {
    try {
      const result = await configApi.getBotConfig()
      if (result.exists) {
        botConfig.value = {
          token: result.token,
          time_connect: result.time_connect,
          chat_ids: result.chat_ids
        }
      }
    } catch (error) {
      console.error('Ошибка загрузки конфигурации бота:', error)
      throw error
    }
  }

  // Обновить конфигурацию бота
  async function updateBotConfig(newConfig: BotConfig) {
    try {
      const result = await configApi.updateBotConfig(newConfig)
      if (result.success) {
        botConfig.value = newConfig
        notifications.success('Конфигурация обновлена', 'Настройки бота сохранены')
      }
      return result
    } catch (error) {
      console.error('Ошибка обновления конфигурации бота:', error)
      notifications.error('Ошибка обновления', 'Не удалось сохранить настройки бота')
      throw error
    }
  }

  // ============= Действия для мероприятий =============

  // Загрузить категории мероприятий
  async function loadEventCategories() {
    eventsLoading.value = true
    try {
      eventCategories.value = await eventsApi.getCategories()
    } catch (error) {
      console.error('Ошибка загрузки категорий мероприятий:', error)
      notifications.error('Ошибка загрузки', 'Не удалось загрузить категории мероприятий')
    } finally {
      eventsLoading.value = false
    }
  }

  // Создать категорию мероприятия
  async function createEventCategory(category: EventCategoryCreate) {
    eventsLoading.value = true
    try {
      const newCategory = await eventsApi.createCategory(category)
      await loadEventCategories() // Обновляем список
      return newCategory
    } catch (error) {
      console.error('Ошибка создания категории:', error)
      notifications.error('Ошибка создания', 'Не удалось создать категорию мероприятия')
      throw error
    } finally {
      eventsLoading.value = false
    }
  }

  // Обновить категорию мероприятия
  async function updateEventCategory(id: number, category: Partial<EventCategory>) {
    eventsLoading.value = true
    try {
      const updatedCategory = await eventsApi.updateCategory(id, category)
      await loadEventCategories() // Обновляем список
      return updatedCategory
    } catch (error) {
      console.error('Ошибка обновления категории:', error)
      notifications.error('Ошибка обновления', 'Не удалось обновить категорию мероприятия')
      throw error
    } finally {
      eventsLoading.value = false
    }
  }

  // Удалить категорию мероприятия
  async function deleteEventCategory(id: number) {
    eventsLoading.value = true
    try {
      await eventsApi.deleteCategory(id)
      await loadEventCategories() // Обновляем список
    } catch (error) {
      console.error('Ошибка удаления категории:', error)
      notifications.error('Ошибка удаления', 'Не удалось удалить категорию мероприятия')
      throw error
    } finally {
      eventsLoading.value = false
    }
  }

  // Получить устройства категории
  async function getCategoryDevices(categoryId: number): Promise<EventDevice[]> {
    try {
      return await eventsApi.getCategoryDevices(categoryId)
    } catch (error) {
      console.error('Ошибка получения устройств категории:', error)
      notifications.error('Ошибка загрузки', 'Не удалось загрузить устройства категории')
      throw error
    }
  }

  // Добавить устройства в категорию
  async function addDevicesToCategory(categoryId: number, devices: EventDeviceUpdate[]) {
    eventsLoading.value = true
    try {
      await eventsApi.addDevicesToCategory(categoryId, devices)
      await loadEventCategories() // Обновляем статистику
    } catch (error) {
      console.error('Ошибка добавления устройств в категорию:', error)
      notifications.error('Ошибка сохранения', 'Не удалось сохранить выбор устройств')
      throw error
    } finally {
      eventsLoading.value = false
    }
  }

  // Загрузить доступные устройства
  async function loadAvailableDevices() {
    try {
      const result = await eventsApi.getAvailableDevices()
      availableDevices.value = result.devices
    } catch (error) {
      console.error('Ошибка загрузки доступных устройств:', error)
      notifications.error('Ошибка загрузки', 'Не удалось загрузить доступные устройства')
    }
  }

  // Загрузить историю статусов
  async function loadStatusHistory(limit = 200) {
    try {
      const history = await eventsApi.getStatusHistory(limit)
      // Преобразуем в recentEvents формат
      recentEvents.value = history.map((h: StatusLogEntry) => ({
        id: String(h.id),
        type: h.status === 'online' ? 'recovery' : 'failure',
        device: h.device_id,
        ip: h.ip,
        message: h.status === 'online' ? 'Устройство восстановлено' : 'Устройство недоступно',
        timestamp: h.timestamp,
        response_ms: h.response_ms,
      }))
    } catch (error) {
      console.error('Ошибка загрузки истории статусов:', error)
    }
  }

  // ============= Утилиты =============

  // Получить устройство по ID
  function getDeviceById(id: number): Device | undefined {
    return devices.value.find((d: Device) => d.id === id)
  }

  // Получить устройства по категории
  function getDevicesByCategory(category: string): Device[] {
    return devices.value.filter((d: Device) => d.category === category)
  }

  // Получить уникальные категории
  const categories = computed(() => {
    const cats = new Set(devices.value.map((d: Device) => d.category))
    return Array.from(cats)
  })

  // Сбросить все данные
  function reset() {
    devices.value = []
    devicesError.value = null
    pingResults.value.clear()
    recentEvents.value = []
    disconnectFromEventStream()
  }

  // ============= Инициализация =============

  // Автоматически загружаем данные при создании store
  async function initialize() {
    await Promise.all([
      loadDevices(),
      loadTelegramStatus(),
      loadFullConfig(),
    ])
    await loadStatusHistory(200)
    connectToEventStream()
  }

  return {
    // Состояние
    devices,
    devicesLoading,
    devicesError,
    pingLoading,
    pingResults,
    telegramStatus,
    telegramLoading,
    recentEvents,
    isConnectedToEvents,
    configDevices,
    botConfig,
    configLoading,
    eventCategories,
    availableDevices,
    eventsLoading,

    // Computed
    deviceStats,
    onlineDevices,
    offlineDevices,
    warningDevices,
    availabilityPercentage,
    averageResponseTime,
    categories,

    // Действия
    loadDevices,
    createDevice,
    updateDevice,
    deleteDevice,
    pingAllDevices,
    pingDevice,
    loadTelegramStatus,
    startTelegramBot,
    stopTelegramBot,
    restartTelegramBot,
    getBotLogs,
    clearBotLogs,
    connectToEventStream,
    disconnectFromEventStream,
    loadFullConfig,
    loadDevicesConfig,
    loadBotConfig,
    updateBotConfig,
    getDeviceById,
    getDevicesByCategory,
    loadEventCategories,
    createEventCategory,
    updateEventCategory,
    deleteEventCategory,
    getCategoryDevices,
    addDevicesToCategory,
    loadAvailableDevices,
    loadStatusHistory,
    reset,
    initialize,
  }
})
