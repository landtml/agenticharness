class _Node:
    __slots__ = ("key", "prev", "next")

    def __init__(self, key):
        self.key = key
        self.prev = None
        self.next = None


def lru_evictions(capacity: int, accesses: list[str]) -> list[str]:
    if capacity < 1:
        raise ValueError("capacity must be at least 1")
    head = _Node(None)
    tail = _Node(None)
    head.next = tail
    tail.prev = head
    nodes: dict[str, _Node] = {}
    evicted: list[str] = []

    def unlink(node):
        node.prev.next = node.next
        node.next.prev = node.prev

    def append(node):
        node.prev = tail.prev
        node.next = tail
        tail.prev.next = node
        tail.prev = node

    for key in accesses:
        node = nodes.get(key)
        if node is not None:
            unlink(node)
            append(node)
            continue
        if len(nodes) == capacity:
            lru = head.next
            unlink(lru)
            del nodes[lru.key]
            evicted.append(lru.key)
        node = _Node(key)
        nodes[key] = node
        append(node)
    return evicted
