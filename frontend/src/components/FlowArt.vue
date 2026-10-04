<script setup lang="ts">
withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
</script>
<template>
  <div :class="['flow-art', { compact }]" aria-hidden="true">
    <svg viewBox="0 0 520 360" fill="none" class="flow-ribbon">
      <g class="ribbon-lines">
        <path v-for="i in 19" :key="i" :d="`M ${70 + i * 5} ${320 - i * 3} C ${-80 + i * 8} ${95 - i * 2}, ${365 + i * 2} ${25 + i * 3}, ${357 + i * 3} ${113 + i * 4} C ${346 + i * 3} ${221 + i * 2}, ${136 + i * 5} ${214 - i * 3}, ${184 + i * 7} ${84 - i * 2}`" stroke="currentColor" :stroke-opacity="0.22 + i * 0.037" stroke-width="1.2" />
      </g>
      <circle cx="391" cy="247" r="5" class="orbit-point"/><path d="M390 233v-9m0 39v9m-15-24h-9m40 0h9" stroke="currentColor" opacity=".45"/>
      <circle cx="130" cy="74" r="2" fill="currentColor" opacity=".6" />
    </svg>
    <span class="art-coordinate">F / 01 — IN THE FLOW</span>
  </div>
</template>
