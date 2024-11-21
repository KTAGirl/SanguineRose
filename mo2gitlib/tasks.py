# mini-micro <s>skirt</s>, sorry, lib for data-driven parallel processing

import pickle
import time
from enum import Enum
from multiprocessing import Process, Queue as PQueue, shared_memory

from mo2gitlib.common import *

_proc_num: int = -1  # number of child process


def this_proc_num() -> int:
    global _proc_num
    return _proc_num


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
_started: float = time.perf_counter()


def _str_time() -> str:
    return str(round(time.perf_counter() - _started, 2)) + ': '


def _str_dt(dt) -> str:
    return str(round(dt, 2))


class SharedPublication:
    shm: shared_memory.SharedMemory
    closed: bool

    def __init__(self, parallel: "Parallel", item: any):
        data = pickle.dumps(item)
        self.shm = shared_memory.SharedMemory(create=True, size=len(data))
        shared = self.shm.buf
        shared[:] = data
        name = self.shm.name
        debug('SharedPublication: ' + name)
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


def _run_task(task: Task, depparams: list[any]) -> any:
    ndep = len(depparams)
    assert ndep <= 3
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
    return out


type SharedReturnParam = tuple[str, int]


def make_shared_return_param(shared: SharedReturn) -> SharedReturnParam:
    # assert _proc_num>=0
    global _proc_num
    return shared.name(), _proc_num


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


class _Started:
    def __init__(self, proc_num: int) -> None:
        self.proc_num = proc_num


def _proc_func(parent_started: float, proc_num: int, inq: PQueue, outq: PQueue) -> None:
    try:
        global _started
        _started = parent_started
        global _proc_num
        assert _proc_num == -1
        _proc_num = proc_num
        debug('Process #' + str(proc_num + 1) + ' started')
        outq.put(_Started(_proc_num))
        while True:
            waitt0 = time.perf_counter()
            msg = inq.get()
            if msg is None:
                break  # while True

            dwait = time.perf_counter() - waitt0
            waitstr = _str_dt(dwait) + 's'

            (tasks, processedshm) = msg
            if processedshm is not None:
                assert tasks is None
                info('Process #' + str(
                    proc_num + 1) + ': after waiting for ' + waitstr + ', releasing shm=' + processedshm)
                _pool_of_shared_returns.done_with(processedshm)
                continue  # while True

            assert tasks is not None
            assert isinstance(tasks, list)
            for tplus in tasks:
                task = tplus[0]
                ndep = len(task.dependencies)
                assert len(tplus) == 1 + ndep
                t0 = time.perf_counter()
                tp0 = time.process_time()
                if waitstr is not None:
                    info(_str_time() + 'Process #' + str(
                        proc_num + 1) + ': after waiting for ' + waitstr + ', starting task ' + task.name)
                    waitstr = None
                else:
                    info(_str_time() + 'Process #' + str(
                        proc_num + 1) + ': starting task ' + task.name)
                out = _run_task(task, tplus[1:])
                elapsed = time.perf_counter() - t0
                cpu = time.process_time() - tp0
                info(
                    _str_time() + 'Process #' + str(
                        proc_num + 1) + ': done task ' + task.name + ', cpu/elapsed=' + _str_dt(
                        cpu) + '/' + _str_dt(elapsed) + 's')
                outq.put((proc_num, task.name, (cpu, elapsed), out))

    except Exception as e:
        critical('Process #' + str(proc_num + 1) + ': exception: ' + str(e))
        critical(traceback.format_exc())
        outq.put(e)
    _pool_of_shared_returns.cleanup()
    debug('Process #' + str(proc_num + 1) + ': exiting')


class _TaskGraphNodeState(Enum):
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
        for parent in self.parents:
            parent._append_leaf(self)
            if parent.state < _TaskGraphNodeState.Done:
                self.waiting_for_n_deps += 1

    def is_done(self, ready: dict[str, tuple["_TaskGraphNode", float]],
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
                if isinstance(ch.task, OwnTask):
                    ready_own[ch.task.name] = (ch, ch.total_weight())
                else:
                    ready[ch.task.name] = (ch, ch.total_weight())

    def _append_leaf(self, leaf: "_TaskGraphNode") -> None:
        self.children.append(leaf)
        self._adjust_leaf_weight(leaf.own_weight)

    def _adjust_leaf_weight(self, w: float) -> None:
        if self.max_leaf_weight < w:
            self.max_leaf_weight = w
            for p in self.parents:
                p._adjust_leaf_weight(self.own_weight + self.max_leaf_weight)

    def total_weight(self) -> float:
        return self.own_weight + self.max_leaf_weight


class Parallel:
    nprocesses: int
    json_fname: str
    json_weights: dict[str, float]
    updated_json_weights: dict[str, float]

    is_running: bool
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

    def __init__(self, jsonfname: str, nproc: int = 0) -> None:
        assert nproc >= 0
        if nproc:
            self.nprocesses = nproc
        else:
            self.nprocesses = os.cpu_count() - 1  # -1 for the master process
        assert self.nprocesses >= 0
        info('Using ' + str(self.nprocesses) + ' processes...')
        self.json_fname = jsonfname
        self.json_weights = {}
        self.updated_json_weights = {}
        if jsonfname is not None:
            try:
                with open(jsonfname, 'rt', encoding='utf-8') as rf:
                    self.json_weights = json.load(rf)
            except Exception as e:
                warn(
                    'WARNING: error loading JSON weights ' + jsonfname + ': ' + str(e) + '. Will continue w/o weights')
                self.json_weights = {}  # just in case

        self.is_running = False
        self.shutting_down = False
        self.has_joined = False

        self.publications = {}

        self.all_task_nodes = {}
        self.pending_task_nodes = {}
        self.ready_task_nodes = {}
        self.running_task_nodes = {}  # name->(procnum,started,node)
        self.done_task_nodes = {}  # name->(node,out)
        self.pending_patterns = []

    def __enter__(self) -> "Parallel":
        self.processes = []
        self.processesload = []  # we'll aim to have it at 2
        self.inqueues = []
        self.procrunningconfirmed = []  # otherwise join() on a not running yet process may hang
        self.outq = PQueue()
        for i in range(self.nprocesses):
            inq = PQueue()
            self.inqueues.append(inq)
            p = Process(target=_proc_func, args=(_started, i, inq, self.outq))
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
        assert task.name not in self.all_task_nodes
        islambda = callable(task.f) and task.f.__name__ == '<lambda>'
        if islambda:
            print('lambda in task ' + task.name)
        assert isinstance(task, OwnTask) or not islambda

        taskparents, patterns = self._dependencies_to_parents(task.dependencies)
        if taskparents is None:
            assert patterns is None
            return False
        assert patterns is not None

        w = task.w
        explicitw = True
        if w is None:
            explicitw = False
            w = 0.1 if isinstance(task,
                                  OwnTask) else 1.0  # 1 sec for non-owning tasks, and assuming that own tasks are shorter by default (they should be)
            w = self.estimated_time(task.name, w)
        node = _TaskGraphNode(task, taskparents, w, explicitw)
        self.all_task_nodes[task.name] = node
        assert node.state == _TaskGraphNodeState.Pending
        self.pending_task_nodes[task.name] = node
        for p in patterns:
            for n in self.all_task_nodes.values():
                if n.state < _TaskGraphNodeState.Done and n.task.name.startswith(p):
                    node.waiting_for_n_deps += 1
                    n.children.append(node)
            node.parents.append(p)
            self.pending_patterns.append((p, node))

        for pp in self.pending_patterns:
            (p, n) = pp
            if task.name.startswith(p):
                node.children.append(n)
                n.waiting_for_n_deps += 1

        return True

    def _internal_add_tasks(self, tasks: list[Task]) -> None:
        while len(tasks) > 0:
            megaok = False
            for t in tasks:
                ok = self._internal_add_task_if(t)
                if ok:
                    debug('Parallel: ' + t.name + ' added')
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

    def run(self, tasks: list[Task]) -> None:
        self.is_running = True
        # building task graph
        self._internal_add_tasks(tasks)

        # graph ok, running the initial tasks
        assert len(self.pending_task_nodes)
        maintstarted = time.perf_counter()
        maintwait = 0.
        maintown = 0.
        maintschedule = 0.
        owntaskstats: dict[str, tuple[int, float, float]] = {}
        while True:
            # place items in process queues, until each has 2 tasks, or until there are no tasks
            sch0 = time.perf_counter()
            while self._schedule_best_tasks():
                pass
            maintschedule += (time.perf_counter() - sch0)

            (overallstatus, towntasks) = self._run_own_tasks(
                owntaskstats)  # ATTENTION: own tasks may call add_late_task() or add_late_tasks() within
            maintown += towntasks
            if overallstatus == 3:
                break  # while True

            sch0 = time.perf_counter()
            while self._schedule_best_tasks():  # late tasks may have been added, need to check again
                pass
            maintschedule += (time.perf_counter() - sch0)

            # waiting for other processes to finish
            waitt0 = time.perf_counter()
            got = self.outq.get()
            debug('Parallel: response size:' + str(len(pickle.dumps(got))))
            if isinstance(got, Exception):
                critical('Parallel: An exception within child process reported. Shutting down')

                if not self.shutting_down:
                    self.shutdown()
                info('Parallel: shutdown ok')
                if not self.has_joined:
                    self.join_all()

                critical(
                    'Parallel: All children terminated, aborting due to an exception in a child process. For the exception itself, see log above.')
                # noinspection PyProtectedMember
                os._exit(13)  # if using sys.exit(), confusing logging will occur

            if isinstance(got, _Started):
                self.procrunningconfirmed[got.proc_num] = True
                continue  # while True

            dwait = time.perf_counter() - waitt0
            strwait = _str_dt(dwait) + 's'
            maintwait += dwait
            if dwait < 0.005:
                strwait += '[MAIN THREAD SERIALIZATION]'

            (procnum, taskname, times, out) = got
            assert taskname in self.running_task_nodes
            (expectedprocnum, started, node) = self.running_task_nodes[taskname]
            assert node.state == _TaskGraphNodeState.Running
            (cput, taskt) = times
            assert procnum == expectedprocnum
            dt = time.perf_counter() - started
            info(_str_time() + 'Parallel: after waiting for ' + strwait +
                 ', received results of task ' + taskname + ' elapsed/task/cpu='
                 + _str_dt(dt) + '/' + _str_dt(taskt) + '/' + _str_dt(cput) + 's')
            self._update_weight(taskname, taskt)
            del self.running_task_nodes[taskname]
            assert taskname not in self.done_task_nodes
            node.is_done(self.ready_task_nodes, self.ready_own_task_nodes)
            self.done_task_nodes[taskname] = (node, out)
            assert self.processesload[procnum] > 0
            self.processesload[procnum] -= 1

        maintelapsed = time.perf_counter() - maintstarted
        info(_str_time() + 'Parallel: main thread: waited+owntasks+scheduler+unaccounted=elapsed '
             + _str_dt(maintwait) + '+' + _str_dt(maintown) + '+' + _str_dt(maintschedule)
             + '+' + _str_dt(maintelapsed - maintwait - maintown - maintschedule) + '=' + _str_dt(
            maintelapsed) + 's, '
             + str(100 - round(100 * maintwait / maintelapsed, 2)) + '% load')
        info("Parallel: breakdown per task type (task name before '.'):")
        for key, val in owntaskstats.items():
            info('  ' + key + ': ' + str(val[0]) + ', took ' + _str_dt(val[1]) + '/' + _str_dt(val[2]) + 's')
        self.is_running = False

    def _schedule_best_tasks(self) -> bool:  # may schedule multiple tasks as one meta-task
        pidx = self._find_best_process()
        if pidx < 0:
            return False
        taskpluses = []
        total_time = 0.
        tasksstr = '['
        t0 = time.perf_counter()
        candidates = sorted(self.ready_task_nodes.values(), key=lambda tpl: -tpl[1])
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

        msg = (taskpluses, None)
        self.inqueues[pidx].put(msg)
        info(_str_time() + 'Parallel: assigned tasks ' + tasksstr + ' to process #' + str(pidx + 1))
        debug('Parallel: request size:' + str(len(pickle.dumps(msg))))
        self.processesload[pidx] += 1
        return True

    def _notify_sender_shm_done(self, pidx: int, name: str) -> None:
        if pidx < 0:
            assert pidx == -1
            debug(_str_time() + 'Releasing own shm=' + name)
            _pool_of_shared_returns.done_with(name)
        else:
            self.inqueues[pidx].put((None, name))

    def _run_own_tasks(self, owntaskstats: dict[str, tuple[int, float, float]]) -> tuple[int, float]:
        # returns overall status: 1: work to do, 2: all running, 3: all done
        towntasks = 0.
        while len(
                self.ready_own_task_nodes) > 0:  # new tasks might have been added by add_late_task(s), so we need to loop
            candidates = sorted(self.ready_own_task_nodes.values(), key=lambda tpl: -tpl[1])
            for c in candidates:
                ot = c[0]
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

                info(_str_time() + 'Parallel: running own task ' + ot.task.name)
                t0 = time.perf_counter()
                tp0 = time.process_time()
                # ATTENTION: ot.task.f(...) may call addLateTask() within
                out = _run_task(ot.task, params)
                elapsed = time.perf_counter() - t0
                cpu = time.process_time() - tp0
                info(_str_time() + 'Parallel: done own task ' + ot.task.name + ', cpu/elapsed=' + _str_dt(
                    cpu) + '/' + _str_dt(elapsed) + 's')
                towntasks += elapsed

                keystr = ot.task.name.split('.')[0]
                oldstat = owntaskstats.get(keystr, (0, 0., 0.))
                owntaskstats[keystr] = (oldstat[0] + 1, oldstat[1] + cpu, oldstat[2] + elapsed)

                self._update_weight(ot.task.name, elapsed)

                assert ot.state == _TaskGraphNodeState.Ready
                assert ot.task.name in self.ready_task_nodes
                del self.ready_task_nodes[ot.task.name]
                ot.is_done(self.ready_task_nodes, self.ready_own_task_nodes)
                ot.state = _TaskGraphNodeState.Done
                self.done_task_nodes[ot.task.name] = (ot, out)

        # status calculation must run after own tasks, because they may call add_late_task(s)()
        allrunningordone = True
        alldone = True
        if len(self.pending_task_nodes) > 0:
            alldone = False
            allrunningordone = False
        if len(self.running_task_nodes) > 0:
            alldone = False
        if not alldone:
            return (2, towntasks) if allrunningordone else (1, towntasks)
        return 3, towntasks

    def add_late_task(self, task: Task) -> None:  # to be called from owntask.f()
        assert self.is_running
        assert task.name not in self.all_task_nodes
        added = self._internal_add_task_if(task)
        assert added  # failure to add is ok only during original building of the tree
        # print(_printTime()+'Parallel: late task '+task.name+' added')

    def add_late_tasks(self, tasks: list[Task]) -> None:
        self._internal_add_tasks(tasks)

    def _find_best_process(self) -> int:
        besti = -1
        for i in range(len(self.processesload)):
            pl = self.processesload[i]
            if pl == 0:  # cannot be better
                return i
            if pl > 1:
                continue
            if besti < 0 or self.processesload[besti] > pl:
                besti = i
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
                debug('Parallel: task ' + task.name + ': expected=' + str(task.w) + ', real=' + str(dt))

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
                # print('Parallel: joinAll(): process #'+str(got.procnum+1)+' confirmed as started')

        info('All processes confirmed as started, waiting for joins')
        for i in range(self.nprocesses):
            self.processes[i].join()
            debug('Process #' + str(i + 1) + ' joined')
        self.has_joined = True

    def unpublish(self, name: str) -> None:
        pub = self.publications[name]
        pub.close()
        del self.publications[name]

    def __exit__(self, exceptiontype: Type[BaseException] | None, exceptionval: BaseException | None,
                 exceptiontraceback: TracebackType | None):
        if exceptiontype is not None:
            critical('Parallel: exception ' + str(exceptiontype) + ' :' + str(exceptionval))
            traceback.print_tb(exceptiontraceback)

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
