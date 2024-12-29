import heapq
import logging
import time
from enum import IntEnum
from multiprocessing import Queue as PQueue, SimpleQueue, Process, shared_memory
from threading import Thread  # only for logging!

from sanguine.install.install_logging import (add_logging_handler, set_logging_hook)
from sanguine.tasks._tasks_common import *
from sanguine.tasks._tasks_logging import (_ChildProcessLogHandler, create_logging_thread,
                                           log_waited, log_elapsed, EndOfRegularLog, StopSkipping)
from sanguine.tasks._tasks_shared import _pool_of_shared_returns, SharedReturnParam


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


def _proc_func(proc_num: int, inq: PQueue, outq: PQueue, logq) -> None:
    try:
        assert current_proc_num() == -1
        set_current_proc_num(proc_num)

        add_logging_handler(_ChildProcessLogHandler(logq))

        debug('Process started')
        outq.put(ProcessStarted(proc_num))
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
        # print('Exception!:'+traceback.format_exc())
        critical('_proc_func() internal exception: {}'.format(repr(e)))
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
    guaranteed_tags: list[str]

    def __init__(self, task: Task, parents: list["_TaskGraphNode"], weight: float, explicit_weight: bool,
                 guaranteedtags: list[str]) -> None:
        self.task = task
        self.children = []
        self.parents = parents
        self.own_weight = weight  # expected time in seconds
        self.max_leaf_weight = 0.
        self.explicit_weight = explicit_weight
        self.state = _TaskGraphNodeState.Pending
        self.waiting_for_n_deps = 0
        self.guaranteed_tags = guaranteedtags

    def mark_as_done_and_handle_children(self) -> list["_TaskGraphNode"]:
        assert self.state == _TaskGraphNodeState.Ready or self.state == _TaskGraphNodeState.Running
        self.state = _TaskGraphNodeState.Done
        out = []
        for ch in self.children:
            assert ch.state == _TaskGraphNodeState.Pending
            assert ch.waiting_for_n_deps > 0
            ch.waiting_for_n_deps -= 1
            if ch.waiting_for_n_deps == 0:
                out.append(ch)
            else:
                debug('Parallel: task {} has {} remaining dependencies to become ready'.format(
                    ch.task.name, ch.waiting_for_n_deps))

        return out

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

    # comparisons for heapq to work
    def __lt__(self, b: "_TaskGraphNode") -> bool:
        return self.total_weight() < b.total_weight()

    def __eq__(self, b: "_TaskGraphNode") -> bool:
        return self.total_weight() == b.total_weight()


class _MainLoopTimer:
    stats: dict[str, float]  # stage name->time
    started: float
    cur_stage: str
    cur_stage_start: float
    ended: float | None

    def __init__(self, stage: str):
        self.stats = {}
        self.cur_stage = stage
        self.started = self.cur_stage_start = time.perf_counter()
        self.ended = None

    def stage(self, new_stage: str) -> float:
        t = time.perf_counter()
        dt = t - self.cur_stage_start
        if self.cur_stage not in self.stats:
            self.stats[self.cur_stage] = dt
        else:
            self.stats[self.cur_stage] += dt
        self.cur_stage = new_stage
        self.cur_stage_start = t
        return dt

    def end(self) -> None:
        t = time.perf_counter()
        if self.cur_stage not in self.stats:
            self.stats[self.cur_stage] = t - self.cur_stage_start
        else:
            self.stats[self.cur_stage] += t - self.cur_stage_start
        self.ended = t

    def log_timer_stats(self) -> None:
        assert self.ended is not None
        elapsed = self.ended - self.started
        info('Parallel/main process: elapsed {:.2f}s, including:'.format(elapsed))
        total = 0.
        for name, t in sorted(self.stats.items(), key=lambda x: -x[1]):
            info('-> {}: {:.2f}s'.format(name, t))
            total += t
        if elapsed - total > 0.01:
            info('-> _unaccounted: {:.2f}s'.format(elapsed - total))

    def elapsed(self) -> float:
        assert self.ended is not None
        return self.ended - self.started


class Parallel:
    outq: PQueue
    logq: SimpleQueue
    out_logq: SimpleQueue
    processes: list[Process]
    unbusyprocesses: list[int]  # procidx of non-busy processes
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
    ready_task_nodes: dict[str, _TaskGraphNode]  # name->node
    ready_task_nodes_heap: list[_TaskGraphNode]
    ready_own_task_nodes: dict[str, _TaskGraphNode]  # name->node
    ready_own_task_nodes_heap: list[_TaskGraphNode]
    running_task_nodes: dict[str, tuple[int, float, _TaskGraphNode]]  # name->(procnum,started,node)
    done_task_nodes: dict[str, tuple[_TaskGraphNode, any]]  # name->(node,out)
    pending_patterns: list[tuple[str, _TaskGraphNode]]  # pattern, node
    dbg_serialize: bool
    old_logging_hook: Callable[[logging.LogRecord], None] | None | bool
    task_stats_srch: FastSearchOverPartialStrings
    task_stats_data: dict[str, tuple[int, float, float]]
    own_task_stats_data: dict[str, tuple[int, float, float]]
    task_stats_unaccounted: tuple[int, float, float]
    own_task_stats_unaccounted: tuple[int, float, float]
    data_dependencies: dict[str, int]
    current_task_node: _TaskGraphNode | None

    def __init__(self, jsonfname: str | None, nproc: int = 0, dbg_serialize: bool = False,
                 taskstatsofinterest: TaskStatsOfInterest = None) -> None:
        # dbg_serialize allows debugging non-own Tasks
        assert current_proc_num() == -1

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
        self.ready_task_nodes_heap = []
        self.ready_own_task_nodes = {}
        self.ready_own_task_nodes_heap = []
        self.running_task_nodes = {}  # name->(procnum,started,node)
        self.done_task_nodes = {}  # name->(node,out)
        self.pending_patterns = []

        if taskstatsofinterest is None:
            taskstatsofinterest = []
        self.task_stats_srch = FastSearchOverPartialStrings([(prefix, 1) for prefix in taskstatsofinterest])
        self.task_stats_data = {}
        self.own_task_stats_data = {}
        self.task_stats_unaccounted = (0, 0., 0.)
        self.own_task_stats_unaccounted = (0, 0., 0.)
        self.old_logging_hook = False
        self.data_dependencies = {}
        self.current_task_node = None

    def __enter__(self) -> "Parallel":
        self.old_logging_hook = set_logging_hook(lambda rec: self.logq.put((-1, time.perf_counter(), rec)))
        self.processes = []
        self.unbusyprocesses = []  # we'll aim to have it at 1; improvements to keep pressure are possible,
        # but not as keeping simplistic processesload[i] == 2 (it disbalances end of processing way too much)
        self.inqueues = []
        self.procrunningconfirmed = []  # otherwise join() on a not running yet process may hang
        self.outq = PQueue()
        self.logq = SimpleQueue()
        self.out_logq = SimpleQueue()
        self.logthread = create_logging_thread(self.logq, self.out_logq)
        self.logthread.start()
        for i in range(self.nprocesses):
            inq = PQueue()
            self.inqueues.append(inq)
            p = Process(target=_proc_func, args=(i, inq, self.outq, self.logq))
            self.processes.append(p)
            p.start()
            self.unbusyprocesses.insert(0, i)
            self.procrunningconfirmed.append(False)
        self.shutting_down = False
        self.has_joined = False
        assert len(self.unbusyprocesses) == len(self.processes)
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
        assert isinstance(task, OwnTask) or task.data_dependencies is None

        assert current_proc_num() == -1

        assert task.name not in self.all_task_nodes
        islambda = callable(task.f) and task.f.__name__ == '<lambda>'
        assert isinstance(task, OwnTask) or isinstance(task, TaskPlaceholder) or not islambda

        taskparents, patterns = self._dependencies_to_parents(task.dependencies)
        if taskparents is None:
            assert patterns is None
            return False
        assert patterns is not None
        if __debug__:
            for p in taskparents:
                assert isinstance(p, _TaskGraphNode)

        # by this point, we're sure that we'll add this particular task
        # checking data tags
        guaranteedtags = {}
        if self.current_task_node is not None:
            for gt in self.current_task_node.guaranteed_tags:
                guaranteedtags[gt] = 1
        for n in taskparents:
            for gt in n.guaranteed_tags:
                guaranteedtags[gt] = 1
        if task.data_dependencies is not None:
            for d in task.data_dependencies.required_tags:
                if d not in guaranteedtags:
                    critical('Parallel: missing datadep={} for task {}'.format(d, task.name))
                    assert False
            for nd in task.data_dependencies.required_not_tags:
                if nd in guaranteedtags:
                    critical('Parallel: prohibited datadep={} for task {}'.format(nd, task.name))
                    assert False
            for pd in task.data_dependencies.provided_tags:
                guaranteedtags[pd] = 1

        # adding task
        w = task.w
        explicitw = True
        if w is None:
            explicitw = False
            w = 0.1 if isinstance(task,
                                  OwnTask) else 1.0  # 1 sec for non-owning tasks, and assuming that own tasks are shorter by default (they should be)
            w = self.estimated_time(task.name, w)
        node = _TaskGraphNode(task, taskparents, w, explicitw, list(guaranteedtags.keys()))
        assert task.name not in self.all_task_nodes
        self.all_task_nodes[task.name] = node

        assert node.waiting_for_n_deps == 0
        if isinstance(task, TaskPlaceholder):
            node.waiting_for_n_deps = 1000000  # 1 would do, but 1000000 is much better visible in debug
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
                self.ready_own_task_nodes[task.name] = node
                heapq.heappush(self.ready_own_task_nodes_heap, node)
            else:
                self.ready_task_nodes[task.name] = node
                heapq.heappush(self.ready_task_nodes_heap, node)
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

    def _run_all_own_tasks(self) -> tuple[bool, float]:
        town = 0.
        ran = False
        assert len(self.ready_own_task_nodes) == len(self.ready_own_task_nodes_heap)
        while len(self.ready_own_task_nodes) > 0:
            towntasks = self._run_own_task()  # ATTENTION: own tasks may call add_task() or add_tasks() within
            town += towntasks
            ran = True
        return ran, town

    @staticmethod
    def _log_stats_data(items, unaccounted: tuple[int, float, float]) -> None:
        for item in sorted(items, key=lambda t: -t[1][2]):
            if item[1][0] != 0:
                info('-> {}*: {}, took {:.2f}/{:.2f}s'.format(item[0], item[1][0], item[1][1], item[1][2]))
        if unaccounted[0]:
            warn('-> _unaccounted: {}, took {:.2f}/{:.2f}s'.format(unaccounted[0], unaccounted[1], unaccounted[2]))

    def run(self, tasks: list[Task]) -> None:
        # building task graph
        self.add_tasks(tasks)

        # graph ok, running the initial tasks
        assert len(self.pending_task_nodes)
        mltimer = _MainLoopTimer('other')
        maintown = 0.
        maintexttasks = 0.

        # we need to try running own tasks before main loop - otherwise we can get stuck in an endless loop of self._schedule_best_tasks()
        mltimer.stage('own-tasks')
        _, dtown = self._run_all_own_tasks()
        maintown += dtown

        # main loop
        while True:
            # place items in process queues, until each has 2 tasks, or until there are no tasks
            mltimer.stage('scheduler')
            while True:
                ok, dt = self._schedule_best_tasks(mltimer)
                maintexttasks += dt
                if not ok:
                    break

            mltimer.stage('own-tasks')
            ran, dtown = self._run_all_own_tasks()
            maintown += dtown

            if ran:
                mltimer.stage('scheduler')
                while True:
                    ok, dt = self._schedule_best_tasks(mltimer)
                    maintexttasks += dt
                    if not ok:
                        break

            mltimer.stage('printing-stats')
            self._stats()

            mltimer.stage('other')
            done = self.is_all_done()
            if done:
                break

            # waiting for other processes to report
            mltimer.stage('waiting')
            got = self.outq.get()
            dwait = mltimer.stage('other')
            if __debug__:  # pickle.dumps is expensive by itself
                debug('Parallel: response size: {}'.format(len(pickle.dumps(got))))
            # warn(str(self.logq.qsize()))
            if isinstance(got, Exception):
                critical('Parallel: An exception within child process reported. Shutting down')

                if not self.shutting_down:
                    self.shutdown(True)
                info('Parallel: shutdown ok')
                if not self.has_joined:
                    self.join_all(True)

                critical(
                    'Parallel: All children terminated, aborting due to an exception in a child process. For the exception itself, see log above.')
                # noinspection PyProtectedMember, PyUnresolvedReferences
                os._exit(1)  # if using sys.exit(), confusing logging will occur

            if isinstance(got, ProcessStarted):
                self.procrunningconfirmed[got.proc_num] = True
                continue  # while True

            strwait = '{:.2f}s'.format(dwait)
            msgwarn = False
            if dwait < 0.005:
                strwait += '[MAIN THREAD SERIALIZATION]'
                msgwarn = True

            (procnum, tasks) = got
            assert procnum not in self.unbusyprocesses
            self.unbusyprocesses.append(procnum)

            maintexttasks += self._process_out_tasks(procnum, tasks, strwait, msgwarn)

            mltimer.stage('printing-stats')
            self._stats()

            mltimer.stage('other')
            done = self.is_all_done()
            if done:
                break

        mltimer.end()
        self.logq.put(StopSkipping())

        elapsed = mltimer.elapsed()
        nonmainpct = maintexttasks / elapsed * 100.
        info_or_perf_warn(nonmainpct < 100.,
                          'Parallel: child processes load {:.2f}s ({:.1f}% of one core, {:.1f}% of {} cores)'.format(
                              maintexttasks, nonmainpct, nonmainpct / self.nprocesses, self.nprocesses))
        info('Parallel: breakdown per child task type of interest:')
        Parallel._log_stats_data(self.task_stats_data.items(), self.task_stats_unaccounted)
        mltimer.log_timer_stats()
        waiting = mltimer.stats['waiting']
        mainpct = (elapsed - waiting) / elapsed * 100.
        info_or_perf_warn(mainpct > 50., 'Parallel: main process load {:.1f}%'.format(mainpct))

        owntasks = mltimer.stats['own-tasks']
        if owntasks - maintown > 0.01:
            pct = (owntasks - maintown) / owntasks * 100.
            info_or_perf_warn(pct > 1.,
                              'Parallel: own tasks overhead {:.2f}s ({:.1f}%)'.format(owntasks - maintown, pct))
        info('Parallel: breakdown per own task type of interest:')
        Parallel._log_stats_data(self.own_task_stats_data.items(), self.own_task_stats_unaccounted)

    def _node_is_ready(self, ch: _TaskGraphNode) -> None:
        assert ch.state == _TaskGraphNodeState.Pending
        assert ch.task.name not in self.ready_task_nodes
        assert ch.task.name not in self.ready_own_task_nodes
        assert ch.task.name in self.pending_task_nodes
        debug('Parallel: task {} is ready'.format(ch.task.name))
        ch.state = _TaskGraphNodeState.Ready
        del self.pending_task_nodes[ch.task.name]
        if isinstance(ch.task, OwnTask):
            self.ready_own_task_nodes[ch.task.name] = ch
            heapq.heappush(self.ready_own_task_nodes_heap, ch)
        else:
            self.ready_task_nodes[ch.task.name] = ch
            heapq.heappush(self.ready_task_nodes_heap, ch)

    def _process_out_tasks(self, procnum: int, tasks: list[tuple[str, tuple, any]], strwait: str | None,
                           msgwarn: bool) -> float:
        outt = 0.
        for taskname, times, out in tasks:
            assert taskname in self.running_task_nodes
            (expectedprocnum, started, node) = self.running_task_nodes[taskname]
            assert node.state == _TaskGraphNodeState.Running
            (cput, taskt) = times
            assert procnum == expectedprocnum
            dt = time.perf_counter() - started
            if strwait is not None:
                info_or_perf_warn(msgwarn,
                                  'Parallel: after waiting for {}, received results of task {} from process #{}, elapsed/task/cpu={:.2f}/{:.2f}/{:.2f}s'.format(
                                      strwait, taskname, procnum + 1, dt, taskt, cput))
            else:
                info(
                    'Parallel: received results of task {} from process #{}, elapsed/task/cpu={:.2f}/{:.2f}/{:.2f}s'.format(
                        taskname, procnum + 1, dt, taskt, cput))
            self._update_task_stats(False, taskname, cpu=cput, elapsed=taskt)
            outt += taskt

            strwait = None
            msgwarn = False
            self._update_weight(taskname, taskt)
            del self.running_task_nodes[taskname]
            assert taskname not in self.done_task_nodes
            rdy = node.mark_as_done_and_handle_children()
            for ch in rdy:
                self._node_is_ready(ch)
            self.done_task_nodes[taskname] = (node, out)

        return outt

    def _schedule_best_tasks(self, mltimer: _MainLoopTimer) -> tuple[
        bool, float]:  # may schedule multiple tasks as one meta-task
        assert len(self.ready_task_nodes) == len(self.ready_task_nodes_heap)
        if len(self.ready_task_nodes) == 0:
            return False, 0.

        pidx = self._find_best_process() if not self.dbg_serialize else 0
        if pidx < 0:
            return False, 0.
        taskpluses = []
        total_time = 0.
        tasksstr = '['
        t0 = time.perf_counter()
        i = 0
        tout = 0.
        while len(self.ready_task_nodes) > 0 and total_time < 0.1:  # heuristics: <0.1s is not worth jerking around
            assert len(self.ready_task_nodes) == len(self.ready_task_nodes_heap)
            node = heapq.heappop(self.ready_task_nodes_heap)
            assert not isinstance(node.task, OwnTask) and not isinstance(node.task, TaskPlaceholder)
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
            return False, 0.

        if self.dbg_serialize:
            ex, out = _process_nonown_tasks(taskpluses, None)
            if ex is not None:
                raise ex
            tout += self._process_out_tasks(pidx, out, None, False)
            return True, tout

        msg = (taskpluses, None)
        mltimer.stage('scheduler.queue-put')
        self.inqueues[pidx].put(msg)
        mltimer.stage('scheduler')
        # self.logq.put((-1,time.perf_counter(),make_log_record(logging.INFO, 'Parallel: assigned tasks {} to process #{}'.format(tasksstr, pidx + 1))))
        mltimer.stage('scheduler.logging')
        info('Parallel: assigned tasks {} to process #{}'.format(tasksstr, pidx + 1))
        if __debug__:  # pickle.dumps is expensive by itself
            debug('Parallel: request size: {}'.format(len(pickle.dumps(msg))))
        mltimer.stage('scheduler')
        return True, tout

    def _notify_sender_shm_done(self, pidx: int, name: str) -> None:
        if pidx < 0:
            assert pidx == -1
            debug('Parallel: Releasing own shm={}'.format(name))
            _pool_of_shared_returns.done_with(name)
        else:
            self.inqueues[pidx].put((None, name))

    @staticmethod
    def _update_task_stats_internal(some_task_stats_data, srch: tuple[str, tuple[int, float, float]], cpu,
                                    elapsed) -> None:
        (key, val) = srch
        found = some_task_stats_data.get(key)
        if found is None:
            some_task_stats_data[key] = (1, cpu, elapsed)
        else:
            some_task_stats_data[key] = (found[0] + 1, found[1] + cpu, found[2] + elapsed)

    def _update_task_stats(self, isown: bool, name: str, cpu: float, elapsed: float) -> None:
        srch = self.task_stats_srch.find_val_for_str(name)

        if isown:
            if srch is None:
                self.own_task_stats_unaccounted = (self.own_task_stats_unaccounted[0] + 1,
                                                   self.own_task_stats_unaccounted[1] + cpu,
                                                   self.own_task_stats_unaccounted[2] + elapsed)
                return
            Parallel._update_task_stats_internal(self.own_task_stats_data, srch, cpu, elapsed)
        else:
            if srch is None:
                self.task_stats_unaccounted = (self.task_stats_unaccounted[0] + 1,
                                               self.task_stats_unaccounted[1] + cpu,
                                               self.task_stats_unaccounted[2] + elapsed)
                return
            Parallel._update_task_stats_internal(self.task_stats_data, srch, cpu, elapsed)

    def _run_own_task(self) -> float:
        assert self.current_task_node is None
        assert len(self.ready_own_task_nodes) > 0
        towntask = 0.
        ot = heapq.heappop(self.ready_own_task_nodes_heap)

        assert isinstance(ot.task, OwnTask)
        # debug('own task: '+ot.task.name)
        if __debug__ and ot.task.data_dependencies is not None:
            dd = ot.task.data_dependencies
            for req in dd.required_tags:
                assert req in self.data_dependencies
            for reqnot in dd.required_not_tags:
                assert reqnot not in self.data_dependencies
            for prov in dd.provided_tags:
                self.data_dependencies[prov] = 1

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
        assert self.current_task_node is None
        self.current_task_node = ot
        (ex, out) = _run_task(ot.task, params)
        self.current_task_node = None
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

        self._update_task_stats(True, ot.task.name, cpu, elapsed)
        self._update_weight(ot.task.name, elapsed)

        assert ot.state == _TaskGraphNodeState.Ready
        assert ot.task.name in self.ready_own_task_nodes
        del self.ready_own_task_nodes[ot.task.name]
        rdy = ot.mark_as_done_and_handle_children()
        for ch in rdy:
            self._node_is_ready(ch)
        ot.state = _TaskGraphNodeState.Done
        self.done_task_nodes[ot.task.name] = (ot, out)

        return towntask

    def is_all_done(self) -> bool:
        return len(self.done_task_nodes) == len(self.all_task_nodes)

    def add_task(self, task: Task) -> None:  # to be called from owntask.f()
        assert task.name not in self.all_task_nodes
        added = self._internal_add_task_if(task)
        abort_if_not(added,
                     lambda: 'Parallel: cannot add task {}, are you sure all dependencies are known?'.format(task.name))

    def replace_task_placeholder(self, task: Task) -> None:
        assert task.name in self.all_task_nodes
        assert task.name in self.pending_task_nodes
        oldtasknode = self.pending_task_nodes[task.name]
        assert oldtasknode.state == _TaskGraphNodeState.Pending
        assert isinstance(oldtasknode.task, TaskPlaceholder)
        children = self.pending_task_nodes[task.name].children
        del self.pending_task_nodes[task.name]
        del self.all_task_nodes[task.name]
        self.add_task(task)
        assert task.name in self.pending_task_nodes
        assert len(self.pending_task_nodes[task.name].children) == 0
        self.pending_task_nodes[task.name].children = children
        debug('Parallel: replaced task placeholder {}, inherited {} children'.format(task.name, len(children)))

    def _find_best_process(self) -> int:
        if len(self.unbusyprocesses) == 0:
            return -1
        return self.unbusyprocesses.pop()

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

    def shutdown(self, force: bool) -> None:
        assert not self.shutting_down

        if force:
            for i in range(self.nprocesses):
                self.processes[i].kill()
        else:
            for i in range(self.nprocesses):
                self.inqueues[i].put(None)
        # self.logq.put(None) - moved to join_all() to prevent processes hanging because of unread log messages
        # print('Parallel: shutting down')
        self.logq.put(EndOfRegularLog())
        self.shutting_down = True

    def join_all(self, force: bool) -> None:
        assert self.shutting_down
        assert not self.has_joined

        # read late log messages from logq; if we don't read them, processes may not terminate
        # while True:
        #   try:
        #        record = self.logq.get(False)
        #        (procnum, t, rec) = record
        #        assert isinstance(rec, logging.LogRecord)
        #        _patch_log_rec(rec, procnum, t)
        #        log_record(rec)
        #    except QueueEmpty:
        #        break

        # for i in range(len(self.inqueues)):
        #    j = 0
        #    while not self.inqueues[i].empty():
        #        self.inqueues[i].get()
        #        j += 1
        #    if j != 0:
        #        alert('{} unread messages from process #{}, skipped'.format(j,i+1))
        #

        if not force:
            n = 0
            while not all(self.procrunningconfirmed):
                if n == 0:
                    info(
                        'Parallel: joinAll(): waiting for all processes to confirm start before joining to avoid not started yet join race')
                    n = 1
                got = self.outq.get()
                if isinstance(got, ProcessStarted):
                    self.procrunningconfirmed[got.proc_num] = True
                    # debug('Parallel: joinAll(): process #{} confirmed as started',got.procnum+1)

        teol0 = time.perf_counter()
        endoflog = self.out_logq.get()
        assert endoflog is None
        dteol = time.perf_counter() - teol0
        if self.old_logging_hook is not False:
            set_logging_hook(self.old_logging_hook)
            self.old_logging_hook = False
            # debug() should go after set_logging_hook()
            info_or_perf_warn(dteol > 0.05,
                              'Parallel: after waiting for {:.2f}s for log thread to process its queue, setting logging hook back to {}'.format(
                                  dteol, repr(self.old_logging_hook)))
        else:
            info_or_perf_warn(dteol > 0.05,
                              'Parallel: took {:.2f}s to wait for log thread to process its queue'.format(dteol))
        # print('synced with log thread')

        info('All processes confirmed as started, waiting for joins')
        for i in range(self.nprocesses):
            self.processes[i].join()
            debug('Process #{} joined'.format(i + 1))

        self.logq.put(None)  # moved here to prevent processes hanging because of unread log messages
        self.logthread.join()
        self.has_joined = True

    def unpublish(self, name: str) -> None:
        pub = self.publications[name]
        pub.close()
        del self.publications[name]

    def _stats(self) -> None:
        assert len(self.ready_task_nodes) == len(self.ready_task_nodes_heap)
        info('Parallel: {} tasks, including {} pending, {}/{} ready, {} running, {} done'.format(
            len(self.all_task_nodes), len(self.pending_task_nodes), len(self.ready_task_nodes),
            len(self.ready_own_task_nodes), len(self.running_task_nodes), len(self.done_task_nodes))
        )
        if __debug__:
            debug(
                'Parallel: pending tasks (up to 10 first): {}'.format(repr([t for t in self.pending_task_nodes][:10])))
            debug('Parallel: ready tasks (up to 10 first): {}'.format(repr([t for t in self.ready_task_nodes][:10])))
            debug('Parallel: ready own tasks: {}'.format(repr([t for t in self.ready_own_task_nodes])))
            debug(
                'Parallel: running tasks (up to 10 first): {}'.format(repr([t for t in self.running_task_nodes][:10])))
        assert (len(self.all_task_nodes) == len(self.pending_task_nodes)
                + len(self.ready_task_nodes) + len(self.ready_own_task_nodes)
                + len(self.running_task_nodes) + len(self.done_task_nodes))

    def __exit__(self, exceptiontype: Type[BaseException] | None, exceptionval: BaseException | None,
                 exceptiontraceback: TracebackType | None):
        force = False
        if exceptiontype is not None:
            critical('Parallel: exception {}: {}'.format(str(exceptiontype), repr(exceptionval)))
            alert('\n'.join(traceback.format_tb(exceptiontraceback)))
            force = True

        if not self.shutting_down:
            self.shutdown(force)
        if not self.has_joined:
            self.join_all(force)

        if log_elapsed() is not None:
            logpct = (log_elapsed() - log_waited()) / log_elapsed() * 100.
            info_or_perf_warn(logpct > 50., 'Parallel: logging thread load {:.1f}%'.format(logpct))
        else:
            warn('Parallel: logging thread did not finish properly?')

        names = [name for name in self.publications]
        for name in names:
            self.unpublish(name)

        if exceptiontype is None:
            if self.json_fname is not None:
                sortedw = dict(sorted(self.updated_json_weights.items(), key=lambda item: -item[1]))
                with open(self.json_fname, 'wt', encoding='utf-8') as wf:
                    # noinspection PyTypeChecker
                    json.dump(sortedw, wf, indent=2)
