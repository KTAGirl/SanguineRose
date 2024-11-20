# mini-micro <s>skirt</s>, sorry, lib for data-driven parallel processing

import pickle
import time
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
            taskplus = inq.get()
            dwait = time.perf_counter() - waitt0
            # print(dwait)
            waitstr = _str_dt(dwait) + 's'

            if taskplus is None:
                break  # while True
            task = taskplus[0]
            processedshm = taskplus[1]
            assert task is None or processedshm is None
            assert task is not None or processedshm is not None
            if processedshm is not None:
                assert task is None
                info('Process #' + str(
                    proc_num + 1) + ': after waiting for ' + waitstr + ', releasing shm=' + processedshm)
                _pool_of_shared_returns.done_with(processedshm)
                continue  # while True

            ndep = len(task.dependencies)
            assert len(taskplus) == 2 + ndep
            t0 = time.perf_counter()
            tp0 = time.process_time()
            info(_str_time() + 'Process #' + str(
                proc_num + 1) + ': after waiting for ' + waitstr + ', starting task ' + task.name)
            out = _run_task(task, taskplus[2:])
            elapsed = time.perf_counter() - t0
            cpu = time.process_time() - tp0
            info(
                _str_time() + 'Process #' + str(proc_num + 1) + ': done task ' + task.name + ', cpu/elapsed=' + _str_dt(
                    cpu) + '/' + _str_dt(elapsed) + 's')
            outq.put((proc_num, task.name, (cpu, elapsed), out))
    except Exception as e:
        critical('Process #' + str(proc_num + 1) + ': exception: ' + str(e))
        critical(traceback.format_exc())
        outq.put(e)
    _pool_of_shared_returns.cleanup()
    debug('Process #' + str(proc_num + 1) + ': exiting')


class _TaskGraphNode:
    task: Task
    children: list["_TaskGraphNode"]
    parents: list["_TaskGraphNode"]
    own_weight: float
    max_leaf_weight: float
    explicit_weight: bool

    def __init__(self, task: Task, parents: list["_TaskGraphNode"], weight: float, explicit_weight: bool) -> None:
        self.task = task
        self.children = []
        self.parents = parents
        self.own_weight = weight  # expected time in seconds
        self.max_leaf_weight = 0.
        self.explicit_weight = explicit_weight
        for parent in self.parents:
            parent._append_leaf(self)

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


class _TaskGraphPatternNode:
    pattern: str

    def __init__(self, pattern: str) -> None:
        self.pattern = pattern

    def _adjust_leaf_weight(self, w: float) -> None:
        pass


class Parallel:
    nprocesses: int
    json_fname: str
    json_weights: dict[str, float]
    updated_json_weights: dict[str, float]

    is_running: bool
    shutting_down: bool
    has_joined: bool

    publications: dict[str, shared_memory.SharedMemory]
    # task_graph: list[_TaskGraphNode]  # graph is a forest
    all_task_nodes: dict[str, _TaskGraphNode]  # name->node
    pending_task_nodes: dict[str, _TaskGraphNode]  # name->node
    # own_nodes: dict[str, _TaskGraphNode]  # name->node

    running_task_nodes: dict[str, tuple[int, float, _TaskGraphNode]]  # name->(procnum,started,node)
    done_task_nodes: dict[str, tuple[_TaskGraphNode, any]]  # name->(node,out)

    # done_own_tasks: dict[str, tuple[_TaskGraphNode, any]]  # name->(node,out)

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
        # self.task_graph = []

        self.all_task_nodes = {}
        self.pending_task_nodes = {}
        # self.own_nodes = {}
        self.running_task_nodes = {}  # name->(procnum,started,node)
        self.done_task_nodes = {}  # name->(node,out)
        # self.done_own_tasks = {}  # name->(node,out)

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

    def _dependencies_to_parents(self, dependencies: list[str]) -> list[_TaskGraphNode] | None:
        taskparents = []
        for d in dependencies:
            if d.endswith('*'):
                pnode = _TaskGraphPatternNode(d)
                taskparents.append(pnode)
                continue
            pnode = self.all_task_nodes.get(d)
            if pnode is None:
                # print(d)
                return None
            else:
                taskparents.append(pnode)
        return taskparents

    def _internal_add_task_if(self, t: Task) -> bool:
        assert t.name not in self.all_task_nodes
        islambda = callable(t.f) and t.f.__name__ == '<lambda>'
        if islambda:
            print('lambda in task '+t.name)
        assert isinstance(t,OwnTask) or not islambda

        taskparents = self._dependencies_to_parents(t.dependencies)
        if taskparents is None:
            return False

        w = t.w
        explicitw = True
        if w is None:
            explicitw = False
            w = 0.1 if isinstance(t,
                                  OwnTask) else 1.0  # 1 sec for non-owning tasks, and assuming that own tasks are shorter by default (they should be)
            w = self.estimated_time(t.name, w)
        node = _TaskGraphNode(t, taskparents, w, explicitw)
        self.all_task_nodes[t.name] = node
        self.pending_task_nodes[t.name] = node
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
            while self._schedule_best_task():
                pass
            maintschedule += (time.perf_counter() - sch0)

            (overallstatus, towntasks) = self._run_own_tasks(
                owntaskstats)  # ATTENTION: own tasks may call add_late_task() or add_late_tasks() within
            maintown += towntasks
            if overallstatus == 3:
                break  # while True

            sch0 = time.perf_counter()
            while self._schedule_best_task():  # late tasks may have been added, need to check again
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
            (cput, taskt) = times
            assert procnum == expectedprocnum
            dt = time.perf_counter() - started
            info(_str_time() + 'Parallel: after waiting for ' + strwait +
                 ', received results of task ' + taskname + ' elapsed/task/cpu='
                 + _str_dt(dt) + '/' + _str_dt(taskt) + '/' + _str_dt(cput) + 's')
            self._update_weight(taskname, taskt)
            del self.running_task_nodes[taskname]
            assert taskname not in self.done_task_nodes
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

    def _schedule_best_task(self) -> bool:
        node = self._find_best_candidate()
        if node is not None:
            pidx = self._find_best_process()
            if pidx >= 0:
                taskplus = [node.task, None]
                assert len(node.task.dependencies) == len(node.parents)
                for parent in node.parents:
                    # print(parent.task.name)
                    # assert parent.task.name in self.donetasks
                    donetask = self._done_parent(parent)
                    assert donetask is not None
                    if donetask is not True:
                        assert isinstance(donetask, Task)
                        taskplus.append(donetask)
                assert len(taskplus) == 2 + len(node.task.dependencies)

                assert node.task.name in self.pending_task_nodes
                del self.pending_task_nodes[node.task.name]

                self.inqueues[pidx].put(taskplus)
                info(_str_time() + 'Parallel: assigned task ' + node.task.name + ' to process #' + str(pidx + 1))
                debug('Parallel: request size:' + str(len(pickle.dumps(taskplus))))
                self.running_task_nodes[node.task.name] = (pidx, time.perf_counter(), node)
                self.processesload[pidx] += 1
                return True
        return False

    def _notify_sender_shm_done(self, pidx: int, name: str) -> None:
        if pidx < 0:
            assert pidx == -1
            debug(_str_time() + 'Releasing own shm=' + name)
            _pool_of_shared_returns.done_with(name)
        else:
            self.inqueues[pidx].put((None, name))

    def _done_parent(self, parent: _TaskGraphNode | _TaskGraphPatternNode) -> _TaskGraphNode | None | True:
        if isinstance(parent, _TaskGraphNode):
            done = self.done_task_nodes.get(parent.task.name)
            return done
        else:
            assert isinstance(parent, _TaskGraphPatternNode)
            assert parent.pattern.endswith('*')
            prefix = parent.pattern[:-1]
            for name, node in self.pending_task_nodes.items():
                assert name == node.task.name
                if name.startswith(prefix):
                    return None
            return True

    def _run_own_tasks(self, owntaskstats: dict[str, tuple[int, float, float]]) -> tuple[int, float]:
        # returns overall status: 1: work to do, 2: all running, 3: all done
        towntasks = 0.
        for ot in self.pending_task_nodes.values():
            # print('task: '+ot.task.name)
            if not isinstance(ot.task, OwnTask):
                continue
            parentsok = True
            params = []
            assert len(ot.parents) == len(ot.task.dependencies)
            for p in ot.parents:
                # print('parent: '+p.task.name)
                done = self._done_parent(p)
                if done is None:
                    parentsok = False
                    break
                if done is not True:
                    params.append(done)
            if not parentsok:
                continue  # for ot

            assert len(params) == len(ot.task.dependencies)
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

            assert ot.task.name in self.pending_task_nodes
            del self.pending_task_nodes[ot.task.name]
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

    def _find_best_candidate(self) -> _TaskGraphNode:
        bestcandidate = None
        for node in self.pending_task_nodes.values():
            if bestcandidate is not None and bestcandidate.total_weight() > node.total_weight():
                continue
            parentsok = True
            for p in node.parents:
                done = self._done_parent(p)
                if done is None:
                    parentsok = False
                    break
            if not parentsok:
                continue
            bestcandidate = node
        return bestcandidate

    def _update_weight(self, taskname: str, dt: float) -> None:
        task = self.all_task_nodes[taskname].task
        if task.w is not None:  # no sense in saving tasks with explicitly specified weights
            oldw = self.json_weights.get(taskname)
            if oldw is None:
                self.updated_json_weights[taskname] = dt
            else:
                self.updated_json_weights[taskname] = (
                                                              oldw + dt) / 2  # heuristics to get some balance between new value and history

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
