from multiprocessing import shared_memory

from sanguine.common import *

if typing.TYPE_CHECKING:
    from sanguine.tasks import Parallel, current_proc_num


### SharedReturn

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

type SharedReturnParam = tuple[str, int]


def make_shared_return_param(shared: SharedReturn) -> SharedReturnParam:
    # assert _proc_num>=0
    return shared.name(), current_proc_num()


### SharedPublication

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
