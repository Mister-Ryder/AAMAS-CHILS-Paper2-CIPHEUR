# 第二篇论文的 CHILS 实验实现与专家复核包

本仓库提供第二篇论文实验实际使用的 **官方 CHILS 源码、CHILS 输入/输出适配器、两轮最新实验参数与 CHILS 结果证据**。源码对应 [KarlsruheMIS/CHILS](https://github.com/KarlsruheMIS/CHILS) 的固定提交 `515952724cd3dcc6c4365a340ecf0f1da782119a`，发表来源为 [SEA 2025](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SEA.2025.22)。本地适配器负责精确权重传输、共同初始解、计时及原图可行性检查；没有改写官方搜索算法。

## 最重要的实验配置

最新 `stk_online_llm_v2` 的两轮 development 实验都使用同一个官方原生可执行程序，同一个 CHILS 适配器，以及同一个共同初始解函数。虽然两轮完整 benchmark 文件哈希不同，发布的 CHILS 函数及图/初始解函数逐字符完全一致。哈希与原文件行号记录在 [source_provenance.json](evidence/source_provenance.json)。

| 实验标签 | 实际官方代码分支 | 候选数 | 线程数 | 交替间隔 |
|---|---|---:|---:|---:|
| `chils_ils` / CHILS-p1 | `main.c` 的单解 `local_search_explore`，官方 baseline ILS 设置 | 1 | 1 | `-s 0`；此参数不用于该单解分支 |
| `chils` / CHILS-p4 | `chils_run` 的多候选协作分支 | 4 | 1 | `-s 0` |

`p1/p4` 是 population 数量，均使用 `-c 1`，不能解释为四核并行。`p1` 是同一官方可执行程序的单解模式，不能冒称额外独立发表的方法。

**`-s 0` 是实际使用的重要配置。** 在该固定源码的多候选分支中，full-graph timed local search 只有 `duration > 0` 才执行，因而这个阶段会被跳过；d-core 初始化、协作与扰动的分支仍可运行。这里没有使用官方默认的 `-s 10`。早期 V04/V06 适配器使用 `-s 0.1`，不能把两类实验混为同一配置。

最新实验的调用模板为：

```console
CHILS -g graph.metis -i initial.ids -o selected.ids -p 1 -c 1 -t REMAINING -s 0 -r 2
CHILS -g graph.metis -i initial.ids -o selected.ids -p 4 -c 1 -t REMAINING -s 0 -r 2
```

两者都传入共同的 weighted-degree 可行初始解。官方 `-i` 语义也有差别：p1 使用所给初始解；p4 只把它装入候选 1–3，候选 0 保留官方 cold 初始化。适配器仅接受原图可行解，并在最新实验中保留不差于共同初始解的最终输出。

## 文件与来源

| 目录 / 文件 | 内容 |
|---|---|
| `third_party/CHILS/` | 原样固定官方源码、头文件、Makefile、README、MIT LICENSE |
| `adapters/stk_v2/native.py` | 最新两轮实际使用的 CHILS 函数精确摘录，补齐最小导入 |
| `adapters/stk_v2/graph.py` | 两轮实际图载入、初始解及可行性函数精确摘录 |
| `adapters/stk_v1/published_weighted_baselines.py` | 较早完整 STK 实验的原样适配器 |
| `adapters/stk_v1/graph.py` | 该 STK 实验的精确图载入和共同初始解摘录 |
| `adapters/legacy/advanced_baselines.py` | 早期 conservative signed32 total 的原样传输适配器 |
| `adapters/legacy/advanced_baselines_v06.py` | 冻结 V06 实验使用的 CHILS signed64 total 原样适配器 |
| `adapters/legacy/advanced_baselines_gcd_v06.py` | 后续独立的无损 LCM/GCD 适配器，供复核数值编码；不是上述冻结实验的默认配置 |
| `scripts/run_chils.py` | 本次新增的公开运行入口，只暴露 CHILS p1/p4 |
| `scripts/export_chils_input.py` | 从已有 NPZ 中导出纯整数权重与冲突邻接 |
| `evidence/` | 原始来源哈希、参数、两轮 CHILS 结果投影及本次验证收据 |

部分早期传输适配器原文件含其它 solver 的命令格式分支，保留它们是为了维持文件字节及历史哈希；本仓库只提供 CHILS 求解器与 CHILS 运行入口。没有发布其它论文算法或生成过程。

## 快速运行

需要 Linux、GNU17/OpenMP 编译器、make、Python 3.10+ 与 NumPy；Windows 可在 WSL 内执行。历史云实验观察到 Python 3.11.17、NumPy 2.4.6。本次验证使用 WSL Ubuntu 22.04、GCC 11.4.0、Python 3.10.12、NumPy 2.2.6。

```console
python3 -m pip install -r requirements.txt
make -C third_party/CHILS
python3 scripts/run_chils.py --adapter stk-v2 --population 1 --graph examples/toy.json --seconds 0.2 --seed 2 --output output/toy_p1.json
python3 scripts/run_chils.py --adapter stk-v2 --population 4 --graph examples/toy.json --seconds 0.2 --seed 2 --output output/toy_p4.json
python3 scripts/verify_release.py --real-train
```

小型 fixture 的共同初始解为 24,000,000 ticks，穷举验证的最优值为 28,000,000 ticks。本次对五种适配器各运行 p1/p4，共十项；都返回原图可行的最优 fixture 解。这只证明小型 fixture 的接口与运行正确，不证明大图最优性。

也可直接运行原生 CLI：

```console
third_party/CHILS/CHILS -g examples/toy.metis -i examples/toy.initial.ids -o output.ids -p 4 -c 1 -t 0.2 -s 0 -r 2
```

原生输出是 **1-based vertex IDs**。METIS `10` 格式每行先写正整数权重，再写对称的 1-based 邻接。原始 scheduling 权重单位为微秒，收益秒数应由整数和精确除以 1,000,000 得到，不能用 rounding、clipping 或 rank 权重替代。

## 一项真正用于实验的 TRAIN 图

[train_CP-AU-r000_A.metis](examples/train_CP-AU-r000_A.metis) 是最新两轮都使用的一个完整 TRAIN 输入：12,467 个节点、84,132 条无向边，984,168 bytes。它只保留连续整数节点、原始完整 duration 权重和冲突邻接；卫星/天线身份、物理位置、联系人ID、时间戳及私有元数据均未复制。

该导出的 SHA256 `2014798450abc91453371fb1af55cc7c5f62184011f16cf3f47e67a6c5101fe1` 与原实验 p1/p4 收据中的 `native.input_sha256` 完全一致。因此可直接研究实际 CHILS 输入，详见 [train_graph_export.json](evidence/train_graph_export.json)。

```console
python3 scripts/run_chils.py --adapter stk-v2 --population 1 --graph examples/train_CP-AU-r000_A.metis --seconds 1 --seed 2 --output output/train_p1.json
python3 scripts/run_chils.py --adapter stk-v2 --population 4 --graph examples/train_CP-AU-r000_A.metis --seconds 1 --seed 2 --output output/train_p4.json
```

本次重新编译后，两种设置在该图上均验证可行、精确原目标和共同初始解保留；收据保存在 [release_validation.json](evidence/release_validation.json)。公开 runner 是本次新增的轻量入口，不是完整论文实验框架；读取公开图及构建初始解计入其预算。历史结果仍以原实验记录为准。

## 最新两轮的实际记录

各轮包含 4 个 TRAIN 输入系列（共享 2 个物理场景来源）× 4 个约束配置，共 16 个图；每图 p1/p4 各一个 seed 2 的 10 秒总 CPU 目标。两轮共 64 条 CHILS 结果全部发布。这里的 16 个图嵌套在两组物理来源中，不是 16 个独立物理样本。

| 实际设置 | 第一轮平均完整收益（秒） | 第二轮平均完整收益（秒） | 每轮运行数 |
|---|---:|---:|---:|
| CHILS-p1 | 750236.5372054375 | 750236.5372054375 | 16 |
| CHILS-p4 | 738920.8581229375 | 738920.8581229375 | 16 |

p1 在这两轮、这些输入及实际 `-s 0` 设置下强于 p4；不能据此断言任意 CHILS 配置或任意数据集都有相同排序。结果质量本身没有给出最优性证书。原始记录与实际成本见：

- [第一轮结果](evidence/online_v2_round1_chils_results.json) / [汇总](evidence/online_v2_round1_chils_summary.csv)
- [第二轮结果](evidence/online_v2_round2_chils_results.json) / [汇总](evidence/online_v2_round2_chils_summary.csv)
- [各批次参数与来源哈希](evidence/experiment_parameters.json)

历史原生程序的 SHA256 为 `19610c03f334c6267f94543ad3053d792cba56e9ae211fceb6c36f21750c88a0`。本次同源码在不同编译环境重建的程序 SHA256 为 `3d6cef00a5c31a6869df99c45415f6416b702e0bd4f196f8e55d70c9a66d1680`，两者不同；没有把新编译程序当作历史二进制，也没有覆盖原结果。

## 专家阅读入口与计时边界

建议从 `src/main.c` 的 p1/p>1 分支和初始解装载开始，再读 `src/local_search.c` 的 greedy、two_one、aap、perturb，以及 `src/chils_internal.c` 的 `chils_run`、disagreement d-core、协作回注与扰动。原始图/解/gain 权重累加使用 `long long`，适配器的 signed64 total 限制针对这一固定源码。

官方 `-t` 是内部名义 **wall time** 目标，不是整个 Python 流程的严格 CPU 截止。局部搜索间隔检查以及初始 greedy 可能造成实际超时。原生 `solution_time`、`total_time`、外部 wall time 和总 CPU 是不同测量；最新实验总 CPU 包含 Python 与原生子进程的实测成本，输入传输及初始解也被计费，实际超预算保留在证据中。

当前没有官方内部 incumbent 的完整 trace。可观察的初始解/最终解标记不足以说明预算中间如何进步，更不能把没有内部曲线解释为算法没有搜索。CHILS 在项目框架中没有 patch proposal，记录 proposal count 为零也不等于没有原生搜索。

## 版权与范围

官方 CHILS 的 MIT 许可和原作者版权完整保留在 [third_party/CHILS/LICENSE](third_party/CHILS/LICENSE)。原作者是 Kenneth Langedal、Ernestine Großmann、Christian Schulz。归属和本地代码许可边界见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

本仓库用于研究与复核实际 CHILS 实验实现。
