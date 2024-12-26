from sanguine.common import *

_proc_num: int = -1  # number of child process


def current_proc_num() -> int:
    global _proc_num
    return _proc_num


def set_current_proc_num(proc_num: int) -> None:
    global _proc_num
    _proc_num = proc_num


class LambdaReplacement:
    f: Callable[[any, any], any]
    capture: any

    def __init__(self, f: Callable[[any, any], any], capture: any) -> None:
        self.f = f
        self.capture = capture

    def call(self, param: any) -> any:
        return self.f(self.capture, param)


class Task:
    name: str
    f: Callable[[any, ...], any] | None  # variable # of params depending on len(dependencies)
    param: any
    dependencies: list[str]
    w: float | None

    def __init__(self, name: str, f: Callable, param: any, dependencies: list[str], w: float | None = None) -> None:
        self.name = name
        self.f = f
        self.param = param
        self.dependencies = dependencies
        self.w: float = w


class OwnTask(Task):
    pass


class TaskPlaceholder(Task):
    def __init__(self, name: str) -> None:
        super().__init__(name, lambda: None, None, [])


type TaskStatsOfInterest = list[str]


class ProcessStarted:
    def __init__(self, proc_num: int) -> None:
        self.proc_num = proc_num

# class _Finished:
#    def __init__(self, proc_num: int) -> None:
#        self.proc_num = proc_num
