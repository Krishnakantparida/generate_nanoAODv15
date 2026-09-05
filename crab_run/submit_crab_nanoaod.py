#!/usr/bin/env python3
"""Create and optionally submit CRAB NanoAOD/NanoAODSIM jobs from DAS YAML files."""

import argparse
import json
import logging
import os
import re
import subprocess
import textwrap
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")


def get_chunks(items, size):
    """Yield successive size-sized chunks from items."""
    for idx in range(0, len(items), size):
        yield items[idx:idx + size]


def natural_sort(items):
    def convert(text):
        return int(text) if text.isdigit() else text.lower()

    def key(value):
        return [convert(part) for part in re.split("([0-9]+)", value)]

    return sorted(items, key=key)


def get_filenames(dataset, retry=3):
    """Return files for a given DAS dataset query via dasgoclient."""
    import time

    query = "file dataset=%s" % dataset
    if dataset.endswith("/USER"):
        query += " instance=prod/phys03"
    cmd = ["dasgoclient", "-query", query, "-json"]

    for attempt in range(retry + 1):
        if attempt:
            logging.info("Retrying DAS query for %s (%d/%d)", dataset, attempt, retry)
            time.sleep(3)
        else:
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
        logging.info("Found %d files for %s", len(files), dataset)
        return natural_sort(files)

    raise RuntimeError("Failed to retrieve file names from DAS for: %s" % dataset)


def load_dataset_queries(path):
    with open(path, "r", encoding="utf-8") as handle:
        if yaml is not None:
            data = yaml.safe_load(handle)
        else:
            data = load_dataset_queries_without_pyyaml(handle)

    datasets = []
    for sample_name, entries in data.items():
        for entry in entries:
            if isinstance(entry, list):
                datasets.extend((sample_name, dataset) for dataset in entry)
            else:
                datasets.append((sample_name, entry))
    return datasets


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
            remainder = line[3:].strip()
            if remainder and remainder != "[":
                pending_list.append(remainder.rstrip(","))
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


def dataset_label(dataset):
    pieces = dataset.strip("/").split("/")
    if not pieces:
        return "dataset"
    label = "_".join(pieces[:2])
    return re.sub(r"[^A-Za-z0-9_]+", "_", label).strip("_")


def safe_path_label(label):
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", label).strip("_") or "unclassified"


def write_file_list(path, files, xrootd_prefix):
    with open(path, "w", encoding="utf-8") as handle:
        for name in files:
            if name.startswith("root://"):
                handle.write(name + "\n")
            else:
                handle.write(xrootd_prefix.rstrip("/") + "/" + name.lstrip("/") + "\n")


def cmsdriver_command(args, first_file, cfg_path, output_file):
    common = [
        "cmsDriver.py", "NANO",
        "--era", args.era,
        "--conditions", args.conditions,
        "--datatier", args.datatier,
        "--eventcontent", args.eventcontent,
        "--step", "NANO",
        "--python_filename", str(cfg_path),
        "--filein", first_file,
        "--fileout", "file:%s" % output_file,
        "--scenario", "pp",
        "--number", str(args.number),
        "--nThreads", str(args.threads),
        "--no_exec",
    ]
    if args.is_mc:
        common.extend(["--mc", "--customise", "Configuration/DataProcessing/Utils.addMonitoring"])
    else:
        common.append("--data")
    return common


def append_customization(cfg_path, file_list_name, output_file, output_module, include_mc_weights):
    imports = [
        "SetupAK8ReclusterSubjets",
        "SetupSkim_HLTSingleMuonOneFatJet",
        "SetupGloParTForAK8Subjets",
    ]
    if include_mc_weights:
        imports.insert(1, "SetupSkimForMC_AlwaysRunWeightsTable")

    with open(cfg_path, "a", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(
            """

            # ========== CUSTOM SKIMMING CONFIGURATION ==========
            import sys
            sys.path.insert(0, '.')
            from cmsskim_customize import {imports}

            process = SetupSkim_HLTSingleMuonOneFatJet(process)
            process = SetupGloParTForAK8Subjets(process)
            process = SetupAK8ReclusterSubjets(process)

            with open("{file_list}", "r") as _input_handle:
                _input_files = [
                    line.strip()
                    for line in _input_handle
                    if line.strip()
                ]

            process.source.fileNames = cms.untracked.vstring(*_input_files)
            process.{output_module}.fileName = cms.untracked.string("file:{output_file}")
            """
        ).format(
            imports=", ".join(imports),
            file_list=file_list_name,
            output_module=output_module,
            output_file=output_file,
        ))


def write_crab_config(path, args, request_name, pset_name, file_list_name, output_dataset_tag, sample_name):
    site_storage = args.storage_site
    tier_dir = "mc" if args.is_mc else "data"
    out_lfn = "%s/%s/%s" % (args.out_lfn_dir_base.rstrip("/"), tier_dir, safe_path_label(sample_name))
    work_area = args.crab_work_area
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(textwrap.dedent(
            """
            from CRABClient.UserUtilities import config

            config = config()
            config.General.requestName = '{request_name}'
            config.General.workArea = '{work_area}'
            config.General.transferOutputs = True
            config.General.transferLogs = True

            config.JobType.pluginName = 'Analysis'
            config.JobType.psetName = '{pset_name}'
            config.JobType.inputFiles = ['cmsskim_customize.py', '{file_list_name}']
            config.JobType.allowUndistributedCMSSW = True

            config.Data.splitting = 'FileBased'
            config.Data.userInputFiles = [line.strip() for line in open('{file_list_name}') if line.strip()]
            config.Data.unitsPerJob = {units_per_job}
            config.Data.publication = False
            config.Data.outputDatasetTag = '{output_dataset_tag}'
            config.Data.outLFNDirBase = '{out_lfn}'

            config.Site.storageSite = '{site_storage}'
            """
        ).format(
            request_name=request_name,
            work_area=work_area,
            pset_name=pset_name,
            file_list_name=file_list_name,
            units_per_job=max(1, args.units_per_job),
            output_dataset_tag=output_dataset_tag,
            out_lfn=out_lfn,
            site_storage=site_storage,
        ))


def run(cmd, cwd):
    logging.info("Running: %s", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd))


def crab_project_dir(job_dir, args, request_name):
    work_area = Path(args.crab_work_area)
    if not work_area.is_absolute():
        work_area = job_dir / work_area
    return work_area / request_name


def generated_job_dirs(output_dir):
    return sorted(path.parent for path in output_dir.glob("*/crab_config.py"))


def manage_existing_jobs(args, output_dir):
    job_dirs = generated_job_dirs(output_dir)
    if not job_dirs:
        raise RuntimeError(
            "No generated CRAB jobs found in %s; run without a lifecycle action first"
            % output_dir
        )

    for job_dir in job_dirs:
        crab_config = job_dir / "crab_config.py"
        request_name = job_dir.name
        project_dir = crab_project_dir(job_dir, args, request_name)
        command = {
            "status": ["crab", "status", "-d", str(project_dir), "--verboseErrors"],
            "resubmit": ["crab", "resubmit", "-d", str(project_dir)],
            "getoutput": ["crab", "getoutput", "-d", str(project_dir)],
        }[args.action]
        logging.info("Managing %s using %s", crab_config, args.action)
        run(command, cwd=job_dir)


def build_jobs(args):
    repo_root = Path(__file__).resolve().parents[1]
    crab_dir = Path(__file__).resolve().parent
    output_dir = (crab_dir / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.action in ("status", "resubmit", "getoutput"):
        manage_existing_jobs(args, output_dir)
        return

    datasets = load_dataset_queries(args.dataset_yaml)
    output_module = "NANOAODSIMoutput" if args.is_mc else "NANOAODoutput"

    for sample_name, dataset in datasets:
        files = get_filenames(dataset, retry=args.retry)
        if args.max_files:
            files = files[:args.max_files]
        if not files:
            logging.warning("No files found for %s; skipping", dataset)
            continue

        for chunk_index, chunk in enumerate(get_chunks(files, args.files_per_chunk)):
            label = dataset_label(dataset)
            job_name = "%s_%s_%03d" % (sample_name, label, chunk_index)
            job_name = re.sub(r"[^A-Za-z0-9_]+", "_", job_name)[:95]
            job_dir = output_dir / job_name
            job_dir.mkdir(parents=True, exist_ok=True)

            file_list = job_dir / "input_files.txt"
            cfg_path = job_dir / ("%s_cfg.py" % job_name)
            crab_cfg = job_dir / "crab_config.py"
            output_file = "%s_%s.root" % (args.output_prefix, job_name)

            write_file_list(file_list, chunk, args.xrootd_prefix)
            first_file = file_list.read_text(encoding="utf-8").splitlines()[0]
            run(cmsdriver_command(args, first_file, cfg_path, output_file), cwd=job_dir)
            append_customization(
                cfg_path,
                file_list.name,
                output_file,
                output_module,
                include_mc_weights=args.is_mc,
            )

            write_crab_config(
                crab_cfg,
                args,
                request_name=job_name,
                pset_name=cfg_path.name,
                file_list_name=file_list.name,
                output_dataset_tag=job_name,
                sample_name=sample_name,
            )

            for dependency in ("cmsskim_customize.py",):
                source = repo_root / dependency
                target = job_dir / dependency
                if target.exists():
                    continue
                if source.is_dir():
                    subprocess.check_call(["cp", "-R", str(source), str(target)])
                else:
                    subprocess.check_call(["cp", str(source), str(target)])

            if args.action == "submit":
                run(["crab", "submit", "-c", str(crab_cfg)], cwd=job_dir)
            else:
                logging.info("Prepared %s", crab_cfg)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "dataset_yaml",
        nargs="?",
        help="YAML file containing DAS dataset queries (required for prepare/submit)",
    )
    parser.add_argument("--mc", dest="is_mc", action="store_true", help="Create NanoAODSIM jobs")
    parser.add_argument("--data", dest="is_mc", action="store_false", help="Create NanoAOD data jobs")
    parser.set_defaults(is_mc=True)
    parser.add_argument("--files-per-chunk", type=int, default=5)
    parser.add_argument("--units-per-job", type=int, default=1)
    parser.add_argument("--max-files", type=int, default=0)
    parser.add_argument("--retry", type=int, default=3)
    parser.add_argument(
        "--action",
        choices=("prepare", "submit", "status", "resubmit", "getoutput"),
        default="prepare",
        help="CRAB lifecycle action; status/resubmit/getoutput use existing generated jobs",
    )
    parser.add_argument(
        "--submit",
        action="store_const",
        const="submit",
        dest="action",
        help="Backward-compatible alias for --action submit",
    )
    parser.add_argument("--output-dir", default="generated")
    parser.add_argument("--crab-work-area", default="crab_projects")
    parser.add_argument("--storage-site", default="T3_US_FNALLPC")
    parser.add_argument("--out-lfn-dir-base", default="/store/group/lpcjm/%s/cms_nanoaod" % os.environ.get("USER", "USER"))
    parser.add_argument("--xrootd-prefix", default="root://cmsxrootd.fnal.gov/")
    parser.add_argument("--threads", type=int, default=8)
    parser.add_argument("--number", type=int, default=-1)
    parser.add_argument("--era", default="Run3_2024")
    parser.add_argument("--conditions", default=None)
    parser.add_argument("--datatier", default=None)
    parser.add_argument("--eventcontent", default=None)
    parser.add_argument("--output-prefix", default=None)
    args = parser.parse_args()

    if args.conditions is None:
        args.conditions = "150X_mcRun3_2024_realistic_v2" if args.is_mc else "150X_dataRun3_v2"
    if args.datatier is None:
        args.datatier = "NANOAODSIM" if args.is_mc else "NANOAOD"
    if args.eventcontent is None:
        args.eventcontent = "NANOAODSIM" if args.is_mc else "NANOAOD"
    if args.output_prefix is None:
        args.output_prefix = "NANOAODSIM" if args.is_mc else "NANOAOD"
    if args.files_per_chunk <= 0:
        raise ValueError("--files-per-chunk must be positive")
    if args.units_per_job <= 0:
        raise ValueError("--units-per-job must be positive")
    if args.action in ("prepare", "submit") and not args.dataset_yaml:
        parser.error("dataset_yaml is required for --action %s" % args.action)
    return args


if __name__ == "__main__":
    build_jobs(parse_args())
