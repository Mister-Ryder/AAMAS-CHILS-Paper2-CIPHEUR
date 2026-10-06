"""Run unmodified published MWIS solver executables and verify returned sets."""
from __future__ import annotations
from fractions import Fraction
from hashlib import sha256
from math import lcm
import os,subprocess,tempfile,time
from pathlib import Path
from .model import Graph

def metis_input(graph:Graph,fixed=(),excluded=()):
    active=sorted(graph.available(fixed,excluded));index={v:i+1 for i,v in enumerate(active)}
    weights={v:Fraction(graph.nodes[v].weight) for v in active};scale=1
    for w in weights.values():scale=lcm(scale,w.denominator)
    integers={v:int(w*scale) for v,w in weights.items()}
    if sum(integers.values())>2**31-1 or any(w<0 for w in integers.values()):
        raise ValueError('Exact integer scaling exceeds conservative solver weight range')
    edges=sum(len(graph.adj[v]&index.keys()) for v in active)//2
    lines=[f'{len(active)} {edges} 10']
    lines.extend(str(integers[v])+' '+ ' '.join(map(str,sorted(index[u] for u in graph.adj[v]&index.keys()))) for v in active)
    return '\n'.join(lines)+'\n',active,scale

def parse_solution(text,active,output_format):
    values=[int(x) for x in text.split()]
    if output_format=='partition_flags':
        if len(values)!=len(active) or not set(values)<={0,1}:raise ValueError('Invalid partition membership output')
        return [v for v,flag in zip(active,values) if flag==1]
    if output_format=='one_based_ids':
        if len(set(values))!=len(values) or any(i<1 or i>len(active) for i in values):raise ValueError('Invalid one-based solution IDs')
        return [active[i-1] for i in values]
    raise ValueError('Unknown explicit solution format')

def solver_command(executable,name,graph_file,solution_file,seconds,seed):
    if name in ('CHILS','CHILS_ILS'):
        states='1' if name=='CHILS_ILS' else '4'
        return [str(executable),'-g',str(graph_file),'-o',str(solution_file),'-p',states,'-c','1','-s','0.1','-t',str(seconds),'-r',str(seed)],'one_based_ids'
    command=[str(executable),str(graph_file),f'--output={solution_file}',f'--time_limit={seconds}',f'--seed={seed}']
    if name=='M2WIS':command+=['--config=mmwis',f'--evo_time_limit={seconds}',f'--ils_time_limit={seconds}']
    elif name not in ('Struction','WeightedBR'):raise ValueError('Unknown published solver')
    return command,'partition_flags'

def run_solver(graph,executable,name,fixed=(),excluded=(),seconds=5,seed=1,hard_wall_seconds=30):
    started=time.perf_counter();text,active,scale=metis_input(graph,fixed,excluded)
    common={'method':name,'seed':seed,'declared_seconds':seconds,'hard_wall_seconds':hard_wall_seconds,
            'integer_scale':scale,'input_sha256':sha256(text.encode()).hexdigest(),
            'executable_sha256':sha256(Path(executable).read_bytes()).hexdigest(),
            'threads':1,'exact_optimum_claimed':False}
    if not active:return {**common,'selected':list(fixed),'value':graph.value(fixed),'feasible':True,'completed':True,'seconds':time.perf_counter()-started}
    try:
        import resource
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
    except ImportError:resource=before=None
    with tempfile.TemporaryDirectory(prefix='cipheur_solver_') as temp:
        root=Path(temp);source=root/'input.graph';solution=root/'solution.txt';source.write_text(text)
        command,fmt=solver_command(executable,name,source,solution,seconds,seed)
        environment={**os.environ,'OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','MKL_NUM_THREADS':'1'}
        stdout=stderr=raw='';returncode=None
        try:
            result=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=hard_wall_seconds,env=environment)
            returncode=result.returncode
            stdout=result.stdout.decode(errors='replace');stderr=result.stderr.decode(errors='replace')
            if result.returncode!=0:raise ValueError(f'Solver exit status {result.returncode}')
            if not solution.exists():raise ValueError('Solver returned no saved solution')
            raw=solution.read_text();selected=list(fixed)+parse_solution(raw,active,fmt)
            if not graph.feasible(selected) or set(selected)&set(excluded):raise ValueError('Returned solution fails original graph feasibility')
            row={**common,'selected':sorted(selected),'value':graph.value(selected),'feasible':True,'completed':True,
                 'output_format':fmt,'solution_text':raw,'stdout':stdout,'stderr':stderr,'status':'checked_feasible_incumbent'}
        except (subprocess.TimeoutExpired,ValueError) as error:
            if isinstance(error,subprocess.TimeoutExpired):
                stdout=(error.stdout or b'').decode(errors='replace')
                stderr=(error.stderr or b'').decode(errors='replace')
            row={**common,'selected':None,'value':None,'feasible':None,'completed':False,'status':str(error),
                 'stdout':stdout,'stderr':stderr,'solution_text':raw}
        row['returncode']=returncode
        row['command']=command
        if resource is not None:
            after=resource.getrusage(resource.RUSAGE_CHILDREN)
            row['child_cpu_seconds']=(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime)
        row['seconds']=time.perf_counter()-started
        return row
