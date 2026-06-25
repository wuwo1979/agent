"""
==========================================================
华为AI岗机考 - 代码模板大全（AI岗专用）
核心：选择题 + AI场景编程题
==========================================================
"""

# =========================================================
# PART 1: AI岗编程题输入输出模板
# =========================================================

# --- 模板A: 标准OJ输入 ---
"""
输入:
d h
x1 x2 ... xd
h1 h2 ... hh
c1 c2 ... ch
...
"""
def read_standard():
    import sys
    d, h = map(int, sys.stdin.readline().split())
    x = list(map(float, sys.stdin.readline().split()))
    h_prev = list(map(float, sys.stdin.readline().split()))
    c_prev = list(map(float, sys.stdin.readline().split()))
    # ... 读取参数
    return d, h, x, h_prev, c_prev

# --- 模板B: CSV/表格数据 ---
def read_csv_data():
    import sys
    lines = sys.stdin.read().strip().split('\n')
    # 第一行是header
    header = lines[0].split(',')
    data = [line.split(',') for line in lines[1:]]
    return header, data


# =========================================================
# PART 2: AI/ML 算法手写模板
# =========================================================

# --- 2.1 逻辑回归（批量梯度下降）---
import numpy as np

class LogisticRegression:
    def __init__(self, lr=0.01, epochs=1000):
        self.lr = lr
        self.epochs = epochs
        self.w = None
        self.mean = None
        self.std = None

    def fit(self, X, y):
        N, D = X.shape
        # 标准化
        self.mean = X.mean(axis=0)
        self.std = X.std(axis=0)
        self.std[self.std == 0] = 1
        X_norm = (X - self.mean) / self.std

        # 加偏置（可选，也可以让模型自己学bias）
        X_norm = np.hstack([np.ones((N, 1)), X_norm])

        # 初始化
        self.w = np.zeros(D + 1)

        for _ in range(self.epochs):
            z = X_norm @ self.w
            pred = 1 / (1 + np.exp(-z))
            grad = (1 / N) * X_norm.T @ (pred - y)
            self.w -= self.lr * grad
        return self

    def predict(self, X, threshold=0.5):
        X_norm = (X - self.mean) / self.std
        X_norm = np.hstack([np.ones((X_norm.shape[0], 1)), X_norm])
        z = X_norm @ self.w
        pred = 1 / (1 + np.exp(-z))
        return (pred >= threshold).astype(int)

    def predict_proba(self, X):
        X_norm = (X - self.mean) / self.std
        X_norm = np.hstack([np.ones((X_norm.shape[0], 1)), X_norm])
        z = X_norm @ self.w
        return 1 / (1 + np.exp(-z))


# --- 2.2 K-means 聚类 ---
class KMeans:
    def __init__(self, k=3, max_iters=100):
        self.k = k
        self.max_iters = max_iters
        self.centroids = None

    def fit(self, X):
        N, D = X.shape
        # 随机选k个质心
        idx = np.random.choice(N, self.k, replace=False)
        self.centroids = X[idx]

        for _ in range(self.max_iters):
            # 分配
            distances = np.linalg.norm(X[:, None] - self.centroids[None], axis=2)
            labels = np.argmin(distances, axis=1)

            # 更新质心
            new_centroids = np.array([X[labels == i].mean(axis=0) for i in range(self.k)])
            if np.allclose(self.centroids, new_centroids):
                break
            self.centroids = new_centroids

        return self


# --- 2.3 数据标准化（高频）---
def standardize(X):
    """标准化到均值0方差1"""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1
    return (X - mean) / std, mean, std

def minmax_scale(X):
    """归一化到[0,1]"""
    min_val = X.min(axis=0)
    max_val = X.max(axis=0)
    range_val = max_val - min_val
    range_val[range_val == 0] = 1
    return (X - min_val) / range_val, min_val, max_val


# =========================================================
# PART 3: NumPy 高频操作速查
# =========================================================

"""
np.array([1,2,3])           # 创建数组
np.zeros((3,4))             # 全0
np.ones((3,4))              # 全1
np.eye(3)                   # 单位矩阵
np.random.randn(3,4)        # 正态分布随机数
np.random.randint(0,10,(3,4)) # 整数随机数
np.linspace(0,1,10)         # 等间隔
np.arange(0,10,2)           # [0,2,4,6,8]

arr.shape                   # 形状
arr.reshape(2,-1)           # 重塑
arr.T                       # 转置
arr @ W                     # 矩阵乘法 (等价于np.dot)
arr.mean(), arr.std()       # 均值/标准差
arr.sum(axis=0)             # 按列求和
np.concatenate([a,b], axis=0) # 拼接
np.stack([a,b], axis=0)     # 堆叠
np.linalg.norm(arr)         # 范数
np.argmax(arr)              # 最大索引
np.unique(arr)              # 去重排序
np.clip(arr, 0, 1)          # 截断
"""

# =========================================================
# PART 4: 数学公式速查（选择题计算用）
# =========================================================

"""
【方差公式】Var(aX + b) = a² · Var(X)
  例: X 方差=4, Y=3X+2, 则Var(Y)=9×4=36 ★高频

【协方差矩阵】σ_ij = E[(X_i-μ_i)(X_j-μ_j)]
  PCA通过对协方差矩阵特征值分解找主成分

【贝叶斯公式】P(A|B) = P(B|A)P(A)/P(B)

【信息熵】H(X) = -Σ p(x)log p(x)

【似然函数】L(θ) = Π p(x_i|θ)
  取对数便于计算 → logL(θ) = Σ log p(x_i|θ)

【矩阵乘法】C_ij = Σ_k A_ik · B_kj
  A(m×n) × B(n×p) = C(m×p)
"""

# =========================================================
# PART 5: 选择题计算题模板
# =========================================================

def calc_f1(tp, fp, fn, tn):
    """计算F1-score"""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return round(f1, 2)

def calc_var_after_transform(var_x, a, b):
    """Var(aX+b) = a²Var(X)"""
    return a ** 2 * var_x

def is_prime(n):
    """质数判断"""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True

def cross_entropy_loss(y_true, y_pred):
    """交叉熵损失"""
    y_pred = np.clip(y_pred, 1e-15, 1 - 1e-15)
    return -np.mean(y_true * np.log(y_pred) + (1 - y_true) * np.log(1 - y_pred))


# =========================================================
# PART 6: PyTorch 场景 （简答题/写伪代码用）
# =========================================================

"""
=== PyTorch 完整训练模板 ===
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

class MyDataset(Dataset):
    def __init__(self, X, y):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.long)
    def __len__(self): return len(self.X)
    def __getitem__(self, idx): return self.X[idx], self.y[idx]

class MyModel(nn.Module):
    def __init__(self, in_dim, num_classes):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(128, num_classes)
        )
    def forward(self, x): return self.net(x)

# model = MyModel(784, 10).to(device)
# criterion = nn.CrossEntropyLoss()
# optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

=== mixed precision ===
# from torch.cuda.amp import autocast, GradScaler
# scaler = GradScaler()
# with autocast(): logits = model(x); loss = criterion(logits, y)
# scaler.scale(loss).backward(); scaler.step(optimizer); scaler.update()

=== 模型保存 ===
# torch.save(model.state_dict(), 'model.pth')
# model.load_state_dict(torch.load('model.pth'))
"""