## TODO:

### MAINSTREAM:
- git2mo.changestofolder and git2mo.discardchanges: restore according to master.json
- noui.py
- user config (specified in project.config, something like ../project-user.json); support only download dirs override and login credentials (github, Nexus) there
- install.py and install plugins (dependency-driven): currently install MSVC runtime, pip, MO2.exe->zip
- download plugins: github, nexus, mega?, LL later (with an emphasis on equal treatment of Nexus and LL modders)

### IMPROVEMENTS:
- cache targetgithub dir in filecache, rm wjHash() from master.py
- better and more systemic logging
- fix ESXS stats
- mo.genprofiles command-line param
- cache: handling updates to wj (those duplicating or invalidating json)
- cache: exclusive json and non-json (removing from non-json when adding json; remove search when looking for, if any)
  
### PERFORMANCE/OPTIMIZATIONS:
- hc -> SharedReturn
- masterjson -> under _microCache()
- reading masterjson -> Tasks
- Folders -> SharedPublish, proc-level memoizing
- Cache in noui.py, with a monitoring daemon
- hashing -> Tasks
- unpacking archives -> Tasks
- jsonfiles (all) -> sharedmem
- Parallelize Reconciliation

### PARALLEL:
- logging
- identify and fix occasional problem with hanging when an exception occurs in child
- make sure that all its shm are always released by child processes
- handle wait() in child process
- Parallel: auto-combine very small tasks
- Parallel: optimize scheduler (current is O(N^2), ouch)
- generalize child-side memoizing cache (shm_name->data); +release from cache
- Parallel: parallel to Task constructor (and automated lists)
- Parallel: switch to data as dependencies
- njson -> pickle (with debug.dumpcaches option)
