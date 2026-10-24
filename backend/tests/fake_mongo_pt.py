"""Coleções Mongo falsas em memória para os testes .pt (sem MongoDB). Suporta o subconjunto usado pelas rotas testadas:
igualdade, $in, $exists, $gte, $ne; projeções de exclusão/inclusão; sort/skip/limit/to_list e iteração assíncrona;
$set, $inc, $push com $each, $unset."""
import copy
import itertools

_ids = itertools.count(1)


def _match_value(v, cond):
    if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
        for op, arg in cond.items():
            if op == "$in" and v not in arg:
                return False
            if op == "$exists" and (v is not _MISSING) != bool(arg):
                return False
            if op == "$gte" and (v is _MISSING or v is None or v < arg):
                return False
            if op == "$ne" and v == arg:
                return False
        return True
    return v == cond


_MISSING = object()


def match(doc, q):
    for k, cond in (q or {}).items():
        if k == "$or":
            if not any(match(doc, sub) for sub in cond):
                return False
            continue
        if not _match_value(doc.get(k, _MISSING), cond):
            return False
    return True


def project(doc, proj):
    d = {k: copy.deepcopy(v) for k, v in doc.items()}
    if not proj:
        return d
    inc = {k for k, v in proj.items() if v and k != "_id"}
    if inc:
        d = {k: v for k, v in d.items() if k in inc or (k == "_id" and proj.get("_id", 1))}
    else:
        for k, v in proj.items():
            if not v:
                d.pop(k, None)
    return d


class Cursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, key, direction=1):
        self.docs.sort(key=lambda d: (d.get(key) is None, d.get(key)), reverse=direction == -1)
        return self

    def skip(self, n):
        self.docs = self.docs[n:]
        return self

    def limit(self, n):
        self.docs = self.docs[:n]
        return self

    async def to_list(self, n):
        return self.docs[:n] if n else self.docs

    def __aiter__(self):
        self._it = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration from None


class Result:
    def __init__(self, n=0):
        self.deleted_count = self.modified_count = self.matched_count = n


class Coll:
    def __init__(self):
        self.docs = []

    async def insert_one(self, d):
        d = copy.deepcopy(d)
        d.setdefault("_id", next(_ids))
        self.docs.append(d)
        return Result(1)

    async def find_one(self, q, proj=None):
        d = next((d for d in self.docs if match(d, q)), None)
        return project(d, proj) if d else None

    def find(self, q=None, proj=None):
        return Cursor([project(d, proj) for d in self.docs if match(d, q or {})])

    async def count_documents(self, q):
        return sum(1 for d in self.docs if match(d, q))

    @staticmethod
    def _apply(d, upd):
        for k, v in (upd.get("$set") or {}).items():
            d[k] = v
        for k, v in (upd.get("$inc") or {}).items():
            d[k] = d.get(k, 0) + v
        for k, v in (upd.get("$push") or {}).items():
            d.setdefault(k, [])
            d[k].extend(v["$each"] if isinstance(v, dict) and "$each" in v else [v])
        for k in (upd.get("$unset") or {}):
            d.pop(k, None)

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if match(d, q):
                self._apply(d, upd)
                return Result(1)
        return Result(0)

    async def find_one_and_update(self, q, upd, return_document=False, projection=None, **_):
        d = next((d for d in self.docs if match(d, q)), None)
        if d is None:
            return None
        before = project(d, projection)
        self._apply(d, upd)
        return project(d, projection) if return_document else before

    async def update_many(self, q, upd):
        n = 0
        for d in self.docs:
            if match(d, q):
                self._apply(d, upd)
                n += 1
        return Result(n)

    async def delete_one(self, q):
        for i, d in enumerate(self.docs):
            if match(d, q):
                del self.docs[i]
                return Result(1)
        return Result(0)

    async def delete_many(self, q):
        n = len(self.docs)
        self.docs = [d for d in self.docs if not match(d, q)]
        return Result(n - len(self.docs))


class FakeDB:
    def __init__(self):
        self._c = {}

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return self._c.setdefault(name, Coll())

    def __getitem__(self, name):
        return getattr(self, name)
