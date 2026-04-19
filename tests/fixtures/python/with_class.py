def module_level() -> int:
    return 42


class Worker:
    def do_work(self) -> int:
        return module_level()

    def other(self) -> int:
        return self.do_work()
