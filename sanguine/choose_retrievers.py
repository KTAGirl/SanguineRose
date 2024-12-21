from sanguine.helpers.file_retriever import (FileRetriever, ArchiveFileRetriever,
                                             GithubFileRetriever, ZeroFileRetriever)


def _filter_with_used(inlist: list[tuple[bytes, list[ArchiveFileRetriever]]],
                      out: list[tuple[bytes, ArchiveFileRetriever | None]],
                      used_archives: dict[bytes, int]) -> list[tuple[bytes, list[ArchiveFileRetriever]]]:
    filtered: list[tuple[bytes, list[ArchiveFileRetriever]]] = []
    for x in inlist:
        (h, retrs) = x
        assert len(retrs) >= 2
        done = False
        for r in retrs:
            arh = r.archive_hash()
            assert arh is not None
            if arh in used_archives:
                out.append((h, r))
                used_archives[arh] += 1
                done = True
                break  # for r

        if not done:
            filtered.append((h, retrs))

    return filtered


def _separate_cluster_step(inlist: list[tuple[bytes, list[ArchiveFileRetriever]]],
                           cluster: list[tuple[bytes, list[ArchiveFileRetriever]]],
                           cluster_archives: dict[bytes, int]) -> list[tuple[bytes, list[ArchiveFileRetriever]]]:
    filtered: list[tuple[bytes, list[ArchiveFileRetriever]]] = []
    for x in inlist:  # this code is close, but not identical to the one in _filter_with_used()
        (h, retrs) = x
        assert len(retrs) >= 2
        found = False
        for r in retrs:
            arh = r.archive_hash()
            assert arh is not None
            if arh in cluster_archives:
                cluster_archives[arh] += 1
            else:
                cluster_archives[arh] = 1
            found = True
            # no break here

        if found:
            cluster.append((h, retrs))
        else:
            filtered.append((h, retrs))
    return filtered


def _separate_cluster(inlist: list[tuple[bytes, list[ArchiveFileRetriever]]],
                      cluster: list[tuple[bytes, list[ArchiveFileRetriever]]],
                      cluster_archives: dict[bytes, int]) -> list[tuple[bytes, list[ArchiveFileRetriever]]]:
    prev = inlist
    while True:
        oldclusterlen = len(cluster)
        filtered: list[tuple[bytes, list[ArchiveFileRetriever]]] = _separate_cluster_step(prev, cluster,
                                                                                          cluster_archives)
        assert len(filtered) <= len(prev)
        assert len(prev) - len(filtered) == len(cluster) - oldclusterlen
        if len(filtered) < len(prev):
            prev = filtered
            continue

        return prev


_MAX_EXPONENT_RETRIEVERS = 20  # 2**20 is a million, within reason


def _make_masked_set(cluster_archives: list[bytes], mask: int) -> dict[bytes, int]:
    filtered_archives = {}
    for i in range(len(cluster_archives)):
        if ((1 << i) & mask) != 0:
            h = cluster_archives[i]
            filtered_archives[h] = 1
    return filtered_archives


def _covers_set(cluster: list[tuple[bytes, list[ArchiveFileRetriever]]], filtered_archives: dict[bytes, int]) -> bool:
    for x in cluster:
        (h, retrs) = x
        for r in retrs:
            arh = r.archive_hash()
            assert arh is not None
            if arh not in filtered_archives:
                return False
    return True


def _cost_of_set(filtered_archives: dict[bytes, int], archive_weights: dict[bytes, int]) -> int:
    out = 0
    for arh in filtered_archives:
        out += archive_weights[arh]
    return out


def _full_search_retrievers(out: list[tuple[bytes, FileRetriever | None]],
                            cluster: list[tuple[bytes, list[ArchiveFileRetriever]]],
                            cluster_archives0: dict[bytes, int],
                            archive_weights: dict[bytes, int]):
    cluster_archives = [h for h in cluster_archives0.keys()]
    assert len(cluster_archives) <= _MAX_EXPONENT_RETRIEVERS
    bestcost = None
    bestset = None
    for mask in range(2 ** len(cluster_archives)):
        filtered_archives = _make_masked_set(cluster_archives, mask)
        if _covers_set(cluster, filtered_archives):
            cost = _cost_of_set(filtered_archives, archive_weights)
            if bestcost is None or cost < bestcost:
                bestcost = cost
                bestset = filtered_archives

    assert bestset is not None
    for x in cluster:
        (h, retrs) = x
        done = False
        for r in retrs:
            arh = r.archive_hash()
            assert arh is not None
            if arh in bestset:
                out.append((h, r))
                done = True
                break  # for x

        assert done


def _number_covered_by_archive(cluster: list[tuple[bytes, list[ArchiveFileRetriever]]], h0: bytes) -> int:
    out = 0
    for x in cluster:
        (h, retrs) = x
        for r in retrs:
            arh = r.archive_hash()
            assert arh is not None
            if arh == h0:
                out += 1
                break  # for r
    return out


def _retriever_key(fr: FileRetriever, archive_weights: dict[bytes, int]) -> str:
    if isinstance(fr, ZeroFileRetriever):
        return '0'
    elif isinstance(fr, GithubFileRetriever):
        return '1.' + str(fr.file_hash)
    elif isinstance(fr, ArchiveFileRetriever):
        arh = fr.archive_hash()
        assert arh is not None
        return '2.' + str(archive_weights[arh]) + '.' + str(fr.file_hash)
    else:
        assert False


def choose_retrievers(inlist0: list[tuple[bytes, list[FileRetriever]]], archive_weights: dict[bytes, int]) -> list[
    tuple[bytes, FileRetriever | None]]:
    out: list[tuple[bytes, FileRetriever | None]] = []

    # sorting
    inlist: list[tuple[bytes, list[FileRetriever]]] = []
    for item in inlist0:
        inlist.append((item[0], sorted(item[1], key=lambda fr: _retriever_key(fr, archive_weights))))

    # first pass: choosing unique ones, as well as GitHub ones
    remaining: list[tuple[bytes, list[ArchiveFileRetriever]]] = []
    used_archives: dict[bytes, int] = {}
    for x in inlist:
        (h, retrs) = x
        if len(retrs) == 0:
            out.append((h, None))
            continue
        elif len(retrs) == 1:
            r0: FileRetriever = retrs[0]
            out.append((h, r0))
            arh = None
            if isinstance(r0, ArchiveFileRetriever):
                arh = r0.archive_hash()
            if arh is not None:
                if arh not in used_archives:
                    used_archives[arh] = 1
                else:
                    used_archives[arh] += 1
            continue

        done = False
        for r in retrs:
            if isinstance(r, GithubFileRetriever):
                out.append((h, r))
                done = True
                break  # for r

        if done:
            continue  # for x

        # cannot do much now, placing it to remaining[]
        if __debug__:
            for r in retrs:
                assert isinstance(r, ArchiveFileRetriever)

        # noinspection PyTypeChecker
        #              we just asserted that all members of retrs are ArchiveFileRetriever
        retrs1: list[ArchiveFileRetriever] = retrs
        remaining.append((h, retrs1))

    # separate into clusters
    remaining = _filter_with_used(remaining, out, used_archives)
    clusters: list[list[tuple[bytes, list[ArchiveFileRetriever]]]] = []
    clusters_archives: list[dict[bytes, int]] = []
    while len(remaining) > 0:
        cluster: list[tuple[bytes, list[ArchiveFileRetriever]]] = [remaining[0]]
        remaining = remaining[1:]
        cluster_archives = {}
        for x in cluster[0]:
            (h, retrs) = x
            if h in cluster_archives:
                cluster_archives[h] += 1
            else:
                cluster_archives[h] = 1

        oldremaininglen = len(remaining)
        oldclusterlen = len(cluster)
        remaining = _separate_cluster(remaining, cluster, cluster_archives)
        assert len(remaining) <= oldremaininglen
        assert len(cluster) - oldclusterlen == oldremaininglen - len(remaining)
        clusters.append(cluster)
        clusters_archives.append(cluster_archives)

    assert len(clusters_archives) == len(clusters)
    for i in range(len(clusters)):
        cluster = clusters[i]
        cluster_archives: dict[bytes, int] = clusters_archives[i]

        while len(cluster_archives) > _MAX_EXPONENT_RETRIEVERS:
            # "greedy" reduction of search space
            #           for the time being, we're just taking lowest-cost archives (starting from highest-use within lowest-cost)
            xarchives: list[tuple[bytes, int, int]] = sorted(
                [(arh, archive_weights[arh], _number_covered_by_archive(cluster, arh)) for arh in
                 cluster_archives.keys()],
                key=lambda x2: (x2[1], x2[2]))
            # we should not try cutting all (len(cluster_archives)-_MAX_EXPONENT) at once, as filtering can change
            #               the pattern
            arh = xarchives[0][0]
            assert arh not in cluster_archives
            cluster_archives[arh] = 1
            cluster = _filter_with_used(cluster, out, cluster_archives)

        assert len(cluster_archives) <= _MAX_EXPONENT_RETRIEVERS
        _full_search_retrievers(out, cluster, cluster_archives, archive_weights)

    return out
