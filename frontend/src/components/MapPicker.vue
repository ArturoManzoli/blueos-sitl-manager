<script setup lang="ts">
import 'leaflet/dist/leaflet.css'

import L from 'leaflet'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{
  latitude: number
  longitude: number
  heading: number
}>()

const emit = defineEmits<{
  (event: 'update:latitude', value: number): void
  (event: 'update:longitude', value: number): void
}>()

const mapElement = ref<HTMLElement | null>(null)
let map: L.Map | null = null
let marker: L.Marker | null = null

const round = (value: number): number => Number(value.toFixed(6))

// A heading-aware arrow so the operator can see where the vehicle will face.
function buildIcon(heading: number): L.DivIcon {
  return L.divIcon({
    className: 'sitl-marker',
    html: `<div class="sitl-marker__arrow" style="transform: rotate(${heading}deg)"></div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

function emitPosition(latLng: L.LatLng): void {
  emit('update:latitude', round(latLng.lat))
  emit('update:longitude', round(latLng.lng))
}

onMounted(() => {
  if (!mapElement.value) {
    return
  }

  const center: L.LatLngExpression = [props.latitude, props.longitude]
  map = L.map(mapElement.value, { zoomControl: true }).setView(center, 13)

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map)

  marker = L.marker(center, { draggable: true, icon: buildIcon(props.heading) }).addTo(map)
  marker.on('dragend', () => marker && emitPosition(marker.getLatLng()))
  map.on('click', (event: L.LeafletMouseEvent) => {
    marker?.setLatLng(event.latlng)
    emitPosition(event.latlng)
  })

  // Leaflet measures the container lazily; force a recompute once it is visible.
  setTimeout(() => map?.invalidateSize(), 0)
})

watch(
  () => [props.latitude, props.longitude] as const,
  ([lat, lng]) => {
    if (!map || !marker) {
      return
    }
    const next = L.latLng(lat, lng)
    if (!marker.getLatLng().equals(next)) {
      marker.setLatLng(next)
      map.panTo(next)
    }
  },
)

watch(
  () => props.heading,
  (heading) => marker?.setIcon(buildIcon(heading)),
)

onBeforeUnmount(() => {
  map?.remove()
  map = null
  marker = null
})
</script>

<template>
  <div
    ref="mapElement"
    class="sitl-map elevation-1"
  />
</template>

<style scoped>
.sitl-map {
  height: 280px;
  width: 100%;
  border-radius: 4px;
  z-index: 0;
}

:deep(.sitl-marker__arrow) {
  width: 0;
  height: 0;
  border-left: 9px solid transparent;
  border-right: 9px solid transparent;
  border-bottom: 22px solid var(--bluevue-primary);
  filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.6));
  transform-origin: center;
}
</style>
