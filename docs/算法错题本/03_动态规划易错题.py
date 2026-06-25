"""
============================================
华为机考 - 算法错题本：动态规划类
重点：状态定义、转移方程、初始化、遍历顺序
============================================
"""

# ==========================================
# 1. 最长递增子序列 (LeetCode 300)
# 易错点：dp[i] 表示以 nums[i] 结尾的LIS长度；需要两层循环
# 优化：贪心+二分 O(nlogn)
# ==========================================
def lengthOfLIS(nums: list) -> int:
    n = len(nums)
    dp = [1] * n  # ★每个元素自身长度为1
    for i in range(n):
        for j in range(i):
            if nums[j] < nums[i]:
                dp[i] = max(dp[i], dp[j] + 1)
    return max(dp)

# 贪心+二分优化
def lengthOfLIS_greedy(nums):
    tails = []
    for x in nums:
        # ★二分查找第一个 >= x 的位置
        l, r = 0, len(tails)
        while l < r:
            mid = (l + r) // 2
            if tails[mid] < x:
                l = mid + 1
            else:
                r = mid
        if l == len(tails):
            tails.append(x)
        else:
            tails[l] = x
    return len(tails)


# ==========================================
# 2. 编辑距离 (LeetCode 72)
# 易错点：dp[i][j] 表示 word1[:i] 转 word2[:j] 的最少操作数
#         初始化第一行/列的边界值
# ==========================================
def minDistance(word1: str, word2: str) -> int:
    m, n = len(word1), len(word2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]

    for i in range(m + 1):
        dp[i][0] = i  # ★删除i个
    for j in range(n + 1):
        dp[0][j] = j  # ★插入j个

    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if word1[i - 1] == word2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]  # ★字符相同，不用操作
            else:
                dp[i][j] = min(
                    dp[i - 1][j],      # 删除
                    dp[i][j - 1],      # 插入
                    dp[i - 1][j - 1]   # 替换
                ) + 1
    return dp[m][n]


# ==========================================
# 3. 分割等和子集 (LeetCode 416) — 0-1背包变种
# 易错点：转化为"能否选出若干个数和为target"；
#         一维dp要倒序遍历，避免重复使用
# ==========================================
def canPartition(nums: list) -> bool:
    total = sum(nums)
    if total % 2 == 1:  # ★奇数不可能平分
        return False
    target = total // 2

    dp = [False] * (target + 1)
    dp[0] = True

    for num in nums:
        for j in range(target, num - 1, -1):  # ★倒序遍历
            dp[j] = dp[j] or dp[j - num]
    return dp[target]


# ==========================================
# 4. 零钱兑换 (LeetCode 322) — 完全背包
# 易错点：dp初始化无穷大，dp[0]=0；完全背包正序遍历
# ==========================================
def coinChange(coins: list, amount: int) -> int:
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0

    for coin in coins:
        for j in range(coin, amount + 1):  # ★正序遍历（完全背包）
            dp[j] = min(dp[j], dp[j - coin] + 1)

    return dp[amount] if dp[amount] != float('inf') else -1


# ==========================================
# 5. 最长回文子串 (LeetCode 5)
# 易错点：中心扩展时奇偶两种情况；越界判断
# ==========================================
def longestPalindrome(s: str) -> str:
    n = len(s)
    start, max_len = 0, 1

    def expand(l, r):
        nonlocal start, max_len
        while l >= 0 and r < n and s[l] == s[r]:
            if r - l + 1 > max_len:
                start = l
                max_len = r - l + 1
            l -= 1
            r += 1

    for i in range(n):
        expand(i, i)      # ★奇数长度
        expand(i, i + 1)  # ★偶数长度
    return s[start:start + max_len]


# ==========================================
# 6. 打家劫舍 III (LeetCode 337) — 树形DP
# 易错点：每个节点返回(偷, 不偷)两个状态
# ==========================================
def rob_iii(root) -> int:
    def dfs(node):
        if not node:
            return (0, 0)
        L = dfs(node.left)
        R = dfs(node.right)
        rob = node.val + L[1] + R[1]        # ★偷当前：不能偷子节点
        not_rob = max(L) + max(R)            # ★不偷当前：子节点可偷可不偷
        return (rob, not_rob)

    return max(dfs(root))


# ==========================================
# 7. 买卖股票的最佳时机含冷冻期 (LeetCode 309)
# 易错点：三种状态（持有、不持有冷冻期、不持有非冷冻期）
# ==========================================
def maxProfit(prices: list) -> int:
    if not prices:
        return 0
    n = len(prices)
    hold = [-10**9] * n       # 持有
    sold = [0] * n             # 不持有（当天卖出，冷冻）
    rest = [0] * n             # 不持有（非冷冻）

    hold[0] = -prices[0]

    for i in range(1, n):
        hold[i] = max(hold[i - 1], rest[i - 1] - prices[i])  # ★只能从rest买入
        sold[i] = hold[i - 1] + prices[i]                     # ★卖出
        rest[i] = max(rest[i - 1], sold[i - 1])               # ★冷冻后恢复

    return max(sold[-1], rest[-1])


# ==========================================
# 8. 单词拆分 (LeetCode 139)
# 易错点：dp[i]表示s[:i]能否被拆分；用set加速查找
# ==========================================
def wordBreak(s: str, wordDict: list) -> bool:
    word_set = set(wordDict)
    n = len(s)
    dp = [False] * (n + 1)
    dp[0] = True

    for i in range(1, n + 1):
        for j in range(i):
            if dp[j] and s[j:i] in word_set:
                dp[i] = True
                break
    return dp[n]