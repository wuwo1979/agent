import sys
import math


# If you need to import additional packages or classes, please import here.

def func():
    tokens = sys.stdin.readline().strip().split()
    if not tokens:
        print("-1 -1")
        return
    if len(tokens) < 4:
        print("-1 -1")
        return
    for _ in tokens:
        if "." in _:
            print("-1 -1")
            return
    lsum, lsig, micnum, card = int(tokens[0]), int(tokens[1]), int(tokens[2]), int(tokens[3])
    # print(lsum, lsig, micnum, card)
    res = []
    def cal_b(m, pp):  # 气泡
        return float((pp - 1) / (m + pp - 1)) if m + pp - 1 > 0 else 0.0

    for i in range(1, card + 1):  # 1
        m = lsum // i
        #print(m)
        if lsum != m*i: continue  # 2
        if m > lsig: continue  # 3
        #if i * card < lsum: continue  # 0
        res.append([cal_b(micnum, i), i])
    if not res:
        print("-1 -1")
        return
    res.sort(key=lambda x: (x[0], x[1]))
    # print(res)
    print(res[0][1], f'{res[0][0]:.4f}')
    # please define the python3 input here. For example: a,b = map(int, input().strip().split())
    # please finish the function body here.
    # please define the python3 output here. For example: print().


if __name__ == "__main__":
    func()
