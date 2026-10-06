"""Exact int64 METIS transport for the published CHILS solver (SEA 2025)."""
import hashlib, json, os, pathlib, subprocess, tempfile, time

def run_chils(graph, initial, remaining_seconds, seed, executable, population=1, output_root=None):
    started=time.monotonic()
    try:
        import resource
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        child_before=before.ru_utime+before.ru_stime
    except ImportError:
        resource=None; child_before=None
    result={'selected':None,'child_cpu_seconds':None,'measurement_available':resource is not None,
            'population':population,'native_threads':1,'seed':seed,'remaining_seconds':remaining_seconds,
            'objective_transport':'original integer microsecond ticks; no weight rounding or scaling',
            'publication':'10.4230/LIPIcs.SEA.2025.22'}
    if remaining_seconds<=0:
        return dict(result,status='budget_exhausted_before_native',wall_seconds=0.0)
    parent=pathlib.Path(output_root) if output_root else None
    if parent: parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='chils-',dir=str(parent) if parent else None) as td:
        td=pathlib.Path(td); inp=td/'graph.metis'; init=td/'initial.ids'; out=td/'selected.ids'
        nodes=sorted(graph.nodes); indices={n:i+1 for i,n in enumerate(nodes)}
        weights=graph.provenance['weight_ticks']
        with inp.open('w',encoding='ascii') as f:
            f.write(f'{len(nodes)} {sum(len(graph.adj[n]) for n in nodes)//2} 10\n')
            for n in nodes:
                w=int(weights[n])
                if w<=0 or w>=2**63: raise ValueError('Unsupported int64 weight')
                f.write(str(w)+' '+ ' '.join(str(indices[a]) for a in sorted(graph.adj[n]))+'\n')
        init.write_text(''.join(str(indices[n])+'\n' for n in sorted(initial)),encoding='ascii')
        # Input transport consumes the same parent CPU budget; bound its wall cost conservatively.
        native_seconds=max(0.001,remaining_seconds-(time.monotonic()-started))
        argv=[str(executable),'-g',str(inp),'-i',str(init),'-o',str(out),'-p',str(population),'-c','1',
              '-t',str(native_seconds),'-s','0','-r',str(seed)]
        result['argv_template']=['CHILS','-g','graph.metis','-i','initial.ids','-o','selected.ids','-p',str(population),'-c','1','-t',str(native_seconds),'-s','0','-r',str(seed)]
        result['input_sha256']=hashlib.sha256(inp.read_bytes()).hexdigest()
        try:
            proc=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(2.0,native_seconds+2.0),check=False)
            result.update(exit_code=proc.returncode,stdout=proc.stdout.decode('utf-8','replace')[-12000:],stderr=proc.stderr.decode('utf-8','replace')[-4000:])
            if proc.returncode!=0: result['status']='native_failed'
            elif not out.is_file(): result['status']='missing_native_solution'
            else:
                ids=[int(v) for v in out.read_text(encoding='ascii').split()]
                if len(ids)!=len(set(ids)) or any(i<1 or i>len(nodes) for i in ids): raise ValueError('Malformed native vertex IDs')
                selected={nodes[i-1] for i in ids}
                if any(graph.adj[n]&selected for n in selected): raise ValueError('Native schedule is infeasible')
                result.update(selected=sorted(selected),status='ok',solution_sha256=hashlib.sha256(out.read_bytes()).hexdigest())
        except subprocess.TimeoutExpired as exc:
            result.update(status='native_wall_guard_timeout',stdout=(exc.stdout or b'').decode('utf-8','replace')[-12000:])
        except Exception as exc:
            result.update(status='native_transport_failure',error=repr(exc))
    if resource is not None:
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        result['child_cpu_seconds']=after.ru_utime+after.ru_stime-child_before
    result['wall_seconds']=time.monotonic()-started
    return result
