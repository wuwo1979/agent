"""
==========================================================
华为AI岗机考 - 编程题真题 + 参考代码
AI岗编程题特点：结合机器学习/深度学习场景
  - 题1（150分）：AI场景模拟/数据处理（如语料清洗、逻辑回归、LSTM）
  - 题2（300分）：AI系统优化/复杂算法（如MOE路由、流水线并行）
==========================================================
"""

# =========================================================
# 真题1: LSTM 前向传播（2026.04.29 AI岗真题）
# 描述：给定输入x_t, 上一时刻隐状态h_{t-1}, 上一时刻细胞状态c_{t-1},
#       按LSTM公式计算h_t和c_t（含四个门）
# 输入: x_t (d维向量), h_{t-1} (h维向量), c_{t-1} (h维向量),
#       以及8个矩阵 W_f, W_i, W_o, W_c (每个h×(d+h))
# 输出: h_t, c_t
# =========================================================
import numpy as np

def lstm_forward(x_t, h_prev, c_prev, params):
    """
    LSTM单步前向传播
    x_t: (d,), h_prev: (h,), c_prev: (h,)
    params: dict with keys 'W_f','W_i','W_o','W_c','b_f','b_i','b_o','b_c'
            每个W是(h, d+h), 每个b是(h,)
    """
    # ★拼接 x_t 和 h_{t-1}
    combined = np.concatenate([x_t, h_prev])  # (d+h,)

    # ★四个门的计算
    f = sigmoid(params['W_f'] @ combined + params['b_f'])  # 遗忘门
    i = sigmoid(params['W_i'] @ combined + params['b_i'])  # 输入门
    o = sigmoid(params['W_o'] @ combined + params['b_o'])  # 输出门
    c_tilde = np.tanh(params['W_c'] @ combined + params['b_c'])  # 候选细胞

    # 更新细胞状态和隐状态
    c_t = f * c_prev + i * c_tilde    # ★细胞状态更新
    h_t = o * np.tanh(c_t)            # ★隐状态更新

    return h_t, c_t

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

# --- 测试 ---
# d, h = 3, 4
# np.random.seed(42)
# x_t = np.random.randn(d)
# h_prev = np.zeros(h)
# c_prev = np.zeros(h)
# params = {k: np.random.randn(h, d+h) for k in ['W_f','W_i','W_o','W_c']}
# params.update({k: np.zeros(h) for k in ['b_f','b_i','b_o','b_c']})
# h_t, c_t = lstm_forward(x_t, h_prev, c_prev, params)
# print(h_t, c_t)


# =========================================================
# 真题2: 大模型语料清洗（2026.04.29 AI岗真题）
# 描述：对语料应用多条清洗规则：
#   1. 删除HTML标签 <...>
#   2. 将连续空格/制表符替换为单个空格
#   3. 删除URL链接 http:// 或 https://
#   4. 将全角符号转为半角
#   5. 删除行首行尾空白
# 输入: 多行文本
# 输出: 清洗后文本
# =========================================================
import re

def clean_corpus(text):
    # ★规则1: 删除HTML标签
    text = re.sub(r'<[^>]+>', '', text)

    # ★规则2: 将连续空白符替换为单个空格
    text = re.sub(r'[ \t]+', ' ', text)

    # ★规则3: 删除URL
    text = re.sub(r'https?://\S+', '', text)

    # ★规则4: 全角转半角
    result = []
    for c in text:
        code = ord(c)
        if 0xFF01 <= code <= 0xFF5E:        # 全角符号
            result.append(chr(code - 0xFEE0))
        elif code == 0x3000:                 # 全角空格
            result.append(chr(0x0020))
        else:
            result.append(c)
    text = ''.join(result)

    # ★规则5: 去除行首行尾空白
    text = text.strip()

    return text


# =========================================================
# 真题3: 云存储故障预测 — 逻辑回归（2025.09.03 AI岗真题）
# 描述：数据清洗 + 逻辑回归批量梯度下降做二分类预测
# 输入: 训练数据(特征+标签), 预测数据(特征)
# 输出: 预测标签
# =========================================================
import pandas as pd
import numpy as np

def logistic_regression_train(X, y, lr=0.01, epochs=1000):
    """
    批量梯度下降训练逻辑回归
    X: (N, D), y: (N,)
    """
    N, D = X.shape
    # ★特征标准化
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std[std == 0] = 1
    X_norm = (X - mean) / std

    # ★添加偏置项
    X_norm = np.hstack([np.ones((N, 1)), X_norm])

    # ★初始化权重为零（避免初始化偏差）
    w = np.zeros(D + 1)

    for epoch in range(epochs):
        z = X_norm @ w
        pred = 1 / (1 + np.exp(-z))  # ★sigmoid
        grad = (1 / N) * X_norm.T @ (pred - y)  # ★梯度
        w -= lr * grad  # ★梯度下降更新

    return w, mean, std

def logistic_regression_predict(X, w, mean, std):
    """逻辑回归预测"""
    X_norm = (X - mean) / std
    X_norm = np.hstack([np.ones((X.shape[0], 1)), X_norm])
    z = X_norm @ w
    pred = 1 / (1 + np.exp(-z))
    return (pred >= 0.5).astype(int)


# =========================================================
# 真题4: MOE路由优化（2025.09.03 AI岗真题 — 300分）
# 描述：M个专家分成NPU组，给定路由矩阵，找目标专家
# 输入:
#   M, N, k: 专家数, NPU数, 目标专家数
#   routing_matrix: N×M 矩阵
#   target_npu: 目标NPU编号
# 输出: 按某规则排序后的k个专家编号
# =========================================================
def moe_routing(M, N, k, routing_matrix, target_npu):
    """
    M个专家, N个NPU, k个目标专家
    routing_matrix[N][M]
    1) 专家按NPU分组（编号连续）
    2) 先筛选target_npu的专家
    3) 再筛选目标专家
    """
    # ★检查专家数能否被NPU数整除
    if M % N != 0:
        return []

    experts_per_npu = M // N

    # ★获取目标NPU的专家范围
    start = target_npu * experts_per_npu
    end = start + experts_per_npu
    npu_experts = list(range(start, end))

    # ★筛选目标专家（按routing matrix中某列的权重排序选取前k个）
    scores = [(routing_matrix[target_npu][e], e) for e in npu_experts]
    scores.sort(key=lambda x: -x[0])  # ★降序

    selected = [e for _, e in scores[:k]]
    return selected


# =========================================================
# 真题5: 流水线并行训练优化（2026.05.27 AI岗真题）
# 描述：求最优的模型层划分点，使流水线训练总时间最短
# 本质：分割数组使各段最大值之和最小 → 二分答案
# 输入: 各层计算时间数组 layers[N], 流水线设备数 P
# 输出: 最小化最大段和
# =========================================================
def minimize_pipeline_time(layers, P):
    """
    layers: 每层计算时间
    P: 流水线设备数（切P段）
    二分搜索最小的"最大段和"
    """
    def can_split(limit):
        """判断能否将数组分成<=P段，每段和<=limit"""
        cnt = 1
        cur_sum = 0
        for t in layers:
            if cur_sum + t > limit:
                cnt += 1
                cur_sum = t
                if cnt > P:
                    return False
            else:
                cur_sum += t
        return True

    left = max(layers)      # ★下界：最大单层时间
    right = sum(layers)     # ★上界：所有层时间总和

    while left < right:
        mid = (left + right) // 2
        if can_split(mid):
            right = mid
        else:
            left = mid + 1

    return left


# =========================================================
# 真题6: 流式日志Top-K高频统计（2026.05.27 AI岗真题）
# 描述：流式统计出现频率最高的K个元素
# 本质：有序集合（Counter + 堆）
# =========================================================
from collections import Counter
import heapq

def top_k_frequent(elements, k):
    """
    elements: 流式日志元素列表
    k: 返回频率最高的k个
    """
    # ★用Counter统计频率
    counter = Counter(elements)
    # ★用大小为k的最小堆求top-k
    heap = []
    for key, freq in counter.items():
        heapq.heappush(heap, (freq, key))
        if len(heap) > k:
            heapq.heappop(heap)  # ★弹出最小的

    result = []
    while heap:
        result.append(heapq.heappop(heap)[1])
    return result[::-1]  # ★频率从高到低


# =========================================================
# 真题7: 随机森林交易风控算法（2026.05.22 AI岗真题）
# 描述：模拟多棵决策树的投票/平均过程做二分类
# =========================================================
def random_forest_vote(predictions, threshold=0.5):
    """
    predictions: (n_trees, n_samples) 每棵树对每个样本的预测概率
    return: 投票后的最终预测
    """
    n_trees, n_samples = predictions.shape
    # ★平均概率
    avg_prob = predictions.mean(axis=0)
    return (avg_prob >= threshold).astype(int)


# =========================================================
# 真题8: 数据清洗模板（华为AI岗高频）
# 描述：处理缺失值、均值填充、异常值处理
# =========================================================
def data_cleaning(df):
    """
    df: pandas DataFrame
    """
    # ★1. 异常值处理（先剔除异常值，再用剩余数据求均值）
    for col in df.columns:
        if df[col].dtype in ['int64', 'float64']:
            # IQR法检测异常值
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            lower = Q1 - 1.5 * IQR
            upper = Q3 + 1.5 * IQR
            # 标记正常值
            mask = (df[col] >= lower) & (df[col] <= upper)
            # 用正常值的均值填充缺失值
            mean_val = df.loc[mask, col].mean()
            df[col] = df[col].fillna(mean_val)
    return df


# =========================================================
# OJ 输入输出模板（AI岗专用）
# =========================================================
"""
华为AI岗编程题输入输出通常有两种形式：

形式1: 传统OJ格式（与普通岗相同）
  输入:
  M N k
  routing_matrix行...
  target_npu

形式2: 数据框格式（CSV/表格类）
  输入:
  feature1,feature2,feature3,label
  1.2,3.4,5.6,0
  7.8,9.0,1.2,1
  ---
  feature1,feature2,feature3
  4.5,6.7,8.9
  """

def io_template_csv():
    import sys
    lines = sys.stdin.read().strip().split('\n')
    # ★查找分隔符
    separator_idx = None
    for i, line in enumerate(lines):
        if line.strip() == '---':
            separator_idx = i
            break

    if separator_idx is not None:
        # 训练数据
        train_lines = lines[1:separator_idx]
        header = lines[0].split(',')
        train_data = [line.split(',') for line in train_lines]
        # 预测数据
        pred_lines = lines[separator_idx+2:]
        pred_header = lines[separator_idx+1].split(',')

        # 后续处理...

# 通用模板
def io_template_standard():
    import sys
    data = sys.stdin.read().strip().split()
    # 或按行读取
    # for line in sys.stdin:
    #     ...