"""Exact graph transport and common degree seed excerpts from STK v1."""
from __future__ import annotations
from fractions import Fraction
import json
from pathlib import Path
import time
import numpy as np
from adapters.legacy.model import Contact, Graph
SCALE=1000000
NAMESPACE="heterogeneous_station_local_base9_full_schedule_v1"

def value_ticks(graph,nodes):return sum(graph.provenance["weight_ticks"][v] for v in nodes)


def value_exact(graph,nodes):return str(Fraction(value_ticks(graph,nodes),SCALE))


def load_graph(npz_path,metadata_path,meter):
    started=time.process_time()
    with np.load(npz_path,allow_pickle=False) as stored:z={k:stored[k].copy() for k in stored.files}
    meta=json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    ids=[str(v) for v in z["contact_id"]]
    weights=[int(v) for v in z["weight_ticks"]]
    if "ground_gap_by_node_ticks" in z:node_gaps=[int(v) for v in z["ground_gap_by_node_ticks"]]
    else:node_gaps=[int(z["ground_gap_ticks"].item())]*len(ids)
    antenna_gaps={}
    for i,antenna in enumerate(z["antenna_id"]):
        antenna=str(antenna);gap=Fraction(node_gaps[i],SCALE)
        if gap.denominator!=1:raise ValueError("Contract requires integral gap seconds")
        if antenna in antenna_gaps and antenna_gaps[antenna]!=int(gap):raise ValueError("Inconsistent antenna gaps")
        antenna_gaps[antenna]=int(gap)
    if "station_gap_by_antenna_seconds" in meta and antenna_gaps!=meta["station_gap_by_antenna_seconds"]:
        raise ValueError("Station metadata does not match every root field")
    satellite_gap=Fraction(int(z["satellite_gap_ticks"].item()),SCALE)
    if satellite_gap.denominator!=1:raise ValueError("Contract requires integral satellite gap seconds")
    contacts=tuple(Contact(ids[i],Fraction(weights[i],SCALE),str(z["satellite_id"][i]),str(z["antenna_id"][i]),
        Fraction(int(z["start_ticks"][i]),SCALE),Fraction(int(z["end_ticks"][i]),SCALE)) for i in range(len(ids)))
    graph=Graph(str(meta.get("source_id",z["source_id"].item()))+":"+str(meta.get("config_id",Path(npz_path).stem)),
        contacts,frozenset((ids[int(a)],ids[int(b)]) for a,b in zip(z["edge_u"],z["edge_v"])),
        {"station_gap_mode":"per_antenna","station_gap_by_antenna":antenna_gaps,"satellite_gap":int(satellite_gap)},
        {"weight_ticks":dict(zip(ids,weights)),"metadata":meta,"numeric_namespace":NAMESPACE})
    # Bulk input work/time is charged; a mandatory seed can still be retained if
    # input parsing alone exceeded the target, with explicit overshoot recorded.
    meter.sealed=True;meter.tick("input_array_and_graph_materialization",len(ids)+2*len(graph.edges));meter.sealed=False
    return graph,{"input_cpu_seconds":time.process_time()-started,"nodes":len(ids),"edges":len(graph.edges)}


def static_completion(graph,domain,initial,meter):
    """Complete a preserved head prefix, never remove/reorder its choices."""
    chosen=set(initial);domain=set(domain)
    if not graph.feasible(chosen) or not chosen<=domain:raise AssertionError("Invalid preserved prefix")
    blocked=set(chosen)
    for node in chosen:blocked.update(graph.adj[node])
    weights=graph.provenance["weight_ticks"]
    order=sorted(domain-blocked,key=lambda node:(-Fraction(weights[node],1+len(graph.adj[node]&domain)),node))
    meter.tick("common_static_degree_completion",len(domain)+sum(len(graph.adj[node]) for node in domain))
    for node in order:
        if node not in blocked:chosen.add(node);blocked.update(graph.adj[node])
    return chosen

