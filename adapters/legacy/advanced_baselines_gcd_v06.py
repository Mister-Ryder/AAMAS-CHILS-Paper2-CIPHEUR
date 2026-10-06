"""Lossless common-factor native encoding, separate from frozen V06 studies.

Integerize exact rational weights by their denominator LCM, then divide every
integer by their positive common GCD. No clipping, rounding or rank replacement
is used. The exact reverse factor restores original objective values. Native
heuristics may still be scale-sensitive: this is a separately recorded adapter.
The original conservative wrapper and its assigned outcomes remain unchanged.
"""
from __future__ import annotations
from fractions import Fraction
from hashlib import sha256
from math import gcd, lcm
import os
from pathlib import Path
import subprocess
import tempfile
import time

from .advanced_baselines import parse_solution, solver_command


def metis_input(graph,name,fixed=(),excluded=()):
    active=sorted(graph.available(fixed,excluded));index={v:i+1 for i,v in enumerate(active)}
    weights={v:Fraction(graph.nodes[v].weight) for v in active};scale=1
    for w in weights.values():scale=lcm(scale,w.denominator)
    integers={v:int(w*scale) for v,w in weights.items()}
    if any(w<0 for w in integers.values()):
        raise ValueError("Native MWIS requires nonnegative weights")
    divisor=0
    for value in integers.values():divisor=gcd(divisor,value)
    divisor=max(1,divisor)
    integers={v:value//divisor for v,value in integers.items()}
    limit=2**63-1 if name in ("CHILS","CHILS_ILS") else 2**31-1
    contract="CHILS_source_verified_signed64_total" if limit==2**63-1 else "conservative_signed32_total"
    if sum(integers.values())>limit or any(w<0 or w>limit for w in integers.values()):
        raise ValueError("Exact integer scaling exceeds "+contract)
    edges=sum(len(graph.adj[v]&index.keys()) for v in active)//2
    text=f"{len(active)} {edges} 10\n"
    text+="\n".join(str(integers[v])+" "+" ".join(map(str,sorted(index[u] for u in graph.adj[v]&index.keys()))) for v in active)+"\n"
    return text,active,scale,contract,divisor


def run_solver(graph,executable,name,fixed=(),excluded=(),seconds=5,seed=1,hard_wall_seconds=30):
    started=time.perf_counter()
    common={"method":name,"seed":seed,"declared_seconds":seconds,"hard_wall_seconds":hard_wall_seconds,
            "threads":1,"exact_optimum_claimed":False,"deadline_scope":"Native internal nominal wall target; outer guard is separate"}
    try:text,active,scale,contract,divisor=metis_input(graph,name,fixed,excluded)
    except ValueError as error:
        return {**common,"selected":None,"value":None,"feasible":None,"completed":False,
                "status":"encoding_not_supported","encoding_error":str(error),"solver_invoked":False,
                "seconds":time.perf_counter()-started}
    common.update(integer_scale=scale,integer_weight_gcd=divisor,
                  integer_objective_to_original_exact=str(Fraction(divisor,scale)),
                  encoding_version="v06_LCM_then_common_GCD_lossless_001",
                  integer_range_contract=contract,input_sha256=sha256(text.encode()).hexdigest(),
                  executable_sha256=sha256(Path(executable).read_bytes()).hexdigest())
    if not active:
        return {**common,"selected":list(fixed),"value":graph.value(fixed),"feasible":True,"completed":True,
                "status":"empty_residual","solver_invoked":False,"seconds":time.perf_counter()-started}
    try:
        import resource
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
    except ImportError:resource=before=None
    with tempfile.TemporaryDirectory(prefix="cipheur_v06_solver_") as temp:
        root=Path(temp);source=root/"input.graph";solution=root/"solution.txt";source.write_text(text,encoding="ascii")
        command,fmt=solver_command(executable,name,source,solution,seconds,seed)
        environment={**os.environ,"OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1"}
        stdout=stderr=raw="";returncode=None
        try:
            child=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=hard_wall_seconds,env=environment)
            returncode=child.returncode;stdout=child.stdout.decode(errors="replace");stderr=child.stderr.decode(errors="replace")
            if returncode!=0:raise ValueError("Solver exit status "+str(returncode))
            if not solution.is_file():raise ValueError("Solver returned no saved solution")
            raw=solution.read_text(encoding="ascii")
            selected=list(fixed)+parse_solution(raw,active,fmt)
            if not graph.feasible(selected) or set(selected)&set(excluded):raise ValueError("Solution violates original graph feasibility")
            value_exact=sum((Fraction(graph.nodes[v].weight) for v in selected),Fraction())
            row={**common,"selected":sorted(selected),"value":graph.value(selected),"value_exact":str(value_exact),
                 "feasible":True,"completed":True,"status":"checked_feasible_incumbent","solution_text":raw,
                 "output_format":fmt,"stdout":stdout,"stderr":stderr,"solver_invoked":True}
        except (subprocess.TimeoutExpired,ValueError) as error:
            if isinstance(error,subprocess.TimeoutExpired):
                stdout=(error.stdout or b"").decode(errors="replace");stderr=(error.stderr or b"").decode(errors="replace")
            row={**common,"selected":None,"value":None,"feasible":None,"completed":False,
                 "status":"hard_guard_timeout" if isinstance(error,subprocess.TimeoutExpired) else "solver_output_error",
                 "error":str(error),"stdout":stdout,"stderr":stderr,"solution_text":raw,"solver_invoked":True}
        row["returncode"]=returncode;row["command"]=command
        if resource is not None:
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            row["child_cpu_seconds"]=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
        row["seconds"]=time.perf_counter()-started
        row["nominal_target_exceeded"]=row["seconds"]>seconds
        return row
