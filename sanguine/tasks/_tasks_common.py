from sanguine.common import *

_proc_num: int = -1  # number of child process


def current_proc_num() -> int:
    global _proc_num
    return _proc_num


def set_current_proc_num(proc_num: int) -> None:
    global _proc_num
    _proc_num = proc_num


def is_lambda(func: Callable) -> bool:
    return callable(func) and func.__name__ == '<lambda>'


class LambdaReplacement:
    f: Callable[[any, any], any]
    capture: any

    def __init__(self, f: Callable[[any, any], any], capture: any) -> None:
        self.f = f
        self.capture = capture

    def call(self, param: any) -> any:
        return self.f(self.capture, param)


class TaskDataDependencies:
    required_tags: list[str]
    required_not_tags: list[str]
    provided_tags: list[str]

    def __init__(self, reqtags: list[str], reqnottags: list[str], provtags: list[str]) -> None:
        self.required_tags = reqtags
        self.required_not_tags = reqnottags
        self.provided_tags = provtags


class Task:
    name: str
    f: Callable[[any, ...], any] | None  # variable # of params depending on len(dependencies)
    param: any
    dependencies: list[str]
    w: float | None
    data_dependencies: TaskDataDependencies

    def __init__(self, name: str, f: Callable, param: any, dependencies: list[str], w: float | None = None,
                 datadeps: TaskDataDependencies = None) -> None:
        self.name = name
        self.f = f
        self.param = param
        self.dependencies = dependencies
        self.w: float = w
        self.data_dependencies = datadeps


class OwnTask(Task):
    pass


class TaskPlaceholder(Task):
    def __init__(self, name: str) -> None:
        super().__init__(name, lambda: None, None, [])


type TaskStatsOfInterest = list[str]


class ProcessStarted:
    def __init__(self, proc_num: int) -> None:
        self.proc_num = proc_num
