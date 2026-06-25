import heapq
import sys


def main():
    data = sys.stdin.read().split()
    ptr = 0
    n = int(data[ptr])
    ptr += 1
    k = int(data[ptr])
    ptr += 1
    nums = list(map(int, data[ptr:ptr + n]))

    total_sum = sum(nums)
    heap = []
    # 第一步：拆分初始连续正数段，存入大根堆（python只有小根堆，存负数模拟）
    i = 0
    while i < n:
        if nums[i] > 0:
            j = i
            while j < n and nums[j] > 0:
                j += 1
            seg_len = j - i
            heapq.heappush(heap, -seg_len)
            i = j
        else:
            i += 1

    reduce_total = 0
    op_times = k

    while op_times > 0 and heap:
        cur_len = -heapq.heappop(heap)  # 取出当前最长段
        if cur_len == 0:
            continue
        # 执行一次操作，总和减少cur_len
        reduce_total += cur_len
        op_times -= 1
        # 该段整体-1后，两端各少1个正数，拆成左右两段
        left = cur_len - 1
        right = 0
        # 举例：长度5段，减1后变成 [x,x,x,x,0] → 左段长度4
        # 长度3段，减1后 [x,0,x] → 左1 右1
        # 拆分逻辑：减1后，最右侧变为0，剩下左侧连续；若原段中间无0，只会拆出左段；
        # 简化处理：原长L-1会分成两段 [a,0,b]，a+b = L-1，最优贪心直接拆成1和L-2，等价全部子段入堆
        # 等价简化：长度L操作一次后，分裂为 1 和 L-2（若大于0）
        if cur_len - 1 > 0:
            # 模拟减1后中间出现0，分割为左右两小段
            if 1 > 0:
                heapq.heappush(heap, -1)
            if (cur_len - 2) > 0:
                heapq.heappush(heap, -(cur_len - 2))

    print(total_sum - reduce_total)


if __name__ == "__main__":
    main()
    # Get-Content 输入.txt -Raw | python test.py
'''
def main():
    import sys
    from collections import defaultdict
    input_lines = sys.stdin.read().splitlines()
    # 第一行：模块列表
    mods_line = input_lines[0].strip()
    mods = mods_line.split(',')
    n = len(mods)
    mod_set = set(mods)
    # 建图、入度
    graph = defaultdict(list)
    in_degree = defaultdict(int)
    for m in mods:
        in_degree[m] = 0
    # 第二行依赖关系
    dep_line = input_lines[1].strip()
    deps = dep_line.split()
    for d in deps:
        a, b = d.split(',')  # a依赖b 边 b -> a
        graph[b].append(a)
        in_degree[a] += 1

    res = []
    # 回溯枚举所有拓扑序
    def backtrack(path, curr_in):
        if len(path) == n:
            res.append(path.copy())
            return
        # 按字典序遍历候选，保证生成有序，最后再统一排序
        candidates = [m for m in mods if curr_in[m] == 0 and m not in path]
        for node in sorted(candidates):
            path.append(node)
            # 临时修改入度
            for neighbor in graph[node]:
                curr_in[neighbor] -= 1
            backtrack(path, curr_in)
            # 回溯恢复
            for neighbor in graph[node]:
                curr_in[neighbor] += 1
            path.pop()

    # 拷贝初始入度用于回溯
    init_in = in_degree.copy()
    backtrack([], init_in)

    if not res:
        print("NULL")
    else:
        # 全部合法序列字典序排序
        res.sort()
        for seq in res:
            print(' '.join(seq))
'''
'''
def main():
    x = x-x.mean(axis=0, keepdims=True)
    x = np.hstack([np.ones((T, B, 1)),x])
    for _ in range(Iteration):
        pred = sigmoid(x @ Wx + b)
        grad = x.T @ (pred - Y)
        Wx -= lr * grad
'''
'''
    lines = []
    for line in sys.stdin:
        s = line.strip()
        if s:
            lines.append(s)
    # 解析三行输入
    target_month = int(lines[0])
    name_list = lines[1].split()
    date_list = lines[2].split()
'''
'''
    lines = [line.strip() for line in sys.stdin if line.strip()]
    # 解析三行输入
    target_dir = lines[0]
    path_arr = lines[1].split()
    size_arr = list(map(int, lines[2].split()))

    # 统一目录格式，末尾加 /
    prefix = target_dir if target_dir.endswith("/") else target_dir + "/"
    sub_size = dict()
'''