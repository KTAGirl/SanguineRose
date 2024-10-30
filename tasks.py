# mini-micro lib for data-driven parallel processing

import os
import time
import json
import traceback
import pickle
from multiprocessing import Process, Queue as PQueue, shared_memory
#from multiprocessing.managers import SharedMemoryManager

class _PoolOfShared:
    def __init__(self):
        self.shareds = {}
        
    def register(self,shared):
        self.shareds[shared.name()] = shared
        
    def doneWith(self,name):
        shared = self.shareds[name]
        shared.close()
        del self.shareds[name]
        
    def __del__(self):
        for name in self.shareds:
            shared = self.shareds[name]
            shared.close()

_poolofshared = _PoolOfShared()

class SharedForSender:
    def __init__(self,item):
        data = pickle.dumps(item)
        self.shm = shared_memory.SharedMemory(create=True,size=len(data))
        shared = self.shm.buf
        shared[:]=data
        _poolofshared.register(self)
                    
    def name(self):
        return self.shm.name
        
    def close(self):
        self.shm.close()
                        
#from mo2git.debug import *

class Task:
    def __init__(self,name,f,param,dependencies):
        self.name = name
        self.f = f
        self.param = param
        self.dependencies = dependencies
        
def _runTask(task,depparams):
    ndep = len(depparams)
    assert(ndep<=3)
    match ndep:
        case 0:
            out = task.f(task.param)
        case 1:
            out = task.f(task.param,depparams[0])
        case 2:
            out = task.f(task.param,depparams[0],depparams[1])
        case 3:
            out = task.f(task.param,depparams[0],depparams[1],depparams[2]) 
    return out
    
_procnum = -1 # number of child process
def makeSharedParam(shared):
    assert(_procnum>=0)
    return (shared.name(),_procnum)

def receivedShared(parallel,sharedparam):
    (name,sender) = sharedparam
    shm = shared_memory.SharedMemory(name)
    out = pickle.loads(shm.buf)
    parallel._notifySenderShmDone(sender,name)
    return out

def _procFunc(num,inq,outq):
    global _procnum
    assert(_procnum==-1)
    _procnum = num
    #print('Process #'+str(num+1)+' started')
    while True:
        taskplus = inq.get()
        if taskplus is None:
            #print('Process #'+str(num+1)+': exiting')
            return
        task = taskplus[0]
        processedshm = taskplus[1]
        assert(task is None or processedshm is None)
        assert(task is not None or processedshm is not None)
        if processedshm is not None:
            assert(task is None)
            print('Process #'+str(num+1)+': releasing shm='+processedshm)
            _poolofshared.doneWith(processedshm)
            continue #while True
            
        ndep = len(task.dependencies)
        assert(len(taskplus)==2+ndep)
        t0 = time.perf_counter()
        tp0 = time.process_time()
        print('Process #'+str(num+1)+': starting task '+task.name)
        out = _runTask(task,taskplus[2:])
        elapsed = time.perf_counter() - t0
        cpu = time.process_time() - tp0
        print('Process #'+str(num+1)+': done task '+task.name+', cpu/elapsed='+str(round(cpu,2))+'/'+str(round(elapsed,2))+'s')
        outq.put((num,task.name,(cpu,elapsed),out))

class _TaskGraphNode:
    def __init__(self,task,parents,weight):
        self.task = task
        self.children=[]
        self.parents = parents
        self.ownweight = weight # expected time in seconds
        self.maxleafweight = 0
        for parent in self.parents:
            parent._appendLeaf(self) 
            
    def _appendLeaf(self,leaf):
        self.children.append(leaf)
        self._adjustLeafWeight(leaf.ownweight)
            
    def _adjustLeafWeight(self,w):
        if self.maxleafweight < w:
            self.maxleafweight = w
            for p in self.parents:
                p._adjustLeafWeight(self.ownweight+self.maxleafweight)
        
    def totalWeight(self):
        return self.ownweight + self.maxleafweight
            
class Parallel:
    def __init__(self,jsonfname,NPROC=0):
        assert(NPROC>=0)
        #self.smm = SharedMemoryManager()
        if NPROC:
            self.NPROC = NPROC
        else:
            self.NPROC = os.cpu_count() - 1 # -1 for the process which will run self.run()
        assert(self.NPROC>=0)
        print('Using '+str(self.NPROC)+' processes...')
        self.jsonfname = jsonfname
        self.jsonweights = {}
        if jsonfname is not None:
            try:
                with open(jsonfname, 'rt',encoding='utf-8') as rf:
                    self.jsonweights = json.load(rf)
            except Exception as e:
                print('WARNING: error loading JSON weights '+jsonfname+': '+str(e)+'. Will continue w/o weights')
                self.jsonweights = {} # just in case                        
        self.isrunning = False

    def __enter__(self):
        #self.smm.start()
        self.processes = []
        self.processesload = [] # we'll aim to have it at 2
        self.inqueues = []
        self.outq = PQueue()
        for i in range(0,self.NPROC):
            inq = PQueue()
            self.inqueues.append(inq)
            p = Process(target=_procFunc,args=(i,inq,self.outq))
            self.processes.append(p)
            p.start()
            self.processesload.append(0)
        self.shuttingdown = False
        self.joined = False
        assert(len(self.processesload)==len(self.processes))
        assert(len(self.inqueues)==len(self.processes))
        return self
        
    def _internalAddTaskIf(self,t):
        assert(t.name not in self.alltasknames)

        taskparents = []
        for d in t.dependencies:
            pnode = graphnodesbyname.get(d)
            if pnode is None:
                return False
            else:
                taskparents.append(pnode)

        node = _TaskGraphNode(t,taskparents,self.jsonweights.get(t.name,1.)) # 1 sec for non-owning tasks
        self.alltasknames[t.name] = 1
        self.alltasknodes.append(node)
        self.graphnodesbyname[t.name]=node
        if len(taskparents) == 0:
            self.taskgraph.append(node)
        return True

    def _internalAddOwnTask(self,ot):
        #print(task.name)
        #assert(ot.param is None) # for owntasks
        assert(ot.name not in self.graphnodesbyname)
        assert(ot.name not in self.ownnodesbyname)
        taskparents = []
        for d in ot.dependencies:
            pnode = self.graphnodesbyname.get(d)
            if pnode is None:
                pnode = self.ownnodesbyname.get(d)
            assert(pnode is not None)
            taskparents.append(pnode)
        node = _TaskGraphNode(ot,taskparents,self.jsonweights.get(ot.name,0.1)) # assuming that own tasks are shorter (they should be)
        self.owntasks.append(node) 
        self.ownnodesbyname[ot.name] = node        

    def run(self,tasks,owntasks):
        self.isrunning = True
        self.alltasknames = {}
        # building task graph
        
        self.taskgraph = [] #it is a forest
        self.graphnodesbyname = {}
        self.alltasknodes = []
        while len(tasks) > 0:
            okone = None
            for t in tasks:
                ok = self._internalAddTaskIf(t)
                if ok:
                    okone = t
                    break #for t
            
            if okone is not None:
                tasks.remove(okone)
                continue # while True
            else:
                print('Parallel: probable typo in task name or circular dependency: cannot resolve tasks '+str(tasks))
                assert(False)
            
        self.owntasks = []
        self.ownnodesbyname = {} # name->node
        self.doneowntasks = {} # name->(node,out)
        for ot in owntasks:
            self._internalAddOwnTask(ot)
                
        # graph ok, running the initial tasks
        assert(len(self.taskgraph))
        self.runningtasks = {} # name->(procnum,started,node)
        self.donetasks = {} # name->(node,out)        
        while True:
            # place items in process queues, until each has 2 tasks, or until there are no tasks
            while self._scheduleBestTask():
                pass

            overallstatus = self._runOwnTasks() #ATTENTION: own tasks may call addLateTask() within
            if overallstatus == 3:
                break # while True

            # waiting for other processes to finish
            (procnum,taskname,times,out) = self.outq.get()
            assert(taskname in self.runningtasks)
            (expectedprocnum,started,node) = self.runningtasks[taskname]
            (cput,taskt) = times
            assert(procnum==expectedprocnum)
            dt = time.perf_counter() - started
            print('Parallel: received results of task '+taskname+' elapsed/task/cpu='
                  +str(round(dt,2))+'/'+str(round(taskt,2))+'/'+str(round(cput,2))+'s')
            self._updateWeight(taskname,taskt)
            del self.runningtasks[taskname]
            assert(taskname not in self.donetasks)
            self.donetasks[taskname] = (node,out)
            assert(self.processesload[procnum] > 0)
            self.processesload[procnum] -= 1
            
        self.isrunning = False 

    def _scheduleBestTask(self):
        node = self._findBestCandidate()
        if node is not None:
            pidx = self._findBestProcess()
            if pidx >= 0:
                taskplus = [node.task,None]
                assert(len(node.task.dependencies)==len(node.parents))
                for parent in node.parents:
                    assert(parent.task.name in self.donetasks)
                    donetask = self._doneTask(parent.task.name)
                    assert(donetask[0]==parent)
                    taskplus.append(donetask[1])
                assert(len(taskplus)==2+len(node.task.dependencies))
                self.inqueues[pidx].put(taskplus)
                print('Parallel: assigned task '+node.task.name+' to process #'+str(pidx))
                self.runningtasks[node.task.name] = (pidx,time.perf_counter(),node)
                self.processesload[pidx] += 1
                return True
        return False
        
    def _notifySenderShmDone(self,pidx,name):
        self.inqueues[pidx].put( (None,name) )
        
    def _doneTask(self,name):
        done = self.donetasks.get(name)
        if done is None:
            done = self.doneowntasks.get(name)
        else:
            assert(name not in self.doneowntasks)
        return done
        
    def _runOwnTasks(self): # returns overall status: 1: work to do, 2: all running, 3: all done
        #print(len(self.owntasks))
        for ot in self.owntasks:
            #print('task: '+ot.task.name)
            if ot.task.name in self.doneowntasks:
                continue
            parentsok = True
            params = []
            assert(len(ot.parents)==len(ot.task.dependencies))
            for p in ot.parents:
                #print('parent: '+p.task.name)
                done = self._doneTask(p.task.name)
                if done is None:
                    parentsok = False
                    break
                params.append(done[1])
            if not parentsok:
                continue # for ot

            assert(len(params)==len(ot.task.dependencies))
            assert(len(params)<=3)

            print('Parallel: running own task '+ot.task.name)
            started = time.perf_counter()
            #ATTENTION: ot.task.f(...) may call addLateTask() within
            out = _runTask(ot.task,params)
            print('Parallel: done own task '+ot.task.name)
            dt = time.perf_counter() - started
            self._updateWeight(ot.task.name,dt)
            self.doneowntasks[ot.task.name] = (ot,out)
        
        # status must run after own tasks, because they may call addLateTask() and addLateOwnTask()
        allrunningordone = True
        alldone = True
        for node in self.alltasknodes:
            if node.task.name not in self.donetasks:
                alldone = False
                if node.task.name not in self.runningtasks:
                    allrunningordone = False
                    break
        if not alldone:
            return 2 if allrunningordone else 1
        return 3
        
    def addLateTask(self,task): #to be called from owntask.f()
        assert(self.isrunning)
        assert(task.name not in self.alltasknames)
        assert(task.name not in self.ownnodesbyname)
        added = self._internalAddTask(t)
        assert(added) #failure to add is ok only during original building of the tree
        print('Parallel: late task '+task.name+' added')
    
    def addLateOwnTask(self,ot):
        assert(self.isrunning)
        assert(task.name not in self.alltasknames)
        assert(task.name not in self.ownnodesbyname)
        self._internalAddOwnTask(self,ot)
        print('Parallel: late own task '+task.name+' added')
    
    def _findBestProcess(self):
        besti = -1
        for i in range(0,len(self.processesload)):
            pl = self.processesload[i]
            if pl == 0: #cannot be better
                return i
            if besti < 0 or self.processesload[besti] > pl:
                besti = i
        return besti

    def _findBestCandidate(self):
        bestcandidate = None
        for node in self.alltasknodes:
            if bestcandidate is not None and bestcandidate.totalWeight() > node.totalWeight():
                continue
            if node.task.name in self.runningtasks or node.task.name in self.donetasks:
                continue
            parentsok = True
            for p in node.parents:
                done = self._doneTask(p.task.name)
                if done is None:
                    parentsok = False
                    break
            if not parentsok:
                continue
            bestcandidate = node
        return bestcandidate
 
    def _updateWeight(self,taskname,dt):
        oldw = self.jsonweights.get(taskname)
        if oldw is None:
            self.jsonweights[taskname] = dt
        else:
            self.jsonweights[taskname] = (self.jsonweights[taskname] + dt) / 2 # heuristics to get some balance between new value and history
 
    def _dbgNone(node):
        print(node.__dict__)
        
    def shutdown(self):
        assert(not self.shuttingdown)
        for i in range(0,self.NPROC):
            self.inqueues[i].put(None)
        self.shuttingdown = True
        
    def joinAll(self):
        assert(self.shuttingdown)
        assert(not self.joined)
        for i in range(0,self.NPROC):
            self.processes[i].join()
        self.joined = True        
        
    def __exit__(self,exceptiontype,exceptionval,exceptiontraceback):
        if exceptiontype is not None:
            print('Parallel: exception '+str(exceptiontype)+' :'+str(exceptionval))
            traceback.print_tb(exceptiontraceback)
        #dbgWait()
        if not self.shuttingdown:
            self.shutdown()
        if not self.joined:
            self.joinAll()
            
        #self.smm.shutdown()
            
        if exceptiontype is None:
            if self.jsonfname is not None:
                with open(self.jsonfname, 'wt',encoding='utf-8') as wf:
                    json.dump(self.jsonweights,wf,indent=2)
            