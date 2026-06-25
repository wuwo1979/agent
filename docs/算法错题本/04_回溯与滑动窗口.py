"""
============================================
华为机考 - 算法错题本：回溯 & 双指针/滑动窗口
重点：剪枝条件、去重技巧、滑动窗口模板
============================================
"""

# ==========================================
# 1. 全排列 II (LeetCode 47) — 含重复元素
# 易错点：同一层去重用 used[i-1]==False（树层去重）
# ==========================================
def permuteUnique(nums: list) -> list:
    nums.sort()  # ★排序是去重前提
    n = len(nums)
    res = []
    used = [False] * n

    def backtrack(path):
        if len(path) == n:
            res.append(path[:])
            return
        for i in range(n):
            if used[i]:
                continue
            # ★树层去重：同一层，前一个相同元素没被用，跳过
            if i > 0 and nums[i] == nums[i - 1] and not used[i - 1]:
                continue
            used[i] = True
            path.append(nums[i])
            backtrack(path)
            path.pop()
            used[i] = False

    backtrack([])
    return res


# ==========================================
# 2. 子集 II (LeetCode 90) — 含重复元素
# 易错点：同层去重；不需要终止条件（for循环自然结束）
# ==========================================
def subsetsWithDup(nums: list) -> list:
    nums.sort()
    res = []

    def backtrack(start, path):
        res.append(path[:])  # ★每个节点都记录
        for i in range(start, len(nums)):
            if i > start and nums[i] == nums[i - 1]:  # ★树层去重
                continue
            path.append(nums[i])
            backtrack(i + 1, path)
            path.pop()

    backtrack(0, [])
    return res


# ==========================================
# 3. N 皇后 (LeetCode 51)
# 易错点：对角线判断：左上到右下：row-col；右上到左下：row+col
# ==========================================
def solveNQueens(n: int) -> list:
    cols = set()
    diag1 = set()  # row - col
    diag2 = set()  # row + col
    board = [['.'] * n for _ in range(n)]
    res = []

    def backtrack(row):
        if row == n:
            res.append([''.join(r) for r in board])
            return
        for col in range(n):
            if col in cols or (row - col) in diag1 or (row + col) in diag2:
                continue
            cols.add(col)
            diag1.add(row - col)
            diag2.add(row + col)
            board[row][col] = 'Q'
            backtrack(row + 1)
            board[row][col] = '.'
            cols.remove(col)
            diag1.remove(row - col)
            diag2.remove(row + col)

    backtrack(0)
    return res


# ==========================================
# 4. 组合总和 (LeetCode 39) — 可重复选
# 易错点：start参数防止重复组合；可重复选所以递归传i而非i+1
# ==========================================
def combinationSum(candidates: list, target: int) -> list:
    res = []

    def backtrack(start, path, remain):
        if remain == 0:
            res.append(path[:])
            return
        if remain < 0:
            return
        for i in range(start, len(candidates)):
            path.append(candidates[i])
            backtrack(i, path, remain - candidates[i])  # ★传i，可重复选
            path.pop()

    backtrack(0, [], target)
    return res


# ==========================================
# 5. 单词搜索 (LeetCode 79)
# 易错点：DFS回溯标记已访问；用board原地标记代替visited数组
# ==========================================
def exist(board: list, word: str) -> bool:
    m, n = len(board), len(board[0])

    def dfs(i, j, k):
        if k == len(word):
            return True
        if i < 0 or i >= m or j < 0 or j >= n or board[i][j] != word[k]:
            return False
        temp = board[i][j]
        board[i][j] = '#'  # ★原地标记访问
        res = (dfs(i + 1, j, k + 1) or
               dfs(i - 1, j, k + 1) or
               dfs(i, j + 1, k + 1) or
               dfs(i, j - 1, k + 1))
        board[i][j] = temp  # ★恢复
        return res

    for i in range(m):
        for j in range(n):
            if board[i][j] == word[0] and dfs(i, j, 0):
                return True
    return False


# ==========================================
# 6. 最小覆盖子串 (LeetCode 76) — 滑动窗口模板
# 易错点：窗口收缩条件；need字典记录还需要多少；valid计数
# ==========================================
from collections import Counter

def minWindow(s: str, t: str) -> str:
    need = Counter(t)
    window = {}
    left, right = 0, 0
    valid = 0  # ★已满足的字符种类数
    start, length = 0, float('inf')

    while right < len(s):
        c = s[right]
        right += 1
        if c in need:
            window[c] = window.get(c, 0) + 1
            if window[c] == need[c]:
                valid += 1

        # ★当所有字符都满足要求时，收缩左边界
        while valid == len(need):
            if right - left < length:
                start = left
                length = right - left
            d = s[left]
            left += 1
            if d in need:
                if window[d] == need[d]:
                    valid -= 1
                window[d] -= 1

    return "" if length == float('inf') else s[start:start + length]


# ==========================================
# 7. 滑动窗口最大值 (LeetCode 239) — 单调队列
# 易错点：用deque存下标；队列头是最大值；过期元素弹出
# ==========================================
from collections import deque

def maxSlidingWindow(nums: list, k: int) -> list:
    q = deque()  # ★存下标，保证队头最大
    res = []

    for i, num in enumerate(nums):
        # 维护单调递减
        while q and nums[q[-1]] <= num:
            q.pop()
        q.append(i)

        # 移除窗口外的元素
        if q[0] <= i - k:
            q.popleft()

        # 窗口形成后才开始记录
        if i >= k - 1:
            res.append(nums[q[0]])

    return res


# ==========================================
# 8. 接雨水 (LeetCode 42)
# 易错点：双指针法 — 矮的一边决定了能接多少水
# ==========================================
def trap(height: list) -> int:
    left, right = 0, len(height) - 1
    left_max = right_max = 0
    ans = 0

    while left < right:
        left_max = max(left_max, height[left])
        right_max = max(right_max, height[right])

        if left_max < right_max:  # ★左边矮，处理左边
            ans += left_max - height[left]
            left += 1
        else:  # ★右边矮，处理右边
            ans += right_max - height[right]
            right -= 1

    return ans


# ==========================================
# 9. 字符串解码 (LeetCode 394) — 栈
# 易错点：数字可能多位数；嵌套结构用栈
# ==========================================
def decodeString(s: str) -> str:
    stack = []
    cur_num = 0
    cur_str = ""

    for c in s:
        if c.isdigit():
            cur_num = cur_num * 10 + int(c)  # ★多位数处理
        elif c == '[':
            stack.append((cur_str, cur_num))
            cur_str = ""
            cur_num = 0
        elif c == ']':
            prev_str, num = stack.pop()
            cur_str = prev_str + num * cur_str
        else:
            cur_str += c

    return cur_str