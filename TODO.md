## TODO:

### MAINSTREAM:
- git2mo: restore according to master.json
- fix ESXS stats
- mo.genprofiles command-line param
- cache: handling updates to wj (those duplicating or invalidating json)
  
### PERFORMANCE:
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
- identify and fix occasional problem with hanging when an exception occurs in child
- make sure that all its shm are always released by child processes
- handle wait() in child process
- Parallel: auto-combine very small tasks
- Parallel: optimize scheduler (current is O(N^2), ouch)
- generalize child-side memoizing cache (shm_name->data); +release from cache
- Parallel: parallel to Task constructor (and automated lists)
- Parallel: switch to data as dependencies
- njson -> pickle (with debug.dumpcaches option)
