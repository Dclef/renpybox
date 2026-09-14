"""Self-contained Python 2.7/3 runtime embedded into generated Ren'Py scripts."""

RUNTIME_SOURCE = r'''
def _renpybox_build_transform(records):
    import re
    from collections import OrderedDict
    try:
        text_types = (basestring,)
    except NameError:
        text_types = (str,)
    trie, dynamic, unanchored = {}, [], []
    cache, cache_size = OrderedDict(), [0]
    stats = {"calls": 0, "cache_hits": 0, "dynamic_candidates": 0}

    def insert(text, value):
        node = trie
        for char in text:
            node = node.setdefault(char, {})
        node.setdefault(None, []).append(value)

    for priority, record in enumerate(records):
        source, target, pattern, replacement, literals = record
        if pattern is None:
            insert(source, (0, priority, target))
        else:
            # A leading wildcard consumes from the beginning. Anchor it to
            # prevent trying every starting position on a failed long input.
            if pattern.startswith("(?P<"):
                pattern = r"\A" + pattern
            index = len(dynamic)
            dynamic.append((re.compile(pattern), replacement, literals, priority))
            if literals:
                insert(max(literals, key=len), (1, index, None))
            else:
                unanchored.append(index)

    def transform(text):
        if not isinstance(text, text_types):
            return text
        stats["calls"] += 1
        if text in cache:
            stats["cache_hits"] += 1
            value = cache.pop(text)
            cache[text] = value
            return value
        matches, candidates, length = {}, set(unanchored), len(text)

        def offer(start, end, priority, target):
            if end <= start:
                return
            previous = matches.get(start)
            if previous is None or (end, -priority) > (previous[0], -previous[1]):
                matches[start] = (end, priority, target)

        for start in range(length):
            node, cursor = trie, start
            while cursor < length:
                node = node.get(text[cursor])
                if node is None:
                    break
                cursor += 1
                for kind, index, target in node.get(None, ()):
                    if kind:
                        candidates.add(index)
                    else:
                        offer(start, cursor, index, target)

        stats["dynamic_candidates"] += len(candidates)
        for index in candidates:
            pattern, replacement, literals, priority = dynamic[index]
            cursor, possible = 0, True
            for literal in literals:
                position = text.find(literal, cursor)
                if position < 0:
                    possible = False
                    break
                cursor = position + len(literal)
            if possible:
                for match in pattern.finditer(text):
                    offer(match.start(), match.end(), priority, match.expand(replacement))

        output, cursor = [], 0
        for start in sorted(matches):
            if start < cursor:
                continue
            end, priority, target = matches[start]
            output.extend((text[cursor:start], target))
            cursor = end
        output.append(text[cursor:])
        result = u"".join(output)
        cost = len(text) + len(result)
        if cost <= 16384:
            cache[text] = result
            cache_size[0] += cost
            while len(cache) > 2048 or cache_size[0] > 1048576:
                key, value = cache.popitem(last=False)
                cache_size[0] -= len(key) + len(value)
        return result

    transform._renpybox_stats = stats
    transform._renpybox_cache = cache
    return transform
'''
