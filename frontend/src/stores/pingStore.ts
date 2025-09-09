/**
 * Pinia store для управления состоянием ping мониторинга
 * Интеграция с функционалом из fluent_gui.py и advanced_bot.py
 */

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { deviceApi, pingApi, telegramApi, configApi, eventStream, eventsApi, monitoringApi, type Device, type DeviceStats, type TelegramStatus, type DeviceConfig, type BotConfig, type EventCategory, type EventCategoryWithDevices, type EventDevice, type EventCategoryCreate, type EventDeviceUpdate } from '@/api/pingApi'
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
  
  const recentEvents = ref<any[]>([])
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

  // ============= Состояние мониторинга =============
  
  const monitoringStatus = ref<any>({})
  const monitoringLoading = ref(false)
  const isMonitoringActive = ref(false)

  // ============= Computed свойства =============

  // Статистика устройств
  const deviceStats = computed((): DeviceStats => {
    const total = devices.value.length
    const online = devices.value.filter(d => d.status === 'online').length
    const offline = devices.value.filter(d => d.status === 'offline').length
    const warning = devices.value.filter(d => d.status === 'warning').length
    
    return { total, online, offline, warning }
  })

  // Устройства онлайн
  const onlineDevices = computed(() => 
    devices.value.filter(d => d.status === 'online')
  )

  // Устройства офлайн
  const offlineDevices = computed(() => 
    devices.value.filter(d => d.status === 'offline')
  )

  // Устройства с предупреждениями
  const warningDevices = computed(() => 
    devices.value.filter(d => d.status === 'warning')
  )

  // Процент доступности
  const availabilityPercentage = computed(() => {
    const total = deviceStats.value.total
    if (total === 0) return 0
    return Math.round((deviceStats.value.online / total) * 100)
  })

  // Среднее время отклика
  const averageResponseTime = computed(() => {
    const responseTimes = devices.value
      .filter(d => d.status === 'online' && d.response_ms)
      .map(d => d.response_ms!)
    
    if (responseTimes.length === 0) return 0
    return Math.round(responseTimes.reduce((a, b) => a + b, 0) / responseTimes.length)
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
      const convertedDevices: Device[] = configDevices.map(configDevice => ({
        id: configDevice.device_id,
        device_id: configDevice.device_id,
        ip: configDevice.ip,
        description: configDevice.description,
        category: configDevice.category,
        status: 'unknown', // Будет обновлено при пинге
        response_ms: null,
        last_seen: null,
        enabled: configDevice.enabled
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
      const index = devices.value.findIndex(d => d.id === id)
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
      devices.value = devices.value.filter(d => d.id !== id)
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
        const device = devices.value.find(d => d.device_id === result.device_id)
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
      const device = devices.value.find(d => d.device_id === deviceKey || String(d.id) === deviceKey)
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
      const device = devices.value.find(d => d.device_id === data.device_id)
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
        message: data.status === 'online' 
          ? 'Устройство восстановлено' 
          : 'Устройство недоступно',
        timestamp: new Date().toLocaleString('ru-RU'),
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

  // ============= Действия для мониторинга =============

  // Загрузить статус мониторинга
  async function loadMonitoringStatus() {
    monitoringLoading.value = true
    try {
      monitoringStatus.value = await monitoringApi.getStatus()
      isMonitoringActive.value = monitoringStatus.value.is_running || false
    } catch (error) {
      console.error('Ошибка загрузки статуса мониторинга:', error)
      notifications.error('Ошибка загрузки', 'Не удалось загрузить статус мониторинга')
    } finally {
      monitoringLoading.value = false
    }
  }

  // Запустить мониторинг
  async function startMonitoring() {
    monitoringLoading.value = true
    try {
      const result = await monitoringApi.start()
      if (result.success) {
        isMonitoringActive.value = true
        await loadMonitoringStatus()
        notifications.success('Мониторинг запущен', result.message)
      } else {
        notifications.error('Ошибка запуска', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка запуска мониторинга:', error)
      notifications.error('Ошибка запуска мониторинга', 'Не удалось запустить автоматический мониторинг')
      throw error
    } finally {
      monitoringLoading.value = false
    }
  }

  // Остановить мониторинг
  async function stopMonitoring() {
    monitoringLoading.value = true
    try {
      const result = await monitoringApi.stop()
      if (result.success) {
        isMonitoringActive.value = false
        await loadMonitoringStatus()
        notifications.success('Мониторинг остановлен', result.message)
      } else {
        notifications.error('Ошибка остановки', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка остановки мониторинга:', error)
      notifications.error('Ошибка остановки мониторинга', 'Не удалось остановить автоматический мониторинг')
      throw error
    } finally {
      monitoringLoading.value = false
    }
  }

  // Выполнить немедленный пинг
  async function performImmediatePing() {
    monitoringLoading.value = true
    try {
      const result = await monitoringApi.pingNow()
      notifications.success('Пинг выполнен', `Проверено ${result.total_devices} устройств`)
      
      // Обновляем статистику устройств
      if (result.results) {
        result.results.forEach((pingResult: any) => {
          const device = devices.value.find(d => d.device_id === pingResult.device_id)
          if (device) {
            device.status = pingResult.status as any
            device.response_ms = pingResult.response_time
            device.last_check = pingResult.timestamp
          }
        })
      }
      
      return result
    } catch (error) {
      console.error('Ошибка выполнения пинга:', error)
      notifications.error('Ошибка пинга', 'Не удалось выполнить немедленный пинг')
      throw error
    } finally {
      monitoringLoading.value = false
    }
  }

  // Перезагрузить конфигурацию мониторинга
  async function reloadMonitoringConfig() {
    try {
      const result = await monitoringApi.reloadConfig()
      if (result.success) {
        await loadMonitoringStatus()
        await loadDevices() // Перезагружаем устройства
        notifications.success('Конфигурация перезагружена', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка перезагрузки конфигурации:', error)
      notifications.error('Ошибка перезагрузки', 'Не удалось перезагрузить конфигурацию')
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

  // Получить статистику категории
  async function getCategoryStatistics(categoryId: number) {
    try {
      return await eventsApi.getCategoryStatistics(categoryId)
    } catch (error) {
      console.error('Ошибка получения статистики категории:', error)
      notifications.error('Ошибка загрузки', 'Не удалось загрузить статистику категории')
      throw error
    }
  }

  // Запустить мониторинг категории
  async function startCategoryMonitoring(categoryId: number) {
    try {
      const result = await eventsApi.startCategoryMonitoring(categoryId)
      if (result.success) {
        await loadEventCategories() // Обновляем список категорий
        notifications.success('Мониторинг категории запущен', result.message)
      } else {
        notifications.error('Ошибка запуска', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка запуска мониторинга категории:', error)
      notifications.error('Ошибка запуска', 'Не удалось запустить мониторинг категории')
      throw error
    }
  }

  // Остановить мониторинг категории
  async function stopCategoryMonitoring(categoryId: number) {
    try {
      const result = await eventsApi.stopCategoryMonitoring(categoryId)
      if (result.success) {
        await loadEventCategories() // Обновляем список категорий
        notifications.success('Мониторинг категории остановлен', result.message)
      } else {
        notifications.error('Ошибка остановки', result.message)
      }
      return result
    } catch (error) {
      console.error('Ошибка остановки мониторинга категории:', error)
      notifications.error('Ошибка остановки', 'Не удалось остановить мониторинг категории')
      throw error
    }
  }

  // Получить статус мониторинга категорий
  async function getCategoriesMonitoringStatus() {
    try {
      return await eventsApi.getCategoriesMonitoringStatus()
    } catch (error) {
      console.error('Ошибка получения статуса мониторинга категорий:', error)
      notifications.error('Ошибка загрузки', 'Не удалось загрузить статус мониторинга категорий')
      throw error
    }
  }

  // ============= Утилиты =============

  // Получить устройство по ID
  function getDeviceById(id: number): Device | undefined {
    return devices.value.find(d => d.id === id)
  }

  // Получить устройства по категории
  function getDevicesByCategory(category: string): Device[] {
    return devices.value.filter(d => d.category === category)
  }

  // Получить уникальные категории
  const categories = computed(() => {
    const cats = new Set(devices.value.map(d => d.category))
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
      loadMonitoringStatus(),
      loadEventCategories(),
      loadAvailableDevices(),
    ])
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
    monitoringStatus,
    monitoringLoading,
    isMonitoringActive,

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
    getCategoryStatistics,
    startCategoryMonitoring,
    stopCategoryMonitoring,
    getCategoriesMonitoringStatus,
    loadMonitoringStatus,
    startMonitoring,
    stopMonitoring,
    performImmediatePing,
    reloadMonitoringConfig,
    reset,
    initialize,
  }
})
