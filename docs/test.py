import sys


# If you need to import additional packages or classes, please import here.

def func():
    tokens = sys.stdin.readlines()
    first = tokens[0]

    N, L, K = first.split()
    N, L, K=int(N), int(L), int(K)
    sign = []
    for _ in range(N):
        sign=tokens[_].split()
    cents = tokens[N + 1].split()
    test = []
    print(cents)
    # print("9 2 8\n12 6 4")
    # please define the python3 input here. For example: a,b = map(int, input().strip().split())
    # please finish the function body here.
    # please define the python3 output here. For example: print().


if __name__ == "__main__":
    func()
