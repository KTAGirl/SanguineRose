from sanguine.common import *


def pickled_cache(cachedir: str, cachedata: dict[str, any], prefix: str, origfiles: list[str],
                  calc: Callable[[any], any], params: any = None) -> tuple[any, dict[str:str]]:
    assert isinstance(origfiles, list)
    readpaths = cachedata.get(prefix + '.files')

    if params is not None:
        # comparing as JSONs is important
        readparams = as_json(cachedata.get(prefix + '.params'))
        jparams = as_json(params)
        sameparams = (readparams == jparams)
    else:
        sameparams = True

    samefiles = readpaths is not None and len(readpaths) == len(origfiles)
    if sameparams and samefiles:
        readpaths = sorted(readpaths)
        origfiles = sorted(origfiles)
        for i in range(len(readpaths)):
            rd = readpaths[i]
            of = (origfiles[i], os.path.getmtime(origfiles[i]))
            assert isinstance(rd, list)
            assert is_normalized_file_path(rd[0])
            assert is_normalized_file_path(of[0])

            jrd = as_json(rd)
            jof = as_json(of)

            if jrd != jof:  # lists are sorted, there should be exact match here
                samefiles = False
                break

    pfname = cachedir + prefix + '.pickle'
    if sameparams and samefiles and os.path.isfile(pfname):
        info('pickledCache(): Yahoo! Can use cache for ' + prefix)
        with open(pfname, 'rb') as rf:
            return pickle.load(rf), {}

    cachedataoverwrites = {}
    files = [(of, os.path.getmtime(of)) for of in origfiles]
    out = calc(params)

    for f in files:
        abort_if_not(f[1] == os.path.getmtime(f[
                                                  0]))  # if any of the files we depend on, has changed while calc() was calculated - something is really weird is going on here

    with open(cachedir + prefix + '.pickle', 'wb') as wf:
        # noinspection PyTypeChecker
        pickle.dump(out, wf)
    cachedataoverwrites[prefix + '.files'] = files
    if params is not None:
        cachedataoverwrites[prefix + '.params'] = params
    return out, cachedataoverwrites
