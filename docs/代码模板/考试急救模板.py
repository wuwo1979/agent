"""
华为 AI岗 机考 急救模板
- 只收录最高频的代码骨架
- 目标是"记住这几行，能拿部分分"
"""

import sys
import numpy as np

# ══════════════════════════════════════════════════════════════
# 0. 万能输入模板（所有题通用）
# ══════════════════════════════════════════════════════════════
def solve():
    data = sys.stdin.read().strip().split()
    it = iter(data)
    T = int(next(it))
    # ... 按题目顺序取值

    # 浮点数组快速读取
    arr = [float(next(it)) for _ in range(n)]
    # 或 np 数组
    x = np.array([float(next(it)) for _ in range(n)])

# ══════════════════════════════════════════════════════════════
# 1. 逻辑回归（最高频，3 场 AI 岗出现）
# ══════════════════════════════════════════════════════════════
def sigmoid_safe(z):
    """安全 sigmoid，防止 exp 溢出"""
    z = np.asarray(z, dtype=np.float64)
    return np.where(
        z >= 0,
        1.0 / (1.0 + np.exp(-z)),
        np.exp(z) / (1.0 + np.exp(z))
    )

def logistic_regression():
    """⭐ 核心骨架：标准化 → 训练 → 预测"""
    input = sys.stdin.readline
    N, epochs, lr = map(float, input().split())
    N = int(N); epochs = int(epochs)

    # 读数据
    X, y = [], []
    for _ in range(N):
        x1, x2, label = map(float, input().split())
        X.append([x1, x2])
        y.append(label)
    X = np.array(X); y = np.array(y)

    # 1️⃣ 标准化（重要！数据差很大时必须做）
    mean, std = X.mean(axis=0), X.std(axis=0)
    X = (X - mean) / std

    # 2️⃣ 加偏置列
    X = np.hstack([np.ones((N, 1)), X])  # shape (N, 3)

    # 3️⃣ 初始化
    w = np.zeros(3)  # [b, w1, w2]

    # 4️⃣ 批量梯度下降（⭐ 核心循环）
    for _ in range(epochs):
        pred = sigmoid_safe(X @ w)       # 前向
        grad = X.T @ (pred - y) / N      # 梯度
        w -= lr * grad                    # 更新

    # 5️⃣ 预测新样本
    q = np.array([float(input()) for _ in range(2)])
    q = (q - mean) / std
    q = np.insert(q, 0, 1.0)  # 加偏置
    prob = sigmoid_safe(q @ w)[0]
    print(f"{prob:.4f}")

# ══════════════════════════════════════════════════════════════
# 2. LSTM 前向传播（4.29 原题）
# ══════════════════════════════════════════════════════════════
def lstm_forward():
    """
    输入: T B D H
    然后 T*B*D 个特征值
    然后 4 组门参数, 每组: Wx(D,H) + Wh(H,H) + b(H)
    """
    tokens = sys.stdin.read().strip().split()
    it = iter(tokens)
    T = int(next(it)); B = int(next(it)); D = int(next(it)); H = int(next(it))

    # 读输入
    x = np.zeros((T, B, D))
    for t in range(T):
        for b_idx in range(B):
            for d in range(D):
                x[t, b_idx, d] = float(next(it))

    # 读 4 组门参数
    gates = []
    for _ in range(4):
        Wx = np.array([float(next(it)) for _ in range(D*H)]).reshape(D, H)
        Wh = np.array([float(next(it)) for _ in range(H*H)]).reshape(H, H)
        b  = np.array([float(next(it)) for _ in range(H)])
        gates.append((Wx, Wh, b))

    Wxi, Whi, bi = gates[0]  # 输入门
    Wxf, Whf, bf = gates[1]  # 遗忘门
    Wxc, Whc, bc = gates[2]  # 候选状态
    Wxo, Who, bo = gates[3]  # 输出门

    h = np.zeros((T, B, H))
    c = np.zeros((T, B, H))

    # ⭐ LSTM 核心公式
    for t in range(T):
        for b_idx in range(B):
            xt = x[t, b_idx]
            h_prev = h[t-1, b_idx] if t > 0 else np.zeros(H)
            c_prev = c[t-1, b_idx] if t > 0 else np.zeros(H)

            ft = sigmoid_safe(xt @ Wxf + h_prev @ Whf + bf)  # 遗忘门
            it = sigmoid_safe(xt @ Wxi + h_prev @ Whi + bi)  # 输入门
            ct_tilde = np.tanh(xt @ Wxc + h_prev @ Whc + bc)  # 候选
            c[t, b_idx] = ft * c_prev + it * ct_tilde        # 细胞状态
            ot = sigmoid_safe(xt @ Wxo + h_prev @ Who + bo)  # 输出门
            h[t, b_idx] = ot * np.tanh(c[t, b_idx])          # 隐状态

    # 输出
    h_out = h.flatten()
    c_out = c[-1, :, :].flatten() if T > 0 else c.flatten()
    print(' '.join(f'{v:.4f}' for v in h_out))
    print(' '.join(f'{v:.4f}' for v in c_out))

# ══════════════════════════════════════════════════════════════
# 3. 混淆矩阵 & F1（选择题高频，也可能编程考）
# ══════════════════════════════════════════════════════════════
def confusion_matrix_metrics(y_true, y_pred):
    TP = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    FP = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    TN = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    FN = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)

    precision = TP / (TP + FP) if TP + FP > 0 else 0
    recall = TP / (TP + FN) if TP + FN > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0
    accuracy = (TP + TN) / (TP + TN + FP + FN)
    return precision, recall, f1, accuracy

# ══════════════════════════════════════════════════════════════
# 4. 数据标准化（逻辑回归前置步骤）
# ══════════════════════════════════════════════════════════════
def standardize(X):
    """Z-score 标准化"""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    return (X - mean) / std

def minmax_scale(X):
    """Min-Max 归一化"""
    min_val = X.min(axis=0)
    max_val = X.max(axis=0)
    return (X - min_val) / (max_val - min_val)

# ══════════════════════════════════════════════════════════════
# 5. K-means 聚类（1015 场次考了 Bi-Kmeans）
# ══════════════════════════════════════════════════════════════
def kmeans(X, k, max_iter=100):
    """标准 K-means（⭐ 记前 3 行即可）"""
    centers = X[np.random.choice(len(X), k, replace=False)]
    for _ in range(max_iter):
        # 1️⃣ 分配簇
        dists = np.linalg.norm(X[:, None] - centers, axis=2)
        labels = np.argmin(dists, axis=1)
        # 2️⃣ 更新中心
        new_centers = np.array([X[labels == i].mean(axis=0) for i in range(k)])
        if np.allclose(centers, new_centers):
            break
        centers = new_centers
    return labels, centers

# ══════════════════════════════════════════════════════════════
# 6. 二叉树层序建树 + DFS（0422 考了 2 次）
# ══════════════════════════════════════════════════════════════
class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right

def build_tree(arr):
    """层序列表 → 二叉树（None 表示空节点）"""
    if not arr or arr[0] is None:

        return None
    root = TreeNode(arr[0])
    q = [root]
    i = 1
    while q and i < len(arr):
        node = q.pop(0)
        if arr[i] is not None:
            node.left = TreeNode(arr[i])
            q.append(node.left)
        i += 1
        if i < len(arr) and arr[i] is not None:
            node.right = TreeNode(arr[i])
            q.append(node.right)
        i += 1
    return root

# ══════════════════════════════════════════════════════════════
# 7. 语料清洗（字符串模拟，4.29 原题）
# ══════════════════════════════════════════════════════════════
import re

def clean_corpus(text, rules):
    """
    常见清洗规则：
    - 删除 HTML 标签: re.sub(r'<[^>]+>', '', text)
    - 删除 URL: re.sub(r'http\S+', '', text)
    - 删除特殊字符: re.sub(r'[^\w\s]', '', text)
    - 多余空格: re.sub(r'\s+', ' ', text).strip()
    - 转小写: text.lower()
    """
    for rule in rules:
        if rule == 'strip_html':
            text = re.sub(r'<[^>]+>', '', text)
        elif rule == 'strip_url':
            text = re.sub(r'https?://\S+', '', text)
        elif rule == 'strip_punct':
            text = re.sub(r'[^\w\s]', '', text)
        elif rule == 'collapse_space':
            text = re.sub(r'\s+', ' ', text).strip()
        elif rule == 'lower':
            text = text.lower()
    return text

# ══════════════════════════════════════════════════════════════
# 8. 选择题速查（考试前看一遍）
# ══════════════════════════════════════════════════════════════
"""
高频选择题考点：
├── Transformer: Attention = softmax(Q·K^T / √d_k)·V
├── RLHF: SFT → RM训练 → PPO强化学习
├── MoE: Top-2门控，每个token选2个专家，门控参数也训练
├── PagedAttention: KV Cache分页管理，减少碎片化
├── AdamW: W=Weight Decay decoupling（解耦权重衰减）
├── 过拟合: 训练好测试差 → L2/Dropout/早停
├── 混淆矩阵: P=TP/(TP+FP), R=TP/(TP+FN), F1=2PR/(P+R)
├── LDA: 有监督，最大化类间/类内散度比
├── NMF: 非负矩阵分解，数据非负，可解释性强
├── 逻辑回归: 决策边界是超平面 (w·x+b=0)
├── Var(aX+b) = a²·Var(X)
├── 正交变换: 保持内积/欧氏距离/余弦相似度（不保持曼哈顿距离）
├── 条件数 κ(A) = ‖A‖·‖A⁻¹‖（越大越病态）
├── Dead ReLU: 输入<0时梯度=0，学习率过大会导致，LeakyReLU可缓解
├── FP16: 降低内存占用与加速计算（非提高精度）
├── PCA: 先标准化再降维
├── 二项分布 MLE: p̂ = x̄/n
├── 贝叶斯网络链式: A→B→C，给定B时A⊥C（条件独立）
└── KV Cache: Prefill计算并缓存, Decode复用, Q不缓存
"""

# ══════════════════════════════════════════════════════════════
# 9. 考试节奏表
# ══════════════════════════════════════════════════════════════
"""
┌──────────────┬──────────┬──────────────────────────────────┐
│    阶段      │  时间    │  策略                             │
├──────────────┼──────────┼──────────────────────────────────┤
│ 选择题20道   │ 30-40min │ 先单选后多选，不确定标记跳过       │
│ 编程题1(150) │ 40-50min │ 写骨架！标准化+梯度下降3行就得80分 │
│ 编程题2(300) │ 30-40min │ 看懂了写暴力解，看不懂输出空列表   │
│ 检查         │ 10min    │ 输入输出格式、小数位数            │
└──────────────┴──────────┴──────────────────────────────────┘
150及格线：选择题100 + 编程1:80 = 180分 稳过！
"""