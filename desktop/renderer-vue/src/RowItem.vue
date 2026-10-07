<script setup lang="ts">
import type { Row } from './useRowsSocket';

// 单独抽成组件 + v-memo，等价于 React 版的 React.memo，
// 否则滚动时每行都会被重新 patch，对比就不公平了。
defineProps<{ row: Row }>();
</script>

<template>
  <div class="row">
    <span class="idx">{{ row.id }}</span>
    <span class="tag" :class="row.status">{{ row.status }}</span>
    <span class="text">{{ row.source }}</span>
    <span class="text target">{{ row.target || '—' }}</span>
  </div>
</template>