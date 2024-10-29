# mini-micro lib for data-driven parallel processing

import os
import time
import json
from multiprocessing import Process, Queue as PQueue

class Task:
    def __init__(self,name,f,param,dependencies):
        self.name = name
        self.f = f
        self.param = param
        self.dependencies = dependencies
        
def _procFunc(num,inq,outq):
    print('Process #'+str(num)+' started')
    while True:
        taskplus = inq.get()
        if taskplus is None:
            print('Process #'+str(num)+': exiting')
            return
        task = taskplus[0]
        ndep = len(task.dependencies)
        assert(len(taskplus)==1+ndep)
        print('Process #'+str(num)+': starting task '+task.name)
        assert(ndep<=3)
        match ndep:
            case 0:
                out = task.f(task.param)
            case 1:
                out = task.f(task.param,taskplus[1])
            case 2:
                out = task.f(task.param,taskplus[1],taskplus[2])
            case 3:
                out = task.f(task.param,taskplus[1],taskplus[2],taskplus[3])
        print('Process #'+str(num)+': done task '+task.name)
        outq.put((num,task.name,out))

class _TaskGraphNode:
    def __init__(self,task,parents,weight):
        self.task = task
        self.children=[]
        self.parents = parents
        self.ownweight = weight # expected time in seconds
        self.maxleafweight = 0
        for parent in self.parents:
            parent.appendLeaf(self) 
            
    def _appendLeaf(self,leaf):
        children.append(leaf)
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
        if NPROC:
            self.NPROC = NPROC
        else:
            self.NPROC = os.cpu_count() - 1 # -1 for the process which will run self.run()
        assert(self.NPROC>=0)
        print('Using '+str(NPROC)+' processes...')
        self.jsonfname = jsonfname
        self.jsonweights = {}
        if jsonfname is non None:
            try:
                with open(jsonfname, 'rt',encoding='utf-8') as rf:
                    self.jsonweights = json.load(rf)
            except Exception as e:
                print('WARNING: error loading JSON weights '+jsonfname+': '+str(e)+'. Will continue w/o weights')
                self.jsonweights = {} # just in case                        
        self.isrunning = False

    def __enter__(self):
        self.processes = []
        self.processesload = [] # we'll aim to have it at 2
        self.inqueues = []
        self.outq = PQueue()
        for i in range(0,self.NPROC):
            inq = PQueue()
            self.inqueues.append(inq)
            p = Process(target=_procFunc,args=(i,inq,outq))
            self.processes.append(p)
            p.start()
            self.processesload.append(0)
        self.shuttingdown = False
        self.joined = False
        assert(len(processesload)==len(processes))
        assert(len(inqueues)==len(processes))
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
        assert(task.param is None) # for owntasks
        assert(task.name not in self.graphnodesbyname)
        assert(task.name not in self.ownnodesbyname)
        taskparents = []
        for d in ot.dependencies:
            assert(d in self.graphnodesbyname)
            pnode = self.graphnodesbyname[d]
            taskparents.append(pnode)
        node = _TaskGraphNode(ot,taskparents,self.jsonweights.get(ot.name,0.1)) # assuming that own tasks are shorter (they should be)
        self.owntasks.append(node) 
        self.ownnodesbyname[ot.name] = node        

    def run(self,tasks,owntasks):
        self.isrunning = True
        self.alltasknames = {}
        # building task graph
        
        self.taskgraph = None
        self.graphnodesbyname = {}
        self.alltasknodes = []
        while True:
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
        self.doneowntasks = {}
        for ot in self.owntasks:
            self._internalAddOwnTask(ot)
                
        # graph ok, running the 
        assert(len(taskgraph))
        self.runningtasks = {} # name->(procnum,started,node)
        self.donetasks = {} # name->(node,out)        
        while True:
            # place items in process queues, until each has 2 tasks, or until there are no tasks
            while self._runBestTask():
                pass

            overallstatus = self._runOwnTasks() #ATTENTION: own tasks may call addLateTask() within
            if overallstatus == 3:
                break # while True

            # waiting for other processes to finish
            (procnum,taskname,out) = self.outq.get()
            assert(taskname in self.runningtasks)
            (expectedprocnum,started,node) = self.runningtasks[taskname]
            assert(procnum==expectedprocnum)
            dt = time.perf_counter() - started
            self._updateWeight(taskname,dt)
            del self.runningtasks[taskname]
            assert(taskname not in self.donetasks)
            self.donetasks[taskname] = (node,out)
            self.processesload[procnum] -= 1
            
        self.isrunning = False 

    def _runBestTask(self):
        node = self._findBestCandidate()
        if node is not None:
            pidx = self.findBestProcess()
            if pidx >= 0:
                taskplus = [node.task]
                assert(len(node.task.dependencies)==len(node.parents))
                for parent in node.parents:
                    assert(parent.task.name in self.donetasks)
                    donetask = self.donetasks[parent.task.name]
                    assert(donetask[0]==parent)
                    taskplus.append(donetask[1])
                assert(len(taskplus)==1+len(node.task.dependencies))
                self.inqueues[i].put(taskplus)
                print('Parallel: added task '+node.task.name+' to process #'+str(i))
                self.runningtasks[node.task.name] = (i,time.perf_counter(),node)
                return True
        return False
        
    def _runOwnTasks(self): # returns overall status: 1: work to do, 2: all running, 3: all done
        for ot in self.owntasks:
            if ot.task.name in self.doneowntasks:
                continue
            parentsok = True
            params = []
            assert(len(ot.parents)==len(ot.task.dependencies))
            for p in ot.parents:
                if p.task.name not in self.donetasks:
                    parentsok = False
                    break
                done = self.donetasks[p.task.name]
                params.append(done[1])
            if not parentsok:
                continue # for ot

            assert(len(params)==len(ot.task.dependenies))
            assert(len(params)<=3)

            print('Parallel: running own task '+ot.task.name)
            started = time.perf_counter()
            #ATTENTION: ot.task.f(...) may call addLateTask() within
            match len(params):
                case 0:
                    ot.task.f()
                case 1:
                    ot.task.f(params[0])
                case 2:
                    ot.task.f(params[0],params[1],params[2])
                case 3:
                    ot.task.f(params[0],params[1],params[2],params[3])
            print('Parallel: done own task '+ot.task.name)
            dt = time.perf_counter() - started
            self._updateWeight(ot.task.name,dt)
            self.doneowntasks[ot.task.name] = 1
        
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
                if p.task.name not in self.donetasks:
                    parentsok = False
                    break
            if not parentsok:
                continue
            bestcandidate = node
        return bestcandidate
 
    def _updateWeight(taskname,dt):
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
        print('Parallel: exception '+str(exceptiontype)+' :'+str(exceptionval))
        print(exceptiontraceback)
        if not self.shuttingdown:
            self.shutdown()
        if not self.joined:
            self.joinAll()
            
        if exceptiontype is None:
            if jsonfname is not None:
                with open(jsonfname, 'wt',encoding='utf-8') as wf:
                    json.dump(self.jsonweights,wf)
            