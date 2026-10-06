#!/usr/bin/env python3
"""Run the released historical CHILS adapters on a public graph fixture.

This small public runner is new packaging code. The adapter functions that it
calls are exact excerpts or byte-identical copies of the experimental code.
"""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from adapters.legacy.model import Contact, Graph


def read_graph(path):
    if path.suffix == '.json':
        raw=json.loads(path.read_text(encoding='utf-8'))
        names=sorted(raw['weights_ticks'],key=int)
        if names != [str(i) for i in range(len(names))]:
            raise ValueError('JSON fixture requires contiguous zero-based numeric vertex IDs')
        weights={int(v):int(raw['weights_ticks'][v]) for v in names}
        adjacency={i:set() for i in weights}
        for a,b in raw['edges']:
            a,b=int(a),int(b)
            if a == b or a not in adjacency or b not in adjacency:
                raise ValueError('Invalid edge')
            adjacency[a].add(b);adjacency[b].add(a)
    else:
        lines=path.read_text(encoding='ascii').splitlines()
        n,m,fmt=map(int,lines[0].split())
        if fmt != 10 or len(lines) != n+1:
            raise ValueError('Expected weighted METIS format 10 with one line per vertex')
        weights={};adjacency={}
        for i,line in enumerate(lines[1:]):
            row=list(map(int,line.split()))
            if not row: raise ValueError('Vertex line must start with a weight')
            weights[i]=row[0];adjacency[i]={u-1 for u in row[1:]}
            if len(adjacency[i]) != len(row)-1: raise ValueError('Duplicate adjacency')
        if sum(map(len,adjacency.values())) != 2*m:
            raise ValueError('Incorrect edge count')
    if not weights or any(w<=0 or w>=2**63 for w in weights.values()) or sum(weights.values())>=2**63:
        raise ValueError('Expected positive weights and total below signed64 maximum')
    for i,neighbors in adjacency.items():
        if i in neighbors or any(j not in weights or i not in adjacency[j] for j in neighbors):
            raise ValueError('Adjacency must be symmetric, in range and loop-free')
    return weights,adjacency


def legacy_graph(weights,adjacency):
    # Zero padding preserves the numeric tie-breaking order for the public fixture.
    width=max(1,len(str(len(weights)-1)))
    names={i:str(i).zfill(width) for i in weights}
    contacts=tuple(Contact(names[i],Fraction(weights[i],1000000),'synthetic','synthetic',0,1) for i in weights)
    edges=frozenset((names[i],names[j]) for i in adjacency for j in adjacency[i] if i<j)
    return Graph('public_CHILS_input',contacts,edges,provenance={'weight_ticks':{names[i]:weights[i] for i in weights}}),names


class PublicMeter:
    """Minimal cost counter for calling the exact STK-v1 graph/seed excerpt."""
    def __init__(self): self.sealed=False;self.work=0
    def tick(self,name,count=1): self.work+=count


def run(args):
    executable=args.executable.resolve()
    if not executable.is_file(): raise FileNotFoundError('Build CHILS or provide --executable')
    # The original benchmark imports its dependencies before starting its clock.
    if args.adapter == 'stk-v2':
        from adapters.stk_v2.graph import IntGraph, degree_seed, feasible
        from adapters.stk_v2.native import child_cpu, run_native, total_cpu
        import numpy as np
    elif args.adapter == 'stk-v1':
        from adapters.stk_v1.graph import static_completion, value_ticks
        from adapters.stk_v1.published_weighted_baselines import run_chils
    else:
        from importlib import import_module
        module={'legacy':'advanced_baselines','v06':'advanced_baselines_v06','gcd':'advanced_baselines_gcd_v06'}[args.adapter]
        adapter=import_module('adapters.legacy.'+module)
    cpu_start=time.process_time();wall_start=time.perf_counter()
    weights,adjacency=read_graph(args.graph)
    common=dict(adapter=args.adapter,population=args.population,native_threads=1,seed=args.seed,
                declared_seconds=args.seconds,vertices=len(weights),edges=sum(map(len,adjacency.values()))//2,
                graph_file_sha256=hashlib.sha256(args.graph.read_bytes()).hexdigest(),
                executable_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(),
                runner_scope='Public packaging runner; historical adapter definitions are unchanged',
                objective_unit='integer microseconds; objective seconds = exact ticks / 1000000')
    if args.adapter == 'stk-v2':
        children_start=child_cpu()
        graph=IntGraph(adjacency,weights,[str(i) for i in weights],{}, {},np.empty(0,dtype=np.int64),np.empty(0,dtype=np.int64))
        state=degree_seed(graph)
        native_args=SimpleNamespace(method='chils_ils' if args.population==1 else 'chils',
            seconds=args.seconds,native_executable=str(executable),seed=args.seed)
        result=run_native(graph,state,native_args,cpu_start,children_start,feasible)
        chosen=set(result['selected'])
        result['cpu_seconds']=total_cpu(cpu_start,children_start)
        result['selected_vertex_ids_zero_based']=sorted(chosen)
        result['feasible']=chosen<=weights.keys() and feasible(graph,chosen)
    else:
        graph,names=legacy_graph(weights,adjacency)
        reverse={name:i for i,name in names.items()}
        if args.adapter == 'stk-v1':
            initial=static_completion(graph,set(graph.nodes),set(),PublicMeter())
            initial_value=value_ticks(graph,initial)
            native=run_chils(graph,initial,max(0,args.seconds-(time.process_time()-cpu_start)),
                            args.seed,str(executable),population=args.population)
            chosen=set(initial)
            if native.get('selected') is not None and value_ticks(graph,native['selected'])>initial_value:
                chosen=set(native['selected'])
            result=dict(native=native,seed_value_ticks=initial_value,selected=sorted(chosen),
                selected_vertex_ids_zero_based=sorted(reverse[i] for i in chosen),
                value_ticks=value_ticks(graph,chosen),feasible=graph.feasible(chosen),
                cpu_seconds=time.process_time()-cpu_start+float(native.get('child_cpu_seconds') or 0),
                execution_status=native['status'])
        else:
            result=adapter.run_solver(graph,str(executable),'CHILS_ILS' if args.population==1 else 'CHILS',
                seconds=args.seconds,seed=args.seed,hard_wall_seconds=max(30,args.seconds+3))
            chosen=result.get('selected')
            result['selected_vertex_ids_zero_based']=(sorted(reverse[i] for i in chosen) if chosen is not None else None)
            result['value_ticks']=(sum(graph.provenance['weight_ticks'][i] for i in chosen) if chosen is not None else None)
            result['cpu_seconds']=time.process_time()-cpu_start+float(result.get('child_cpu_seconds') or 0)
    result.update(common)
    result['wall_seconds']=time.perf_counter()-wall_start
    result['value_seconds_exact']=(str(Fraction(result['value_ticks'],1000000)) if result.get('value_ticks') is not None else None)
    # Public receipts retain command flags while omitting transient absolute paths.
    def sanitize(value):
        if isinstance(value,dict):
            return {k:sanitize(v) for k,v in value.items() if k not in ('command','stdout','stderr')}
        if isinstance(value,list):return [sanitize(v) for v in value]
        return value
    return sanitize(result)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graph',type=Path,default=ROOT/'examples/toy.json')
    parser.add_argument('--adapter',choices=('legacy','v06','gcd','stk-v1','stk-v2'),default='stk-v2')
    parser.add_argument('--population',type=int,choices=(1,4),default=1)
    parser.add_argument('--seconds',type=float,default=.2)
    parser.add_argument('--seed',type=int,default=2)
    parser.add_argument('--executable',type=Path,default=ROOT/'third_party/CHILS/CHILS')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.seconds<=0:parser.error('--seconds must be positive')
    result=run(args)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding='utf-8')
    print(json.dumps({k:result.get(k) for k in ('adapter','population','feasible','value_ticks','value_seconds_exact','cpu_seconds','wall_seconds','execution_status')}))
    if result.get('feasible') is not True:raise SystemExit(1)

if __name__=='__main__':main()
