#!/bin/bash

#module load anaconda3
conda activate msprime_scripts

set -euo pipefail

# make slurm_out if not exists
[[ -d slurm_out ]] || mkdir slurm_out

##to view dependency graph (use only a few seeds!)
#snakemake --dag --config null_simulations=1 admixed_simulations=1 | dot -Tsvg > dag.svg

##unlock if job was interrupted
#snakemake --unlock

##perform workflow.  
snakemake --cluster-config della_cluster.yaml \
    --cluster "sbatch --cpus-per-task={cluster.n} \
        --mem={cluster.memory} --time={cluster.time} \
        --output=slurm_out/{cluster.jobname}_%A --job-name={cluster.jobname} \
        --parsable" \
    --use-conda \
    -pr \
    -w 60 -j 50 \
    #--rerun-incomplete
