<script setup lang="ts">
import { computed, ref } from 'vue';
import { useVirtualizer } from '@tanstack/vue-virtual';
import RowItem from './RowItem.vue';
import type { Row } from './useRowsSocket';

const props = defineProps<{ rows: Row[] }>();

const parentRef = ref<HTMLElement | null>(null);

// @tanstack/vue-virtual v3 要求传入一个 computed 的 options 对象
const virtualizerOptions = computed(() => ({
  count: props.rows.length,
  getScrollElement: () => parentRef.value,
  estimateSize: () => 68,
  overscan: 8,
  getItemKey: (i: number) => props.rows[i]?.id ?? i,
}));

const virtualizer = useVirtualizer(virtualizerOptions);

const items = computed(() => virtualizer.value.getVirtualItems());
const totalSize = computed(() => virtualizer.value.getTotalSize());

// Vue 的 `:ref` 函数式写法会在每次 patch 都重新调用，
// 配合 measureElement 会触发 ResizeObserver 死循环（实测滚动掉到 14fps、53 个长任务）。
// 所以只在 mounted 时测一次，之后交给 ResizeObserver 增量更新。
const vMeasure = {
  mounted(el: HTMLElement) {
    virtualizer.value.measureElement(el);
  },
};
</script>

<template>
  <div class="table-head">
    <span>#</span><span>状态</span><span>原文</span><span>译文</span>
  </div>
  <div class="table-body" ref="parentRef">
    <div v-if="rows.length === 0" class="empty">点「加载 10 万行」开始</div>
    <div v-else class="table-sizer" :style="{ height: totalSize + 'px' }">
      <div
        v-for="item in items"
        :key="item.key"
        v-memo="[rows[item.index]]"
        class="row-wrap"
        :data-index="item.index"
        v-measure
        :style="{ transform: `translateY(${item.start}px)` }"
      >
        <RowItem :row="rows[item.index]" />
      </div>
    </div>
  </div>
</template>