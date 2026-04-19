def straight_line(x: int) -> int:
    y = x + 1
    z = y * 2
    return z


def with_if(x: int) -> int:
    if x > 0:
        return x
    return 0


def deeply_nested(items: list[int]) -> int:
    total = 0
    for item in items:
        if item > 0:
            if item % 2 == 0:
                total += item
            else:
                total -= item
        elif item == 0:
            total = total
        else:
            try:
                total -= abs(item)
            except ValueError:
                total = 0
    return total


def boolean_ops(a: int, b: int, c: int) -> bool:
    return a > 0 and b > 0 or c > 0


def comprehension_example(items: list[int]) -> list[int]:
    return [i * 2 for i in items if i > 0]


def ternary_example(a: int, b: int) -> int:
    return a if a > b else b
