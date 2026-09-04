#!/usr/bin/env python3
"""Prepare HTCondor chunk files and a sample-aware JDL from DAS YAML headers."""

import argparse
import json
import logging
import re
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")


def safe_path_label(label):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "unclassified"


def get_chunks(items, size):
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def get_filenames(dataset, retry=3):
    import time

    query = "file dataset=%s" % dataset
    if dataset.endswith("/USER"):
        query += " instance=prod/phys03"
    cmd = ["dasgoclient", "-query", query, "-json"]

    for attempt in range(retry + 1):
        if attempt:
            time.sleep(3)
        logging.info("Querying DAS for %s", dataset)
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = proc.communicate()
        if proc.returncode != 0 or errs:
            logging.error("DAS query failed: %s", errs.decode("utf-8", errors="replace"))
            continue

        files = []
        for row in json.loads(outs.decode("utf-8")):
            for rec in row.get("file", []):
                name = rec.get("name")
                if name:
                    files.append(str(name))
        return sorted(files)

    raise RuntimeError("Failed to retrieve file names from DAS for: %s" % dataset)


def load_dataset_queries_without_pyyaml(handle):
    data = {}
    current_key = None
    pending_list = None

    for raw_line in handle:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if not raw_line.startswith((" ", "\t", "-")) and line.endswith(":"):
            current_key = line[:-1]
            data[current_key] = []
            pending_list = None
            continue
        if current_key is None:
            raise ValueError("Dataset YAML entry appears before a sample key: %s" % raw_line)
        if line.startswith("- ["):
            pending_list = []
            data[current_key].append(pending_list)
            continue
        if pending_list is not None:
            if line == "]":
                pending_list = None
            else:
                pending_list.append(line.rstrip(","))
            continue
        if line.startswith("- "):
            data[current_key].append(line[2:].strip().rstrip(","))
            continue
        raise ValueError("Unsupported YAML line without PyYAML installed: %s" % raw_line)

    return data


def load_dataset_queries(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) if yaml is not None else load_dataset_queries_without_pyyaml(handle)

    datasets = []
    for sample_name, entries in data.items():
        for entry in entries:
            if isinstance(entry, list):
                datasets.extend((sample_name, dataset) for dataset in entry)
            else:
                datasets.append((sample_name, entry))
    return datasets


def write_jdl(path, args_file, mode):
    executable = "run_cmsdriver_mc.sh" if mode == "mc" else "run_cmsdriver_data.sh"
    memory = "6144MB" if mode == "mc" else "4096MB"
    log_prefix = "mc_nanoaod" if mode == "mc" else "data_nanoaod"
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(
            """universe = vanilla
executable = {executable}
arguments = $(JobId) $(SampleName) $(InputList)
transfer_input_files = $(SUBMIT_DIR)/../cmsskim_customize.py, $(SUBMIT_DIR)/../MyAnalysis, $(SUBMIT_DIR)/$(InputList)

log = logs/{log_prefix}_$(Cluster)_$(Process).log
output = logs/{log_prefix}_$(Cluster)_$(Process).out
error = logs/{log_prefix}_$(Cluster)_$(Process).err

request_cpus = 8
request_memory = {memory}
request_disk = 10GB

on_exit_hold = (ExitCode != 0)
on_exit_remove = (ExitCode == 0)
use_x509userproxy = true
priority = 0
+JobFlavour = "testmatch"

queue JobId,SampleName,InputList from {args_file}
""".format(executable=executable, log_prefix=log_prefix, memory=memory, args_file=args_file.name)
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_yaml")
    parser.add_argument("--mode", choices=("data", "mc"), required=True)
    parser.add_argument("--files-per-chunk", type=int, default=5)
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--retry", type=int, default=3)
    args = parser.parse_args()

    if args.files_per_chunk <= 0:
        raise ValueError("--files-per-chunk must be positive")

    prefix = "miniAODSIM_chunk" if args.mode == "mc" else "miniAOD_chunk"
    args_path = Path("condor_%s_jobs.txt" % args.mode)
    jdl_path = Path("cms_nanoAODv15_%s_generated.jdl" % args.mode)
    rows = []
    job_id = 0

    for sample_name, dataset in load_dataset_queries(args.dataset_yaml):
        files = get_filenames(dataset, retry=args.retry)
        if args.max_files:
            files = files[:args.max_files]

        sample_dir = safe_path_label(sample_name)
        for chunk in get_chunks(files, args.files_per_chunk):
            chunk_name = "%s_%s_%d.txt" % (prefix, sample_dir, job_id)
            with open(chunk_name, "w", encoding="utf-8") as handle:
                for name in chunk:
                    handle.write(name + "\n")
            rows.append("%d %s %s\n" % (job_id, sample_dir, chunk_name))
            job_id += 1

    with open(args_path, "w", encoding="utf-8") as handle:
        handle.writelines(rows)
    write_jdl(jdl_path, args_path, args.mode)
    logging.info("Wrote %s and %s with %d jobs", args_path, jdl_path, job_id)


if __name__ == "__main__":
    main()
