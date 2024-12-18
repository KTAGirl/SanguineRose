# mini-micro <s>skirt</s>, sorry, lib for data-driven parallel processing

import logging
import time
from enum import IntEnum
from multiprocessing import Process, Queue as PQueue, shared_memory
from threading import Thread  # only for logging!

from sanguine.common import *
# noinspection PyProtectedMember
from sanguine.helpers._logging import add_logging_handler, log_to_file_only, logging_started

_proc_num: int = -1  # number of child process


# def this_proc_num() -> int:
#    global _proc_num
#    return _proc_num


class _ChildProcessLogHandler(logging.StreamHandler):
    logq: PQueue

    def __init__(self, logq: PQueue) -> None:
        super().__init__()
        self.logq = logq

    def emit(self, record: logging.LogRecord) -> None:
        global _proc_num
        self.logq.put((_proc_num, time.perf_counter(), record))


class SharedReturn:
    shm: shared_memory.SharedMemory
    closed: bool

    def __init__(self, item: any):
        data = pickle.dumps(item)
        self.shm = shared_memory.SharedMemory(create=True, size=len(data))
        shared = self.shm.buf
        shared[:] = data
        _pool_of_shared_returns.register(self)
        self.closed = False

    def name(self) -> str:
        return self.shm.name

    def close(self) -> None:
        if not self.closed:
            self.shm.close()
            self.closed = True

    def __del__(self) -> None:
        self.close()


class _PoolOfSharedReturns:
    shareds: dict[str, SharedReturn]

    def __init__(self) -> None:
        self.shareds = {}

    def register(self, shared: SharedReturn) -> None:
        self.shareds[shared.name()] = shared

    def done_with(self, name: str) -> None:
        shared = self.shareds[name]
        shared.close()
        del self.shareds[name]

    def cleanup(self) -> None:
        for name in self.shareds:
            shared = self.shareds[name]
            shared.close()
        self.shareds = {}

    def __del__(self) -> None:
        self.cleanup()


_pool_of_shared_returns = _PoolOfSharedReturns()


# def _log_time() -> float:
#    return time.perf_counter() - _started


class SharedPublication:
    shm: shared_memory.SharedMemory
    closed: bool

    def __init__(self, parallel: "Parallel", item: any):
        data = pickle.dumps(item)
        self.shm = shared_memory.SharedMemory(create=True, size=len(data))
        shared = self.shm.buf
        shared[:] = data
        name = self.shm.name
        debug('SharedPublication: {}'.format(name))
        assert name not in parallel.publications
        parallel.publications[name] = self.shm
        self.closed = False

    def name(self) -> str:
        return self.shm.name

    def close(self) -> None:
        if not self.closed:
            self.shm.close()
            self.closed = True

    def __del__(self) -> None:
        self.close()


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
    f: Callable[[any, ...], any]  # variable # of params depending on len(dependencies)
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


def _run_task(task: Task, depparams: list[any]) -> (Exception | None, any):
    ndep = len(depparams)
    assert ndep <= 3
    try:
        match ndep:
            case 0:
                out = task.f(task.param)
            case 1:
                out = task.f(task.param, depparams[0])
            case 2:
                out = task.f(task.param, depparams[0], depparams[1])
            case 3:
                out = task.f(task.param, depparams[0], depparams[1], depparams[2])
            case _:
                assert False
        return None, out
    except Exception as e:
        critical('Parallel: exception in task {}: {}'.format(task.name, e))
        warn(traceback.format_exc())
        return e, None


type SharedReturnParam = tuple[str, int]


def make_shared_return_param(shared: SharedReturn) -> SharedReturnParam:
    # assert _proc_num>=0
    global _proc_num
    return shared.name(), _proc_num


# def log_process_prefix() -> str:
#    global _proc_num
#    return 'Process #{}: '.format(_proc_num + 1)


type SharedPubParam = str


def make_shared_publication_param(shared: SharedPublication) -> str:
    return shared.name()


_cache_of_published: dict[str, any] = {}  # per-process cache of published data


def from_publication(sharedparam: SharedPubParam, should_cache=True) -> any:
    found = _cache_of_published.get(sharedparam)
    if found is not None:
        return found
    shm = shared_memory.SharedMemory(sharedparam)
    out = pickle.loads(shm.buf)
    if should_cache:
        _cache_of_published[sharedparam] = out
    return out


def _log_proc_func(loqq: PQueue) -> None:
    while True:
        record = loqq.get()
        if record is None:
            break
        (procnum, t, rec) = record
        rec.sanguine_when = t - logging_started()
        rec.sanguine_prefix = 'Process #{}: '.format(procnum + 1)
        log_to_file_only(rec)


class _Started:
    def __init__(self, proc_num: int) -> None:
        self.proc_num = proc_num


def _process_nonown_tasks(tasks: list[list], dwait: float | None) -> tuple[Exception | None, any]:
    assert isinstance(tasks, list)
    outtasks: list[tuple[str, tuple[float, float], any]] = []
    for tplus in tasks:
        task = tplus[0]
        ndep = len(task.dependencies)
        assert len(tplus) == 1 + ndep
        t0 = time.perf_counter()
        tp0 = time.process_time()
        if dwait is not None:
            info('after waiting for {:.2f}s, starting task {}'.format(dwait, task.name))
            dwait = None
        else:
            info('starting task {}'.format(task.name))
        (ex, out) = _run_task(task, tplus[1:])
        if ex is not None:
            return ex, None  # for tplus
        elapsed = time.perf_counter() - t0
        cpu = time.process_time() - tp0
        info('done task {}, cpu/elapsed={:.2f}/{:.2f}s'.format(task.name, cpu, elapsed))
        outtasks.append((task.name, (cpu, elapsed), out))
        # end of for tplus
    return None, outtasks


def _proc_func(proc_num: int, inq: PQueue, outq: PQueue, logq: PQueue) -> None:
    try:
        global _proc_num
        assert _proc_num == -1
        _proc_num = proc_num

        add_logging_handler(_ChildProcessLogHandler(logq))

        debug('Process started')
        outq.put(_Started(_proc_num))
        ex = None
        while True:
            waitt0 = time.perf_counter()
            msg = inq.get()
            if msg is None:
                break  # while True

            dwait = time.perf_counter() - waitt0

            (tasks, processedshm) = msg
            if processedshm is not None:
                assert tasks is None
                info('after waiting for {:.2f}s, releasing shm={}'.format(dwait, processedshm))
                _pool_of_shared_returns.done_with(processedshm)
                continue  # while True

            ex, outtasks = _process_nonown_tasks(tasks, dwait)
            if ex is not None:
                break  # while True
            outq.put((proc_num, outtasks))
            # end of while True

        if ex is not None:
            outq.put(ex)
    except Exception as e:
        critical('_proc_func() internal exception: {}'.format(e))
        warn(traceback.format_exc())
        outq.put(e)
    _pool_of_shared_returns.cleanup()
    debug('exiting process')


class _TaskGraphNodeState(IntEnum):
    Pending = 0,
    Ready = 1,
    Running = 2,
    Done = 3


class _TaskGraphNode:
    task: Task
    children: list["_TaskGraphNode"]
    parents: list["_TaskGraphNode|str"]
    own_weight: float
    max_leaf_weight: float
    explicit_weight: bool
    state: _TaskGraphNodeState
    waiting_for_n_deps: int

    def __init__(self, task: Task, parents: list["_TaskGraphNode"], weight: float, explicit_weight: bool) -> None:
        self.task = task
        self.children = []
        self.parents = parents
        self.own_weight = weight  # expected time in seconds
        self.max_leaf_weight = 0.
        self.explicit_weight = explicit_weight
        self.state = _TaskGraphNodeState.Pending
        self.waiting_for_n_deps = 0

    def mark_as_done_and_handle_children(self, pending: dict[str, "_TaskGraphNode"],
                                         ready: dict[str, tuple["_TaskGraphNode", float]],
                                         ready_own: dict[str, tuple["_TaskGraphNode", float]]) -> None:
        assert self.state == _TaskGraphNodeState.Ready or self.state == _TaskGraphNodeState.Running
        self.state = _TaskGraphNodeState.Done
        for ch in self.children:
            assert ch.state == _TaskGraphNodeState.Pending
            assert ch.waiting_for_n_deps > 0
            ch.waiting_for_n_deps -= 1
            if ch.waiting_for_n_deps == 0:
                ch.state = _TaskGraphNodeState.Ready
                assert ch.task.name not in ready
                assert ch.task.name not in ready_own
                assert ch.task.name in pending
                debug('Parallel: task {} is ready'.format(ch.task.name))
                del pending[ch.task.name]
                if isinstance(ch.task, OwnTask):
                    ready_own[ch.task.name] = (ch, ch.total_weight())
                else:
                    ready[ch.task.name] = (ch, ch.total_weight())
            else:
                debug('Parallel: task {} has {} remaining dependencies to become ready'.format(
                    ch.task.name, ch.waiting_for_n_deps))

    def append_leaf(self, leaf: "_TaskGraphNode") -> None:
        self.children.append(leaf)
        self._adjust_leaf_weight(leaf.own_weight)

    def _adjust_leaf_weight(self, w: float) -> None:
        if self.max_leaf_weight < w:
            self.max_leaf_weight = w
            for p in self.parents:
                if isinstance(p, str) or int(p.state) >= int(_TaskGraphNodeState.Ready):
                    continue
                p._adjust_leaf_weight(self.own_weight + self.max_leaf_weight)

    def total_weight(self) -> float:
        return self.own_weight + self.max_leaf_weight


class Parallel:
    outq: PQueue
    logq: PQueue
    processes: list[Process]
    processesload: list[int]  # we'll aim to have it at 1; improvements to keep pressure are possible,
    inqueues: list[PQueue]
    procrunningconfirmed: list[bool]  # otherwise join() on a not running yet process may hang
    logthread: Thread

    nprocesses: int
    json_fname: str
    json_weights: dict[str, float]
    updated_json_weights: dict[str, float]

    shutting_down: bool
    has_joined: bool

    publications: dict[str, shared_memory.SharedMemory]
    all_task_nodes: dict[str, _TaskGraphNode]  # name->node
    pending_task_nodes: dict[str, _TaskGraphNode]  # name->node
    ready_task_nodes: dict[str, tuple[_TaskGraphNode, float]]  # name->node
    ready_own_task_nodes: dict[str, tuple[_TaskGraphNode, float]]  # name->node
    running_task_nodes: dict[str, tuple[int, float, _TaskGraphNode]]  # name->(procnum,started,node)
    done_task_nodes: dict[str, tuple[_TaskGraphNode, any]]  # name->(node,out)
    pending_patterns: list[tuple[str, _TaskGraphNode]]  # pattern, node
    dbg_serialize: bool

    def __init__(self, jsonfname: str | None, nproc: int = 0, dbg_serialize: bool = False) -> None:
        # dbg_serialize allows debugging non-own Tasks
        global _proc_num
        assert _proc_num == -1

        assert nproc >= 0
        if nproc:
            self.nprocesses = nproc
        else:
            self.nprocesses = os.cpu_count() - 1  # -1 for the master process
        assert self.nprocesses >= 0
        self.dbg_serialize = dbg_serialize
        info('Parallel: using {} processes...'.format(self.nprocesses))
        self.json_fname = jsonfname
        self.json_weights = {}
        self.updated_json_weights = {}
        if jsonfname is not None:
            try:
                with open(jsonfname, 'rt', encoding='utf-8') as rf:
                    self.json_weights = json.load(rf)
            except Exception as e:
                warn('error loading JSON weights from {}: {}. Will continue w/o weights'.format(jsonfname, e))
                self.json_weights = {}  # just in case

        self.shutting_down = False
        self.has_joined = False

        self.publications = {}

        self.all_task_nodes = {}
        self.pending_task_nodes = {}
        self.ready_task_nodes = {}
        self.ready_own_task_nodes = {}
        self.running_task_nodes = {}  # name->(procnum,started,node)
        self.done_task_nodes = {}  # name->(node,out)
        self.pending_patterns = []

    def __enter__(self) -> "Parallel":
        self.processes = []
        self.processesload = []  # we'll aim to have it at 1; improvements to keep pressure are possible,
        # but not as keeping simplistic processesload[i] == 2 (it disbalances end of processing way too much)
        self.inqueues = []
        self.procrunningconfirmed = []  # otherwise join() on a not running yet process may hang
        self.outq = PQueue()
        self.logq = PQueue()
        self.logthread = Thread(target=_log_proc_func, args=(self.logq,))
        self.logthread.start()
        for i in range(self.nprocesses):
            inq = PQueue()
            self.inqueues.append(inq)
            p = Process(target=_proc_func, args=(i, inq, self.outq, self.logq))
            self.processes.append(p)
            p.start()
            self.processesload.append(0)
            self.procrunningconfirmed.append(False)
        self.shutting_down = False
        self.has_joined = False
        assert len(self.processesload) == len(self.processes)
        assert len(self.inqueues) == len(self.processes)
        return self

    def _dependencies_to_parents(self, dependencies: list[str]) -> tuple[list[_TaskGraphNode] | None, list[str] | None]:
        taskparents = []
        patterns = []
        for d in dependencies:
            if d.endswith('*'):
                patterns.append(d[:-1])
                continue
            pnode = self.all_task_nodes.get(d)
            if pnode is None:
                return None, None
            else:
                taskparents.append(pnode)
        return taskparents, patterns

    def _internal_add_task_if(self, task: Task) -> bool:
        global _proc_num
        assert _proc_num == -1

        assert task.name not in self.all_task_nodes
        islambda = callable(task.f) and task.f.__name__ == '<lambda>'
        # if islambda:
        #    print('lambda in task ' + task.name)
        assert isinstance(task, OwnTask) or not islambda

        taskparents, patterns = self._dependencies_to_parents(task.dependencies)
        if taskparents is None:
            assert patterns is None
            return False
        assert patterns is not None
        if __debug__:
            for p in taskparents:
                assert isinstance(p, _TaskGraphNode)

        w = task.w
        explicitw = True
        if w is None:
            explicitw = False
            w = 0.1 if isinstance(task,
                                  OwnTask) else 1.0  # 1 sec for non-owning tasks, and assuming that own tasks are shorter by default (they should be)
            w = self.estimated_time(task.name, w)
        node = _TaskGraphNode(task, taskparents, w, explicitw)
        self.all_task_nodes[task.name] = node

        assert node.waiting_for_n_deps == 0
        for parent in node.parents:
            assert isinstance(parent, _TaskGraphNode)
            parent.append_leaf(node)
            if int(parent.state) < int(_TaskGraphNodeState.Done):
                node.waiting_for_n_deps += 1

        # processing other task's dependencies on this task's patterns
        for p in patterns:
            for n in self.all_task_nodes.values():
                if n.state < _TaskGraphNodeState.Done and n.task.name.startswith(p):
                    node.waiting_for_n_deps += 1
                    n.children.append(node)
                    debug(
                        'Parallel: adding task {} with pattern {}, now it has {} dependencies due to existing task {}'.format(
                            node.task.name, p, node.waiting_for_n_deps, n.task.name))
            node.parents.append(p)
            self.pending_patterns.append((p, node))

        debug('Parallel: added task {}, which is waiting for {} dependencies'.format(node.task.name,
                                                                                     node.waiting_for_n_deps))

        assert node.state == _TaskGraphNodeState.Pending
        if node.waiting_for_n_deps == 0:
            node.state = _TaskGraphNodeState.Ready
            if isinstance(node.task, OwnTask):
                self.ready_own_task_nodes[task.name] = (node, node.total_weight())
            else:
                self.ready_task_nodes[task.name] = (node, node.total_weight())
        else:
            self.pending_task_nodes[task.name] = node

        # processing other task's pattern dependencies on this task
        for pp in self.pending_patterns:
            (p, n) = pp
            if task.name.startswith(p):
                node.children.append(n)
                n.waiting_for_n_deps += 1
                debug('Parallel: task {} now has {} dependencies due to added task {}'.format(n.task.name,
                                                                                              n.waiting_for_n_deps,
                                                                                              node.task.name))

        return True

    def add_tasks(self, tasks: list[Task]) -> None:
        while len(tasks) > 0:
            megaok = False
            for t in tasks:
                ok = self._internal_add_task_if(t)
                if ok:
                    tasks.remove(t)
                    megaok = True
                    break  # for t

            if megaok:
                continue  # while True
            else:
                taskstr = '[\n'
                for task in tasks:
                    taskstr += '    ' + str(task.__dict__) + ',\n'
                taskstr += '\n]'

                critical('Parallel: probable typo in task name or circular dependency: cannot resolve tasks:\n'
                         + taskstr + '\n')
                abort_if_not(False)

    def _run_all_own_tasks(self, owntaskstats: dict[str, tuple[int, float, float]]) -> float:
        town = 0.
        while len(self.ready_own_task_nodes) > 0:
            towntasks = self._run_own_task(
                owntaskstats)  # ATTENTION: own tasks may call add_task() or add_tasks() within
            town += towntasks
        return town

    def run(self, tasks: list[Task]) -> None:
        # building task graph
        self.add_tasks(tasks)

        # graph ok, running the initial tasks
        assert len(self.pending_task_nodes)
        maintstarted = time.perf_counter()
        maintwait = 0.
        maintown = 0.
        maintschedule = 0.
        owntaskstats: dict[str, tuple[int, float, float]] = {}

        # we need to try running own tasks before main loop - otherwise we can get stuck in an endless loop of self._schedule_best_tasks()
        maintown += self._run_all_own_tasks(owntaskstats)

        # main loop
        while True:
            # place items in process queues, until each has 2 tasks, or until there are no tasks
            sch0 = time.perf_counter()
            while self._schedule_best_tasks():
                pass
            maintschedule += (time.perf_counter() - sch0)

            maintown += self._run_all_own_tasks(owntaskstats)

            sch0 = time.perf_counter()
            while self._schedule_best_tasks():  # tasks may have been added by _run_own_tasks(), need to check again
                pass
            maintschedule += (time.perf_counter() - sch0)

            if self.is_all_done():
                break

            # waiting for other processes to report
            waitt0 = time.perf_counter()
            got = self.outq.get()
            if __debug__:  # pickle.dumps is expensive by itself
                debug('Parallel: response size: {}'.format(len(pickle.dumps(got))))
            # warn(str(self.logq.qsize()))
            if isinstance(got, Exception):
                critical('Parallel: An exception within child process reported. Shutting down')

                if not self.shutting_down:
                    self.shutdown()
                info('Parallel: shutdown ok')
                if not self.has_joined:
                    self.join_all()

                critical(
                    'Parallel: All children terminated, aborting due to an exception in a child process. For the exception itself, see log above.')
                # noinspection PyProtectedMember, PyUnresolvedReferences
                os._exit(1)  # if using sys.exit(), confusing logging will occur

            if isinstance(got, _Started):
                self.procrunningconfirmed[got.proc_num] = True
                continue  # while True

            dwait = time.perf_counter() - waitt0
            strwait = '{:.2f}s'.format(dwait)
            maintwait += dwait
            if dwait < 0.005:
                strwait += '[MAIN THREAD SERIALIZATION]'

            (procnum, tasks) = got
            assert self.processesload[procnum] > 0
            self.processesload[procnum] -= 1

            self._process_out_tasks(procnum, tasks, strwait)

            if self.is_all_done():
                break

        maintelapsed = time.perf_counter() - maintstarted
        info(
            'Parallel/main process: waited+owntasks+scheduler+unaccounted=elapsed {:.2f}+{:.2f}+{:.2f}+{:.2f}={:.2f}s, {:.1f}% load'.format(
                maintwait, maintown, maintschedule, maintelapsed - maintwait - maintown - maintschedule,
                maintelapsed, 100 * (1. - maintwait / maintelapsed)))
        info("Parallel: breakdown per task type (task name before '.'):")
        for key, val in owntaskstats.items():
            info('  {}: {}, took {:.2f}/{:.2f}s'.format(key, val[0], val[1], val[2]))

    def _process_out_tasks(self, procnum: int, tasks: list[tuple[str, tuple, any]], strwait: str | None) -> None:
        for taskname, times, out in tasks:
            assert taskname in self.running_task_nodes
            (expectedprocnum, started, node) = self.running_task_nodes[taskname]
            assert node.state == _TaskGraphNodeState.Running
            (cput, taskt) = times
            assert procnum == expectedprocnum
            dt = time.perf_counter() - started
            if strwait is not None:
                info(
                    'Parallel: after waiting for {}, received results of task {} from process {}, elapsed/task/cpu={:.2f}/{:.2f}/{:.2f}s'.format(
                        strwait, taskname, procnum + 1, dt, taskt, cput))
            else:
                info(
                    'Parallel: received results of task {} from process {}, elapsed/task/cpu={:.2f}/{:.2f}/{:.2f}s'.format(
                        taskname, procnum + 1, dt, taskt, cput))

            strwait = None
            self._update_weight(taskname, taskt)
            del self.running_task_nodes[taskname]
            assert taskname not in self.done_task_nodes
            node.mark_as_done_and_handle_children(self.pending_task_nodes, self.ready_task_nodes,
                                                  self.ready_own_task_nodes)
            self.done_task_nodes[taskname] = (node, out)

    def _schedule_best_tasks(self) -> bool:  # may schedule multiple tasks as one meta-task
        pidx = self._find_best_process()
        if pidx < 0:
            return False
        taskpluses = []
        total_time = 0.
        tasksstr = '['
        t0 = time.perf_counter()
        candidates = sorted([tpl for tpl in self.ready_task_nodes.values() if not isinstance(tpl[0].task, OwnTask)],
                            key=lambda tpl: -tpl[1])
        i = 0
        while i < len(candidates) and total_time < 0.1:  # heuristics: <0.1s is not worth jerking around
            node = candidates[i][0]
            assert not isinstance(node.task, OwnTask)
            i += 1
            taskplus = [node.task]
            assert len(node.task.dependencies) == len(node.parents)
            for parent in node.parents:
                if isinstance(parent, _TaskGraphNode):
                    done = self.done_task_nodes[parent.task.name]
                    taskplus.append(done[1])
                else:
                    assert isinstance(parent, str)
            assert len(taskplus) == 1 + len(node.task.dependencies)

            assert node.state == _TaskGraphNodeState.Ready
            assert node.task.name in self.ready_task_nodes
            del self.ready_task_nodes[node.task.name]
            node.state = _TaskGraphNodeState.Running
            self.running_task_nodes[node.task.name] = (pidx, t0, node)

            taskpluses.append(taskplus)
            total_time += node.own_weight
            tasksstr += ',+' + node.task.name

        tasksstr += ']'
        if len(taskpluses) == 0:
            return False

        if self.dbg_serialize:
            ex, out = _process_nonown_tasks(taskpluses, None)
            if ex is not None:
                raise ex
            self._process_out_tasks(pidx, out, None)
            return True

        msg = (taskpluses, None)
        self.inqueues[pidx].put(msg)
        info('Parallel: assigned tasks {} to process #{}'.format(tasksstr, pidx + 1))
        if __debug__:  # pickle.dumps is expensive by itself
            debug('Parallel: request size: {}'.format(len(pickle.dumps(msg))))
        self.processesload[pidx] += 1
        return True

    def _notify_sender_shm_done(self, pidx: int, name: str) -> None:
        if pidx < 0:
            assert pidx == -1
            debug('Parallel: Releasing own shm={}'.format(name))
            _pool_of_shared_returns.done_with(name)
        else:
            self.inqueues[pidx].put((None, name))

    def _run_own_task(self, owntaskstats: dict[str, tuple[int, float, float]]) -> float:
        assert len(self.ready_own_task_nodes) > 0
        towntask = 0.
        best = min(self.ready_own_task_nodes.values(), key=lambda tpl: -tpl[1])

        ot = best[0]
        assert isinstance(ot.task, OwnTask)
        # print('task: '+ot.task.name)
        params = []
        assert len(ot.parents) == len(ot.task.dependencies)
        for p in ot.parents:
            if isinstance(p, _TaskGraphNode):
                param = self.done_task_nodes[p.task.name]
                params.append(param[1])
            else:
                assert isinstance(p, str)

        assert len(params) <= len(ot.task.dependencies)
        assert len(params) <= 3

        info('Parallel: running own task {}'.format(ot.task.name))
        t0 = time.perf_counter()
        tp0 = time.process_time()

        # nall = len(self.all_task_nodes)
        # ATTENTION: ot.task.f(...) may call add_task() or add_task(s) within
        (ex, out) = _run_task(ot.task, params)
        if ex is not None:
            raise Exception('Parallel: Exception in user OwnTask.run(), quitting')
        # newnall = len(self.all_task_nodes)
        # assert newnall >= nall
        # wereadded = newnall > nall

        elapsed = time.perf_counter() - t0
        cpu = time.process_time() - tp0
        info('Parallel: done own task {}, cpu/elapsed={:.2f}/{:.2f}s'.format(
            ot.task.name, cpu, elapsed))
        towntask += elapsed

        lastdot = ot.task.name.rfind('.')
        assert lastdot >= 0
        keystr = ot.task.name[:lastdot]
        oldstat = owntaskstats.get(keystr, (0, 0., 0.))
        owntaskstats[keystr] = (oldstat[0] + 1, oldstat[1] + cpu, oldstat[2] + elapsed)

        self._update_weight(ot.task.name, elapsed)

        assert ot.state == _TaskGraphNodeState.Ready
        assert ot.task.name in self.ready_own_task_nodes
        del self.ready_own_task_nodes[ot.task.name]
        ot.mark_as_done_and_handle_children(self.pending_task_nodes, self.ready_task_nodes, self.ready_own_task_nodes)
        ot.state = _TaskGraphNodeState.Done
        self.done_task_nodes[ot.task.name] = (ot, out)

        return towntask

    def is_all_done(self) -> bool:
        self._stats()
        return len(self.done_task_nodes) == len(self.all_task_nodes)

    def add_task(self, task: Task) -> None:  # to be called from owntask.f()
        assert task.name not in self.all_task_nodes
        added = self._internal_add_task_if(task)
        assert added  # failure to add is ok only during original building of the tree

    def _find_best_process(self) -> int:
        besti = -1
        for i in range(len(self.processesload)):
            pl = self.processesload[i]
            if pl == 0:  # cannot be better
                return i
            # if pl > 1:
            #    continue
            # if besti < 0 or self.processesload[besti] > pl:
            #    besti = i
        return besti

    def received_shared_return(self, sharedparam: SharedReturnParam) -> any:
        (name, sender) = sharedparam
        shm = shared_memory.SharedMemory(name)
        out = pickle.loads(shm.buf)
        self._notify_sender_shm_done(sender, name)
        return out

    def _update_weight(self, taskname: str, dt: float) -> None:
        task = self.all_task_nodes[taskname].task
        if task.w is None:  # if not None - no sense in saving tasks with explicitly specified weights
            oldw = self.json_weights.get(taskname)
            if oldw is None:
                self.updated_json_weights[taskname] = dt
            else:
                self.updated_json_weights[taskname] = (
                                                              oldw + dt) / 2  # heuristics to get some balance between new value and history
        else:
            if abs(task.w - dt) > task.w * 0.3:  # ~30% tolerance
                debug('Parallel: task {}: expected={:.2f}, real={:.2f}'.format(task.name, task.w, dt))

    def estimated_time(self, taskname: str, defaulttime: float) -> float:
        return self.updated_json_weights.get(taskname, self.json_weights.get(taskname, defaulttime))

    def copy_estimates(self) -> dict[str, float]:
        return self.json_weights | self.updated_json_weights

    @staticmethod
    def estimated_time_from_estimates(estimates: dict[str, float], taskname: str, defaulttime: float) -> float:
        return estimates.get(taskname, defaulttime)

    def all_estimates_for_prefix(self, tasknameprefix: str) -> Generator[str, float]:
        lprefix = len(tasknameprefix)
        for tn, t in self.updated_json_weights.items():
            if tn.startswith(tasknameprefix):
                yield tn[lprefix:], t
        for tn, t in self.json_weights.items():
            if tn.startswith(tasknameprefix):
                yield tn[lprefix:], t

    def shutdown(self) -> None:
        assert not self.shutting_down
        for i in range(self.nprocesses):
            self.inqueues[i].put(None)
        self.logq.put(None)
        self.shutting_down = True

    def join_all(self) -> None:
        assert self.shutting_down
        assert not self.has_joined

        n = 0
        while not all(self.procrunningconfirmed):
            if n == 0:
                info(
                    'Parallel: joinAll(): waiting for all processes to confirm start before joining to avoid not started yet join race')
                n = 1
            got = self.outq.get()
            if isinstance(got, _Started):
                self.procrunningconfirmed[got.proc_num] = True
                # debug('Parallel: joinAll(): process #{} confirmed as started',got.procnum+1)

        info('All processes confirmed as started, waiting for joins')
        for i in range(self.nprocesses):
            self.processes[i].join()
            debug('Process #{} joined'.format(i + 1))
        self.logthread.join()
        self.has_joined = True

    def unpublish(self, name: str) -> None:
        pub = self.publications[name]
        pub.close()
        del self.publications[name]

    def _stats(self) -> None:
        info('Parallel: {} tasks, including {} pending, {}/{} ready, {} running, {} done'.format(
            len(self.all_task_nodes), len(self.pending_task_nodes), len(self.ready_task_nodes),
            len(self.ready_own_task_nodes), len(self.running_task_nodes), len(self.done_task_nodes))
        )
        if __debug__:
            debug(
                'Parallel: pending tasks (up to 10 first): {}'.format(repr([t for t in self.pending_task_nodes][:10])))
            debug('Parallel: ready tasks (up to 10 first): {}'.format(repr([t for t in self.ready_task_nodes][:10])))
            debug('Parallel: ready own tasks: {}'.format(repr([t for t in self.ready_own_task_nodes])))
            debug('Parallel: running tasks: {}'.format(repr([t for t in self.running_task_nodes])))
        assert (len(self.all_task_nodes) == len(self.pending_task_nodes)
                + len(self.ready_task_nodes) + len(self.ready_own_task_nodes)
                + len(self.running_task_nodes) + len(self.done_task_nodes))

    def __exit__(self, exceptiontype: Type[BaseException] | None, exceptionval: BaseException | None,
                 exceptiontraceback: TracebackType | None):
        if exceptiontype is not None:
            critical('Parallel: exception {}: {}'.format(exceptiontype, exceptionval))
            debug('\n'.join(traceback.format_tb(exceptiontraceback)))

        if not self.shutting_down:
            self.shutdown()
        if not self.has_joined:
            self.join_all()

        names = [name for name in self.publications]
        for name in names:
            self.unpublish(name)

        if exceptiontype is None:
            if self.json_fname is not None:
                sortedw = dict(sorted(self.updated_json_weights.items(), key=lambda item: -item[1]))
                with open(self.json_fname, 'wt', encoding='utf-8') as wf:
                    # noinspection PyTypeChecker
                    json.dump(sortedw, wf, indent=2)
