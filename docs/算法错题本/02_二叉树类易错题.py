"""
============================================
华为机考 - 算法错题本：二叉树类
重点：递归思路、用全局变量记录最大值、路径问题
============================================
"""

# ==========================================
# 1. 二叉树的最近公共祖先 (LeetCode 236)
# 易错点：递归返回值的理解；p和q都在左子树时直接返回左子树结果
# ==========================================
class TreeNode:
    def __init__(self, x):
        self.val = x
        self.left = None
        self.right = None

def lowestCommonAncestor(root: TreeNode, p: TreeNode, q: TreeNode) -> TreeNode:
    if not root or root == p or root == q:
        return root  # ★找到p或q就返回，不继续往下找

    left = lowestCommonAncestor(root.left, p, q)
    right = lowestCommonAncestor(root.right, p, q)

    if left and right:  # ★左右各有一个，root就是LCA
        return root
    return left if left else right  # ★只在一边找到，向上传递


# ==========================================
# 2. 二叉树的直径 (LeetCode 543)
# 易错点：直径 = 任意两节点最长路径的边数 = 左深度+右深度；
#         需要全局变量记录最大值，不能用返回值
# ==========================================
def diameterOfBinaryTree(root: TreeNode) -> int:
    ans = 0

    def depth(node):
        nonlocal ans
        if not node:
            return 0
        L = depth(node.left)
        R = depth(node.right)
        ans = max(ans, L + R)  # ★更新最大直径
        return max(L, R) + 1   # ★返回以该节点为根的深度

    depth(root)
    return ans


# ==========================================
# 3. 验证二叉搜索树 (LeetCode 98)
# 易错点：不能只比较当前节点和左右子节点！要用上下界
# ==========================================
def isValidBST(root: TreeNode) -> bool:
    def helper(node, low=float('-inf'), high=float('inf')):
        if not node:
            return True
        if not (low < node.val < high):  # ★用区间判断
            return False
        return helper(node.left, low, node.val) and helper(node.right, node.val, high)

    return helper(root)


# ==========================================
# 4. 路径总和 III (LeetCode 437)
# 易错点：前缀和 + 回溯；路径不一定从根开始；需要用map记录前缀和出现次数
# ==========================================
def pathSum(root: TreeNode, targetSum: int) -> int:
    from collections import defaultdict
    prefix = defaultdict(int)
    prefix[0] = 1  # ★初始化：路径和刚好等于targetSum的情况

    def dfs(node, cur_sum):
        if not node:
            return 0
        cur_sum += node.val
        count = prefix[cur_sum - targetSum]  # ★找之前有多少条前缀和路径
        prefix[cur_sum] += 1

        count += dfs(node.left, cur_sum)
        count += dfs(node.right, cur_sum)

        prefix[cur_sum] -= 1  # ★回溯：离开当前节点要减掉
        return count

    return dfs(root, 0)


# ==========================================
# 5. 二叉树展开为链表 (LeetCode 114)
# 易错点：按先序遍历展开到右指针；需要保存右子树再连接
# ==========================================
def flatten(root: TreeNode) -> None:
    cur = root
    while cur:
        if cur.left:
            pre = cur.left
            while pre.right:  # ★找左子树最右节点
                pre = pre.right
            pre.right = cur.right    # ★把右子树接到左子树最右节点
            cur.right = cur.left     # 左子树移到右边
            cur.left = None          # ★左子树置空
        cur = cur.right


# ==========================================
# 6. 从前序与中序遍历构造二叉树 (LeetCode 105)
# 易错点：下标计算；用hashmap加速中序查找
# ==========================================
def buildTree(preorder: list, inorder: list) -> TreeNode:
    idx_map = {val: i for i, val in enumerate(inorder)}
    pre_idx = 0

    def helper(left, right):
        nonlocal pre_idx
        if left > right:
            return None
        root_val = preorder[pre_idx]
        pre_idx += 1
        root = TreeNode(root_val)
        mid = idx_map[root_val]
        root.left = helper(left, mid - 1)   # ★左子树在[left, mid-1]
        root.right = helper(mid + 1, right)  # ★右子树在[mid+1, right]
        return root

    return helper(0, len(inorder) - 1)


# ==========================================
# 7. 二叉树中的最大路径和 (LeetCode 124)
# 易错点：路径不能分叉；负值处理；用全局变量比较
# ==========================================
def maxPathSum(root: TreeNode) -> int:
    ans = float('-inf')

    def dfs(node):
        nonlocal ans
        if not node:
            return 0
        L = max(dfs(node.left), 0)   # ★负值不选
        R = max(dfs(node.right), 0)
        ans = max(ans, node.val + L + R)  # ★以当前节点为最高点的路径
        return node.val + max(L, R)  # ★只能返回一边

    dfs(root)
    return ans