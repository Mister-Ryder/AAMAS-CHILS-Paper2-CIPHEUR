"""Exact graph transport and common degree seed used by both online-v2 rounds."""
from __future__ import annotations
from dataclasses import dataclass
from fractions import Fraction
import json
from pathlib import Path
import numpy as np

@dataclass
class IntGraph:
    adjacency: dict
    weights: dict
    contact_ids: list
    metadata: dict
    source_metadata: dict
    edge_u: np.ndarray
    edge_v: np.ndarray


def load_graph(path, metadata_path):
    with np.load(path,allow_pickle=False) as z:
        ids=[str(x) for x in z['contact_id']]
        weights={i:int(w) for i,w in enumerate(z['weight_ticks'])}
        adj={i:set() for i in weights}
        u=z['edge_u'].astype(np.int64);v=z['edge_v'].astype(np.int64)
        for a,b in zip(u,v):
            a=int(a);b=int(b);adj[a].add(b);adj[b].add(a)
        gap=z['ground_gap_by_node_ticks'] if 'ground_gap_by_node_ticks' in z else [int(z['ground_gap_ticks'].item())]*len(ids)
        data=dict(weight_scale=1000000,
            duration={i:Fraction(int(b)-int(a),1000000) for i,(a,b) in enumerate(zip(z['start_ticks'],z['end_ticks']))},
            station_gap={i:Fraction(int(g),1000000) for i,g in enumerate(gap)},
            satellite_gap=Fraction(int(z['satellite_gap_ticks'].item()),1000000),
            station={i:str(x) for i,x in enumerate(z['antenna_id'])},
            satellite={i:str(x) for i,x in enumerate(z['satellite_id'])})
    meta=json.loads(Path(metadata_path).read_text(encoding='utf-8'))
    return IntGraph(adj,weights,ids,data,meta,u,v)


class Incumbent:
    def __init__(self, graph, initial=()):
        self.graph=graph;self.selected=set();self.order=[];self.positions={}
        self.blockers=[0]*len(graph.weights);self.value=0
        for node in initial:self.add(node)
    def add(self,node):
        if node in self.selected or self.blockers[node]:raise AssertionError('Infeasible insertion')
        self.positions[node]=len(self.order);self.order.append(node);self.selected.add(node)
        self.value+=self.graph.weights[node]
        for other in self.graph.adjacency[node]:self.blockers[other]+=1
    def remove(self,node):
        pos=self.positions.pop(node);last=self.order.pop()
        if pos<len(self.order):self.order[pos]=last;self.positions[last]=pos
        self.selected.remove(node);self.value-=self.graph.weights[node]
        for other in self.graph.adjacency[node]:self.blockers[other]-=1
    def commit(self,removed,added):
        before=self.value
        if sum(self.graph.weights[v] for v in added)<=sum(self.graph.weights[v] for v in removed):return False
        for v in removed:self.remove(v)
        try:
            for v in added:self.add(v)
        except Exception:
            for v in set(added)&self.selected:self.remove(v)
            for v in removed:self.add(v)
            raise
        assert self.value>before
        return True


def degree_seed(graph, initial=()):
    state=Incumbent(graph,initial)
    for node in sorted(graph.weights,key=lambda v:(-graph.weights[v]/(1+len(graph.adjacency[v])),v)):
        if node not in state.selected and not state.blockers[node]:state.add(node)
    return state


def feasible(graph,chosen):
    return all(not(graph.adjacency[v]&chosen) for v in chosen)

