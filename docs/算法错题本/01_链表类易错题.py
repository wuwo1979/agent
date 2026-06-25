"""
============================================
华为机考 - 算法错题本：链表类
重点：边界条件、空节点、dummy节点技巧
============================================
"""

# ==========================================
# 1. 环形链表 II (LeetCode 142) — 找环入口
# 易错点：快慢指针相遇后，慢指针回到head，等速走即相遇于入口
# ==========================================
class ListNode:
    def __init__(self, x):
        self.val = x
        self.next = None

def detectCycle(head: ListNode) -> ListNode:
    slow = fast = head
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next
        if slow == fast:  # 相遇，有环
            # ★易错：把slow重置到head，然后等速走
            slow = head
            while slow != fast:
                slow = slow.next
                fast = fast.next
            return slow
    return None  # 无环


# ==========================================
# 2. LRU 缓存 (LeetCode 146)
# 易错点：put时key已存在要更新value并移到头部；容量满要删尾部
# ==========================================
class DLinkedNode:
    def __init__(self, key=0, value=0):
        self.key = key
        self.value = value
        self.prev = None
        self.next = None

class LRUCache:
    def __init__(self, capacity: int):
        self.cache = {}
        self.capacity = capacity
        self.head = DLinkedNode()  # ★哨兵头
        self.tail = DLinkedNode()  # ★哨兵尾
        self.head.next = self.tail
        self.tail.prev = self.head

    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1
        node = self.cache[key]
        self._move_to_head(node)
        return node.value

    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            node = self.cache[key]
            node.value = value  # ★更新value
            self._move_to_head(node)
        else:
            node = DLinkedNode(key, value)
            self.cache[key] = node
            self._add_to_head(node)
            if len(self.cache) > self.capacity:
                removed = self._remove_tail()
                del self.cache[removed.key]  # ★删除map里的key

    def _add_to_head(self, node):
        node.prev = self.head
        node.next = self.head.next
        self.head.next.prev = node
        self.head.next = node

    def _remove_node(self, node):
        node.prev.next = node.next
        node.next.prev = node.prev

    def _move_to_head(self, node):
        self._remove_node(node)
        self._add_to_head(node)

    def _remove_tail(self):
        node = self.tail.prev
        self._remove_node(node)
        return node


# ==========================================
# 3. 合并 K 个升序链表 (LeetCode 23)
# 易错点：优先队列需要 (val, idx, node) 防止比较node报错
# ==========================================
import heapq

def mergeKLists(lists):
    heap = []
    idx = 0  # ★防止node不可比较
    for node in lists:
        if node:
            heapq.heappush(heap, (node.val, idx, node))
            idx += 1

    dummy = ListNode(0)
    cur = dummy
    while heap:
        val, i, node = heapq.heappop(heap)
        cur.next = node
        cur = cur.next
        if node.next:
            heapq.heappush(heap, (node.next.val, idx, node.next))
            idx += 1
    return dummy.next


# ==========================================
# 4. 排序链表 (LeetCode 148) — 归并排序 O(nlogn)
# 易错点：找中点用快慢指针；递归终止条件是 head is None or head.next is None
# ==========================================
def sortList(head: ListNode) -> ListNode:
    if not head or not head.next:  # ★终止条件
        return head

    # 找中点(快慢指针)
    slow, fast = head, head.next  # ★fast先走一步，保证奇数个时slow在中点偏左
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next

    mid = slow.next
    slow.next = None  # ★断开成两个链表

    left = sortList(head)
    right = sortList(mid)
    return _merge(left, right)

def _merge(l1, l2):
    dummy = ListNode(0)
    cur = dummy
    while l1 and l2:
        if l1.val < l2.val:
            cur.next = l1
            l1 = l1.next
        else:
            cur.next = l2
            l2 = l2.next
        cur = cur.next
    cur.next = l1 if l1 else l2
    return dummy.next


# ==========================================
# 5. K 个一组翻转链表 (LeetCode 25)
# 易错点：需要先判断剩余节点是否够k个；翻转后要正确连接前后段
# ==========================================
def reverseKGroup(head: ListNode, k: int) -> ListNode:
    dummy = ListNode(0)
    dummy.next = head
    prev = dummy

    while True:
        # 检查是否还有k个节点
        tail = prev
        for i in range(k):
            tail = tail.next
            if not tail:
                return dummy.next  # ★不够k个，返回

        # 翻转 [head:tail] 区间
        next_group = tail.next
        head, tail = _reverse_range(head, tail)  # ★注意返回新的头尾
        prev.next = head
        tail.next = next_group
        prev = tail
        head = next_group

def _reverse_range(head, tail):
    prev = tail.next
    cur = head
    while prev != tail:
        nxt = cur.next
        cur.next = prev
        prev = cur
        cur = nxt
    return tail, head  # ★翻转后tail变成头，head变成尾