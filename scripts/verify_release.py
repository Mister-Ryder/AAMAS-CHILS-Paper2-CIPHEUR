#!/usr/bin/env python3
"""Verify public CHILS source hashes and real solver execution on a tiny graph."""
from __future__ import annotations
import argparse
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import platform
import subprocess
import sys
from types import SimpleNamespace

from run_chils import ROOT,read_graph,run

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--executable',type=Path,default=ROOT/'third_party/CHILS/CHILS')
    parser.add_argument('--real-train',action='store_true',help='Also run both populations for one second on the released actual TRAIN graph')
    parser.add_argument('--output',type=Path,default=ROOT/'evidence/release_validation.json')
    args=parser.parse_args()
    provenance=json.loads((ROOT/'evidence/source_provenance.json').read_text(encoding='utf-8'))
    for entry in provenance['upstream']['files']:
        assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256']
    weights,adj=read_graph(ROOT/'examples/toy.json')
    optimum=0
    for size in range(len(weights)+1):
        for selected in itertools.combinations(weights,size):
            chosen=set(selected)
            if all(not(adj[v]&chosen) for v in chosen):optimum=max(optimum,sum(weights[v] for v in chosen))
    assert optimum==28000000
    records=[]
    for adapter in ('legacy','v06','gcd','stk-v1','stk-v2'):
        for population in (1,4):
            result=run(SimpleNamespace(executable=args.executable,graph=ROOT/'examples/toy.json',
                adapter=adapter,population=population,seconds=.2,seed=2))
            assert result['feasible'] is True and result['value_ticks']==optimum,(adapter,population,result)
            records.append(result)
    if args.real_train:
        export=json.loads((ROOT/'evidence/train_graph_export.json').read_text(encoding='utf-8'))
        graphpath=ROOT/export['export_path']
        assert hashlib.sha256(graphpath.read_bytes()).hexdigest()==export['export_sha256']
        for population in (1,4):
            result=run(SimpleNamespace(executable=args.executable,graph=graphpath,
                adapter='stk-v2',population=population,seconds=1,seed=2))
            assert result['feasible'] is True
            assert result['native']['input_sha256']==export['export_sha256']
            assert result['value_ticks']>=result['seed_value_ticks']
            weights,adj=read_graph(graphpath);selected=set(result['selected_vertex_ids_zero_based'])
            assert sum(weights[v] for v in selected)==result['value_ticks']
            assert float(Fraction(result['value_ticks'],1000000))==float(Fraction(result['value_seconds_exact']))
            records.append(result)
    summary={'scope':'New public release validation, not replacement for historical experiment outcomes',
        'platform':platform.platform(),'python':platform.python_version(),
        'executable_sha256':hashlib.sha256(args.executable.read_bytes()).hexdigest(),
        'historical_executable_sha256':provenance['upstream']['historical_executable_sha256'],
        'rebuilt_executable_matches_historical_binary':hashlib.sha256(args.executable.read_bytes()).hexdigest()==provenance['upstream']['historical_executable_sha256'],
        'upstream_source_hashes_verified':True,'tiny_graph_exact_optimum_ticks':optimum,
        'actual_train_graph_verified':args.real_train,'records':records}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'passed':True,'solver_runs':len(records),'actual_train_graph_verified':args.real_train,'tiny_graph_optimum_ticks':optimum}))

if __name__=='__main__':main()
