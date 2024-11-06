## TODO:

### MAINSTREAM:
- master.py: refactor handling of ownmods
- remove PROJECT.py (in project there should be config only, and .bat files)
- git2mo.changestofolder and git2mo.discardchanges: restore according to master.json
- replace assert(False) with common.abort() where necessary
- better and more systemic logging
- fix ESXS stats
- mo.genprofiles command-line param
- cache: handling updates to wj (those duplicating or invalidating json)
- cache: exclusive json and non-json (removing from non-json when adding json; remove search when looking for, if any)
  
### PERFORMANCE/OPTIMIZATIONS:
- master.json size optimization: text-based "compression" (hierarchical representation) 
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
