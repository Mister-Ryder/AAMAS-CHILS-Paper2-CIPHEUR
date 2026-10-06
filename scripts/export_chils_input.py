#!/usr/bin/env python3
"""Export only integer duration weights and conflict adjacency from an NPZ graph.

No contact identities, positions, timestamps, stations or satellites are copied.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--npz',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with np.load(args.npz,allow_pickle=False) as raw:
        weights=[int(w) for w in raw['weight_ticks']]
        adjacency={i:set() for i in range(len(weights))}
        for a,b in zip(raw['edge_u'],raw['edge_v']):
            a,b=int(a),int(b)
            if a==b:raise ValueError('Self edge')
            adjacency[a].add(b);adjacency[b].add(a)
        if 'start_ticks' in raw and 'end_ticks' in raw:
            if not np.array_equal(raw['weight_ticks'],raw['end_ticks']-raw['start_ticks']):
                raise ValueError('Weights are not original complete-duration microseconds')
    if any(w<=0 or w>=2**63 for w in weights) or sum(weights)>=2**63:
        raise ValueError('Invalid signed64 original weights')
    text=f'{len(weights)} {sum(map(len,adjacency.values()))//2} 10\n'
    text+=''.join(str(weights[v])+' '+' '.join(str(u+1) for u in sorted(adjacency[v]))+'\n' for v in range(len(weights)))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(text,encoding='ascii',newline='\n')
    print(json.dumps({'vertices':len(weights),'edges':sum(map(len,adjacency.values()))//2,
        'input_npz_sha256':hashlib.sha256(args.npz.read_bytes()).hexdigest(),
        'export_sha256':hashlib.sha256(text.encode('ascii')).hexdigest()}))

if __name__=='__main__':main()
