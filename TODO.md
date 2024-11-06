## TODO:

### MAINSTREAM:
- remove PROJECT.py (in project there should be only 2 configs PROJECT.json and PROJECT-user.json, and .bat files such as PROJECT.bat, PROJECT-debug.bat, and shortcuts PROJECT-mo2git.bat, PROJECT-git2mo.bat etc.)
- replace assert() with common.always_assert() wherever modder's/user's errors are expected (mostly in Folders)
- targetgithub dir->filecache, rm wjHash() from master.py
- git2mo.changestofolder and git2mo.discardchanges: restore according to master.json
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
- Cache in a monitoring daemon?
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
