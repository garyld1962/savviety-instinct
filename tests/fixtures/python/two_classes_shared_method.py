def inner_a() -> int:
    return 1


def inner_b() -> int:
    return 2


class A:
    def run(self) -> int:
        return inner_a()


class B:
    def run(self) -> int:
        return inner_b()
