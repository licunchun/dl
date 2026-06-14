# Short-Term Job Monitor

- Job: `27558`
- Started monitor: 2026-05-29T23:20:49+08:00
- Poll interval seconds: `1800`

## Poll 2026-05-29T23:20:49+08:00

```text
             JOBID  PARTITION                     NAME     USER ST       TIME  NODES NODELIST(REASON)
             27558       A100          a100_short_term    lcc17  R      13:40      1 gpu18
```

### stdout tail
```text
[job] start 2026-05-29T23:07:09+08:00
[job] host gpu18-A100-E3-3U
[job] cwd /home/lcc17/dl
[job] slurm job id 27558
Python 3.11.15
[env] torch 2.12.0+cu126
[env] cuda_available True
[env] device0 NVIDIA A100-SXM4-80GB
Fri May 29 23:07:13 2026       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 595.71.05              Driver Version: 595.71.05      CUDA Version: 13.2     |
+-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  NVIDIA A100-SXM4-80GB          On  |   00000000:27:00.0 Off |                    0 |
| N/A   49C    P0            114W /  400W |   72297MiB /  81920MiB |     11%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
|   1  NVIDIA A100-SXM4-80GB          On  |   00000000:2A:00.0 Off |                    0 |
| N/A   43C    P0            238W /  400W |   16663MiB /  81920MiB |     82%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
|   2  NVIDIA A100-SXM4-80GB          On  |   00000000:51:00.0 Off |                    0 |
| N/A   47C    P0            324W /  400W |   72297MiB /  81920MiB |     97%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
|   3  NVIDIA A100-SXM4-80GB          On  |   00000000:57:00.0 Off |                    0 |
| N/A   34C    P0             62W /  400W |       0MiB /  81920MiB |      0%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
|   4  NVIDIA A100-SXM4-80GB          On  |   00000000:9E:00.0 Off |                    0 |
| N/A   57C    P0            287W /  400W |   17307MiB /  81920MiB |     97%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
|   5  NVIDIA A100-SXM4-80GB          On  |   00000000:A4:00.0 Off |                    0 |
| N/A   44C    P0            216W /  400W |   35041MiB /  81920MiB |     76%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
|   6  NVIDIA A100-SXM4-80GB          On  |   00000000:C7:00.0 Off |                    0 |
| N/A   26C    P0             58W /  400W |       0MiB /  81920MiB |      0%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+
|   7  NVIDIA A100-SXM4-80GB          On  |   00000000:CA:00.0 Off |                    0 |
| N/A   29C    P0             59W /  400W |       0MiB /  81920MiB |      0%      Default |
|                                         |                        |             Disabled |
+-----------------------------------------+------------------------+----------------------+

+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI              PID   Type   Process name                        GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|    0   N/A  N/A         2010386      C   ...envs/diffsynth/bin/python3.12      72288MiB |
|    1   N/A  N/A         1985992      C   .../lagin/ADEPT/.venv/bin/python      16654MiB |
|    2   N/A  N/A         2010387      C   ...envs/diffsynth/bin/python3.12      72288MiB |
|    4   N/A  N/A         1981403      C   .../lagin/ADEPT/.venv/bin/python      17298MiB |
|    5   N/A  N/A         2212155      C   python                                35032MiB |
+-----------------------------------------------------------------------------------------+
[job] short-term competition model
```

### stderr tail
```text
/home/lcc17/dl/scripts/short_term_competition_train.py:369: FutureWarning: `torch.cuda.amp.GradScaler(args...)` is deprecated. Please use `torch.amp.GradScaler('cuda', args...)` instead.
  scaler = torch.cuda.amp.GradScaler(enabled=cfg.amp)
```

