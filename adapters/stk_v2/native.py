"""Exact CHILS adapter definitions used by both online-v2 development rounds."""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import time

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def child_cpu():
    try:
        import resource
        row = resource.getrusage(resource.RUSAGE_CHILDREN)
        return row.ru_utime + row.ru_stime
    except ImportError:
        return None


def total_cpu(start, children_start):
    now = child_cpu()
    return time.process_time() - start + (now - children_start
        if now is not None and children_start is not None else 0.)


def _base_result(graph, state, start):
    return dict(seed_value_ticks=state.value, value_ticks=state.value,
        selected=sorted(state.selected), stats={}, controller={}, trials=[],
        certificates=[], conditional_local_bound_calls=0, online_llm_calls=0,
        external_oracle_calls=0, policy_reset_at_instance_start=True,
        best_so_far=[dict(cpu_seconds=time.process_time()-start,
                         value_ticks=state.value, stage='degree_seed')])


def run_native(graph, state, args, start, children_start, feasible):
    result = _base_result(graph, state, start)
    native = dict(population=1 if args.method == 'chils_ils' else 4, native_threads=1,
                  publication='10.4230/LIPIcs.SEA.2025.22', native_trace_unavailable=True,
                  objective_transport='original integer microsecond ticks',
                  vertex_transport='METIS 1-based contiguous indices', solver_invoked=False)
    result['native'] = native
    remaining = args.seconds - total_cpu(start, children_start)
    if remaining <= 0:
        native['status'] = 'budget_exhausted_before_native'
        return result
    executable = args.native_executable or os.environ.get('CHILS_EXECUTABLE')
    if not executable or not Path(executable).is_file():
        raise FileNotFoundError('Provide --native-executable or CHILS_EXECUTABLE')
    native['executable_sha256'] = digest(executable)
    nodes = sorted(graph.weights)
    if nodes != list(range(len(nodes))):
        raise ValueError('Native transport requires contiguous zero-based internal vertices')
    if (any(w <= 0 or w >= 2**63 for w in graph.weights.values()) or
            sum(graph.weights.values()) >= 2**63):
        raise ValueError('Original integer weights exceed the signed64 CHILS contract')
    with tempfile.TemporaryDirectory(prefix='stk-online-chils-') as folder:
        folder = Path(folder)
        source, initial, output = (folder/'graph.metis', folder/'initial.ids', folder/'selected.ids')
        with source.open('w', encoding='ascii') as stream:
            stream.write(f'{len(nodes)} {sum(len(graph.adjacency[v]) for v in nodes)//2} 10\n')
            for node in nodes:
                stream.write(str(graph.weights[node])+' '+' '.join(
                    str(other+1) for other in sorted(graph.adjacency[node]))+'\n')
        initial.write_text(''.join(str(v+1)+'\n' for v in sorted(state.selected)), encoding='ascii')
        native.update(input_sha256=digest(source), initial_sha256=digest(initial))
        remaining = args.seconds - total_cpu(start, children_start)
        if remaining <= 0:
            native['status'] = 'budget_exhausted_after_transport'
            return result
        command = [str(executable), '-g', str(source), '-i', str(initial), '-o', str(output),
                   '-p', str(native['population']), '-c', '1', '-t', str(remaining),
                   '-s', '0', '-r', str(args.seed)]
        native.update(solver_invoked=True, native_time_parameter_seconds=remaining,
                      native_time_parameter_scope='native nominal time target; total CPU measured separately',
                      command=command)
        before = child_cpu()
        environment = {**os.environ, 'OMP_NUM_THREADS':'1', 'OPENBLAS_NUM_THREADS':'1',
                       'MKL_NUM_THREADS':'1', 'NUMEXPR_NUM_THREADS':'1'}
        try:
            process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=max(5., remaining+3.), env=environment, check=False)
            native.update(exit_code=process.returncode,
                stdout=process.stdout.decode('utf-8', 'replace')[-12000:],
                stderr=process.stderr.decode('utf-8', 'replace')[-4000:],
                status='ok' if process.returncode == 0 else 'native_failed')
        except subprocess.TimeoutExpired as error:
            native.update(status='native_wall_guard_timeout', exit_code=None,
                stdout=(error.stdout or b'').decode('utf-8', 'replace')[-12000:],
                stderr=(error.stderr or b'').decode('utf-8', 'replace')[-4000:])
        after = child_cpu()
        native['child_cpu_seconds'] = after-before if after is not None and before is not None else None
        if output.is_file():
            ids = [int(value) for value in output.read_text(encoding='ascii').split()]
            if len(ids) != len(set(ids)) or any(v < 1 or v > len(nodes) for v in ids):
                raise ValueError('Malformed 1-based native solution')
            chosen = {v-1 for v in ids}
            if not feasible(graph, chosen):
                raise ValueError('Native solution is infeasible in the original graph')
            native.update(solution_sha256=digest(output), raw_value_ticks=sum(graph.weights[v] for v in chosen))
            if native['raw_value_ticks'] > state.value:
                result.update(selected=sorted(chosen), value_ticks=native['raw_value_ticks'])
                result['best_so_far'].append(dict(cpu_seconds=total_cpu(start, children_start),
                    value_ticks=result['value_ticks'], stage='native_final_observed'))
        elif native['status'] == 'ok':
            native['status'] = 'missing_native_solution'
    result['execution_status'] = ('ok' if native['status'] == 'ok' or
        native['status'].startswith('budget_exhausted') else native['status']+'_seed_guard')
    return result

