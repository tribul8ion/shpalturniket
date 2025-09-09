<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { usePingStore } from '@/stores/pingStore'

const pingStore = usePingStore()

// Получаем события из store
const events = computed(() => pingStore.recentEvents)
const loading = computed(() => pingStore.devicesLoading)

const getEventIcon = (type: string) => {
  switch (type) {
    case 'recovery': 
    case 'online': return 'tabler-circle-check'
    case 'failure':
    case 'offline': return 'tabler-circle-x'
    case 'warning': return 'tabler-alert-triangle'
    case 'info': return 'tabler-info-circle'
    default: return 'tabler-circle'
  }
}

const getEventColor = (type: string) => {
  switch (type) {
    case 'recovery':
    case 'online': return 'success'
    case 'failure':
    case 'offline': return 'error'
    case 'warning': return 'warning'
    case 'info': return 'info'
    default: return 'primary'
  }
}

onMounted(() => {
  // События загружаются автоматически через SSE в store
  pingStore.connectToEventStream()
})
</script>

<template>
  <VCard>
    <VCardItem>
      <VCardTitle class="d-flex align-center gap-2">
        <VIcon
          icon="tabler-history"
          size="24"
        />
        Последние события
      </VCardTitle>
      
      <template #append>
        <VBtn
          color="primary"
          variant="text"
          size="small"
          to="/ping-analytics?tab=events"
        >
          Все события
        </VBtn>
      </template>
    </VCardItem>

    <VCardText>
      <VList
        v-if="!loading && events.length > 0"
        class="card-list"
      >
        <VListItem
          v-for="event in events"
          :key="event.id"
          class="px-0"
        >
          <template #prepend>
            <VAvatar
              :color="getEventColor(event.type)"
              variant="tonal"
              size="32"
            >
              <VIcon
                :icon="getEventIcon(event.type)"
                size="16"
              />
            </VAvatar>
          </template>

          <VListItemTitle class="font-weight-medium">
            {{ event.device }}
            <VChip
              size="x-small"
              variant="outlined"
              class="ml-2"
            >
              {{ event.ip }}
            </VChip>
          </VListItemTitle>
          
          <VListItemSubtitle class="mt-1">
            {{ event.message }}
          </VListItemSubtitle>

          <template #append>
            <span class="text-caption text-medium-emphasis">
              {{ new Date(event.timestamp).toLocaleString('ru-RU') }}
            </span>
          </template>
        </VListItem>
      </VList>

      <!-- Загрузка -->
      <div
        v-else-if="loading"
        class="text-center py-4"
      >
        <VProgressCircular
          indeterminate
          color="primary"
        />
        <p class="text-body-2 mt-2">
          Загрузка событий...
        </p>
      </div>

      <!-- Нет событий -->
      <div
        v-else
        class="text-center py-8"
      >
        <VIcon
          icon="tabler-inbox"
          size="48"
          class="text-medium-emphasis mb-4"
        />
        <p class="text-body-1 text-medium-emphasis">
          Нет последних событий
        </p>
      </div>
    </VCardText>
  </VCard>
</template>

<style scoped>
.card-list {
  --v-list-gap: 12px;
}
</style>
